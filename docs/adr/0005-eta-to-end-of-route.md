# ADR-0005: Derive "ETA to end of route" as the difference between the next-stop and final-stop ETAs

- **Status:** Accepted
- **Date:** 2026-06-04
- **Scope:** `transformation/models/intermediate/int_eta_to_end_of_route.sql`

## Context

The project needs an average-ETA metric for analysis of how weather and
accidents affect bus route delays. The naive approach — averaging
`minutes_until_arrival` over all `(snapshot, vehicle, stop)` rows — is
biased by **where the bus is in the route**: a bus at the start of the
line has 60 min of ETA ahead, a bus near the end has 5 min. A flat
average across the two is meaningless.

Per snapshot, the bus is somewhere along a segment. Computing its
remaining time to the terminal mixes one *partial* segment (current
position → next stop) with several *full* segments (next stop → final
stop). Averaging these mixed values gives a metric that depends on
sampling geometry rather than on traffic.

We want a metric that is comparable across snapshots and across
vehicles at different points in the route, isolating the time needed
to traverse **only fully-quantised segments** of the line.

## Decision

For each `(source, line_id, vehicle_id)` snapshot, compute:

```
next_stop_eta   = minutes_until_arrival for the smallest-positive-ETA stop
                  on the line in this snapshot
final_stop_eta  = minutes_until_arrival for the line's terminal stop
                  (max stop_order) in this snapshot

segments_remaining = final_stop_order - next_stop_order
eta_to_end         = final_stop_eta  - next_stop_eta
eta_per_segment    = eta_to_end / segments_remaining
```

`eta_to_end` and `eta_per_segment` are the two new metrics exposed by
`int_eta_to_end_of_route`.

- `next_stop_eta` uses the **smallest positive** `minutes_until_arrival`
  on purpose. An `eta = 0` observation means the bus is currently at
  that stop; the *next* target is the smallest positive ETA, which
  keeps the in-progress segment out of the metric.
- The filter `final_stop_eta > next_stop_eta AND final_stop_order > next_stop_order`
  drops buses already at or past the terminal (no full segments
  remain), where the metric is undefined.
- The headline metric for downstream analysis is `eta_per_segment`:
  minutes per full segment, normalised so observations from any bus
  at any position are directly comparable.

## Considered alternatives

1. **Per-stop ETA averaged across all stops.** Take the mean of
   `minutes_until_arrival` over all `(snapshot, vehicle, stop)` rows.
   Rejected: conflates partial and full segments; a bus near the
   terminal contributes a 1-min "ETA" on par with a 60-min one. Highly
   biased by sampling.

2. **Position-normalised ETA: `eta_to_final / (final_stop_order - current_position)`.**
   A plausible framing if we had continuous position. Rejected: we
   don't have continuous position; the only resolution we have is the
   discrete stop list. The "next stop" framing is the closest available
   proxy and avoids the need to invent a position estimate.

3. **Use the raw `minutes_until_arrival` to the terminal stop, unadjusted.**
   Rejected: the snapshot's `minutes_until_arrival` to the final stop
   already includes the in-progress segment from the bus's current
   position to the next stop. Two buses at the same "real" speed but
   one approaching stop N and the other approaching stop N+1 would
   show different `eta_to_final` values purely because of where they
   happen to be on the route.

4. **Hand-rolled incremental position estimate from GPS coordinates.**
   Rejected: vehicle GPS is sampled at the snapshot's GPS fix time,
   not at every stop, and a per-snapshot linear interpolation would
   be fragile. The discrete stop-list framing is the natural grain
   of the data.

The chosen approach was preferred because it (a) is exact under the
data we actually have, (b) eliminates the partial-segment bias without
inventing an interpolation, (c) decomposes naturally into
`eta_per_segment`, which is the most-comparable metric for downstream
"how slow is this route right now?" questions, and (d) is expressible
as a single dbt model on top of existing intermediates.

## Consequences

**Positive**

- `eta_per_segment` is comparable across vehicles, lines, hours of day,
  and external conditions (weather, accidents), independent of where
  the bus is in the route.
- A single intermediate provides both the raw full-segment total
  (`eta_to_end`) and the normalised rate (`eta_per_segment`); downstream
  consumers can pick whichever fits the question.
- The model is built entirely on existing intermediates
  (`int_previsao_calculated`, `int_line_stops`); no new ingestion
  required.

**Negative**

- The metric is undefined for buses already at the terminal (~8.6% of
  snapshots in current data); they are filtered out. Acceptable
  because their "remaining ETA" is by definition zero and including
  them would skew the metric toward 0.
- The metric inherits the noise of `minutes_until_arrival` (stale
  `ta` timestamps, etc. — see ADR-0004). Downstream consumers
  concerned with freshness should join on `blob_timestamp` and
  filter.
- Buses that have *just departed* the terminal can have artificially
  small `eta_per_segment` (only one full segment visible). In
  practice, these are rare and the global metric is robust; if
  needed, a downstream filter `segments_remaining >= 2` could be
  added.

## Validation

Built on top of the validated `int_line_stops` (Pearson r > 0.99 vs.
SPTrans website per ADR-0001) and `int_previsao_calculated` (range
[0, 720) per ADR-0003). Smoke checks on first build:

| Metric | Value |
|--------|-------|
| Vehicle-snapshots in (raw) | 147,816 |
| Vehicle-snapshots out (after filters) | 135,122 (91.4%) |
| `eta_per_segment` median | 1.67 min/segment |
| `eta_per_segment` mean | 2.49 min/segment |
| `eta_per_segment` p99 | ~12 min/segment |

The 8.6% drop matches the rate of "bus at terminal" snapshots observed
during dev. The median of ~1.7 min/segment is consistent with a
roughly 1-2 km/h average urban segment traversal in São Paulo traffic.
Sanity-checked by sampling individual rows (`sandbox/validate_eta_to_end_logic.py`).

To re-run validation:

```
python sandbox/validate_eta_to_end_logic.py
```

Expect the kept-rate to stay near 91% and the median near 1-2 min/segment.
A drop in kept-rate or a sudden jump in `eta_per_segment` median would
signal either an upstream regression or a real change in SPTrans'
prediction window.
