# ADR-0001: Derive canonical bus stop order via pairwise voting on snapshot ETAs

- **Status:** Accepted
- **Date:** 2026-06-04
- **Scope:** `transformation/models/intermediate/line_stops/int_line_stops.sql`

## Context

The Olho Vivo `previsao` API returns, for each `(line_id, stop_id)`, the
vehicles currently approaching that stop and their ETA. Snapshots are stored
as JSON blobs and unnested into `stg_previsao_raw`, then enriched with
arrival-time arithmetic in `int_previsao_calculated`.

We need a single, persistent table that lists, for each directional bus line,
the **canonical order of its stops** along the route. There is no SPTrans
endpoint that exposes this list directly; we must infer it from the ETA
observations we already collect.

Constraints:

- A single snapshot of a single vehicle only reveals stops **ahead** of the
  bus's current position — never behind.
- Many snapshots, many vehicles, and many days are available; coverage of any
  particular `(line_id, stop_id)` is uneven.
- Within a single snapshot two stops can share an ETA minute (tied), so any
  ordering scheme must be robust to ties.
- `line_id` is directional (the same physical route uses two distinct ids,
  one per direction), so we do **not** need to disambiguate trip direction.

## Decision

For each `(source, line_id, vehicle_id)` snapshot, generate every pair of
stops `(predecessor, successor)` where `predecessor.minutes_until_arrival <
successor.minutes_until_arrival`. Aggregate these pair counts across all
snapshots. For each stop on each line, compute

```
forward_score = times_before / (times_before + times_after)
```

and rank stops within each `line_id` by `forward_score DESC` (ties broken
deterministically by `stop_id`). The resulting `stop_order` is the canonical
position of the stop along the route, 1-indexed from the line's first stop.

## Considered alternatives

1. **Average per-snapshot rank.** For each snapshot, rank stops 1..N by ETA;
   for each `(line_id, stop_id)` take the mean. Rejected: stops near the
   *start* of a line are only ever visible from a tiny number of snapshots
   (only when a vehicle is at the very beginning), so their averages are
   noisy and biased relative to mid-route stops, which appear in many more
   snapshots.

2. **Best snapshot per vehicle.** Pick, per `(line_id, vehicle_id)`, the
   snapshot with the most distinct stops visible (proxy for "vehicle nearest
   to the line's start") and trust that snapshot's order. Then unify across
   vehicles. Rejected: brittle — a single bad snapshot can corrupt the order
   for an entire vehicle; no graceful handling of ties; relies on assuming
   the API returns *all* downstream stops, which it doesn't always.

3. **Topological sort of a predecessor → successor graph.** Build a DAG from
   the same pairwise observations, then topo-sort. Rejected: cycles caused by
   noisy snapshots (e.g. delayed predictions, snapshot timestamp skew) make
   pure topo-sort fragile; expensive to express in pure SQL on Postgres.

Pairwise voting was preferred because it (a) uses *all* observations
democratically, (b) naturally handles ties via the continuous score, (c) is
robust to a few noisy snapshots (one bad pair against thousands of good ones
barely moves the score), and (d) is expressible as a single dbt model with
window functions.

## Consequences

**Positive**

- Single intermediate table provides line-level stop ordering for the entire
  warehouse, replacing per-snapshot ad-hoc ranking.
- Score column (`forward_score`) is interpretable and can flag low-confidence
  stops (e.g. score very close to 0.5).
- Adapts automatically as more data arrives — re-running the model
  incorporates new observations without manual intervention.

**Negative**

- The self-join on `int_previsao_calculated` is O(rows²) within each
  `(source, line_id, vehicle_id)` group; growth must be monitored. If
  snapshots become very dense (many stops per snapshot per vehicle), the
  intermediate pair count CTE will balloon. Mitigation if needed: sample
  snapshots (e.g. one per hour per vehicle) before pairing.
- Two stops with identical pairwise statistics are broken by `stop_id` order,
  which is arbitrary. In practice this only affects stops that genuinely
  share ETAs in every snapshot.

## Validation

Empirical validation by comparing the model's stop order to the SPTrans
website (`/Linha/Buscar`) for individual vehicles. The website lists, per
stop on a line, the ETA of each approaching vehicle relative to a reference
time. Sorting those ETAs for a single chosen vehicle gives a ground-truth
forward order from that vehicle's current position.

Validation runs (see `sandbox/parse_webscrape.py` and `sandbox/compare_line.py`):

| Line  | Vehicle | Stops compared | Pearson r | Exact-rank matches |
|-------|---------|----------------|-----------|--------------------|
| 1140  | 63557   | 38 / 38        | 0.9991    | 30 / 38 (78.9 %)   |
| 33170 | 31935   | 75 / 75        | 0.9999    | 67 / 75 (89.3 %)   |

In both cases every stop the website reported for the vehicle was present in
the model with a near-identical rank. The model additionally surfaced
early-terminal stops the chosen vehicle had already passed (and therefore did
not appear in its snapshot). All deviations from a constant rank offset fell
inside ETA-tied groups, where the website itself does not impose a strict
order.

To re-run validation: save the SPTrans line page as `webscrape_<vid>.htm` at
the project root, then

```
python sandbox/parse_webscrape.py webscrape_<vid>.htm <vid>
python sandbox/compare_line.py <line_id> <vid>
```

Expect Pearson r > 0.99 for any healthy line; any drop below that signals
either data drift or a model regression.
