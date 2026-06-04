# ADR-0004: Dual ETA computation — blob-primary, snapshot fallback

- **Status:** Accepted
- **Date:** 2026-06-04
- **Scope:** `int_previsao_calculated.minutes_until_arrival`.

## Context

Every Olho Vivo prediction row carries **two timestamps**:

- `blob_timestamp` — parsed from the blob filename
  (`previsao_2026-05-30T08:00:00.json`). This is the moment the ingestion
  script wrote the blob to Azure.
- `snapshot_timestamp` — the `ta` field from the SPTrans response. This is
  the vehicle's GPS fix time, set by the on-board hardware.

We can compute `minutes_until_arrival` from either: predicted arrival minus
blob time, or predicted arrival minus snapshot time. They usually agree to
within seconds. Two failure modes have been observed:

1. **Stale `ta`.** Some vehicles intermittently report old GPS fixes,
   apparently due to on-board communication issues. The snapshot timestamp
   then trails reality by minutes-to-hours and the snapshot-based ETA blows
   up.
2. **Delayed ingestion.** The ingestion script can fall behind (rare, but
   it happens), in which case the blob is written well after the prediction
   was actually fetched, pushing the blob-based ETA into negative territory
   even though the underlying `ta`-based one is fine.

A single canonical `minutes_until_arrival` is needed for everything
downstream.

## Decision

Compute both ETAs. Use the **blob-based ETA by default**, and fall back to
the snapshot-based ETA only when the blob-based one is negative.

```sql
case
    when blob_minutes_until_arrival < 0 then snapshot_minutes_until_arrival
    else blob_minutes_until_arrival
end as minutes_until_arrival
```

## Rationale

- The **blob timestamp is monotonic and trustworthy**: it is set by our own
  ingestion script, runs on infrastructure we control, and cannot drift
  silently.
- The **snapshot timestamp `ta` is the truer "moment the prediction was
  valid"** when it is fresh — but we have no way to detect staleness
  cheaply on a per-row basis.
- A negative blob-based ETA is a clean, unambiguous signal that the
  ingestion was late relative to the prediction; in that one case the `ta`
  value is more trustworthy than the blob.

## Considered alternatives

- **Snapshot-primary, blob fallback.** Rejected — would silently propagate
  the "stale `ta`" failure mode for every affected row, which is the more
  common and harder-to-detect problem.
- **Average the two.** Rejected — averages a trustworthy value with a
  potentially garbage one.
- **Take the minimum / maximum.** Rejected — same problem; no semantics.
- **Drop rows where the two disagree by more than some tolerance.**
  Rejected — would discard legitimate data and require choosing a tolerance.

## Consequences

**Positive**

- Both failure modes (stale `ta`, delayed ingestion) are handled by a
  one-line conditional.
- The downstream `int_previsao_calculated.yml` test
  (`>= 0 and minutes_until_arrival < 720`) acts as a tripwire: if both
  computations fail simultaneously, the test fires.

**Negative**

- A persistently-stale `ta` whose blob-based ETA still happens to be
  positive will silently use the stale value. There is no per-row staleness
  check; we only detect the case where blob disagrees badly enough to go
  negative.
- The two raw computations (`blob_minutes_until_arrival`,
  `snapshot_minutes_until_arrival`) live only in internal CTEs and are not
  exposed in the final model. If a future debugging need requires them,
  re-add them deliberately — do not let them creep back into the public
  surface area, since their presence invites consumers to use the wrong
  value.

## Related

- Depends on ADR-0002 (UTC storage) and ADR-0003 (12-hour overnight rule),
  which together make both ETAs comparable in the first place.
