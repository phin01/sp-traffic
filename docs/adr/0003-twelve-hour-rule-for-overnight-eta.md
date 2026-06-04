# ADR-0003: Overnight ETA adjustment uses a 12-hour rule

- **Status:** Accepted
- **Date:** 2026-06-04
- **Scope:** `get_prediction_timestamp_utc` macro and its callers in
  `int_previsao_calculated`.

## Context

Olho Vivo's `t` field gives a predicted bus arrival time as `HH:MM` only —
no date. After we attach a calendar date with
`get_same_day_prediction_utc` (using the snapshot/blob timestamp as the
reference, see ADR-0002), the result *usually* sits within a few minutes of
the reference. Two edge cases break this:

1. **Snapshot just before midnight, ETA just after midnight.** Reference =
   `23:55 BR`, ETA string = `00:05`. Same-day attachment yields an ETA that
   is ~24h in the past instead of 10 minutes in the future.
2. **Snapshot just after midnight, ETA was actually from yesterday.** Bus
   was delayed; reference = `00:05 BR`, ETA string = `23:55`. Same-day
   attachment yields an ETA ~24h in the future instead of 10 minutes ago.

We need a deterministic rule to add or subtract a day in each case.

## Decision

After computing the same-day UTC prediction timestamp, apply a **12-hour
rule**:

```sql
-- get_prediction_timestamp_utc(prediction, reference)
case
    when prediction <  reference - interval '12 hours' then prediction + interval '1 day'
    when prediction >  reference + interval '12 hours' then prediction - interval '1 day'
    else prediction
end
```

If the same-day prediction is more than 12 hours behind the reference, it
belongs to *tomorrow*. If it is more than 12 hours ahead, it belongs to
*yesterday*. Otherwise it is left as-is.

## Considered alternatives

- **Trust the snapshot timestamp's calendar date unconditionally.** Rejected
  — fails for the midnight cases above.
- **Compare `HH:MM` to the reference's `HH:MM` and roll the date manually.**
  Rejected — duplicates timezone math that the same-day macro already does
  correctly, and is harder to reason about across DST.
- **Skip rows where the gap exceeds some threshold.** Rejected — silently
  loses real data and pushes the problem downstream.

## Assumption being made

**No legitimate Olho Vivo ETA exceeds 12 hours.** Empirically the longest
routes we have observed take 2–3 hours to traverse, and the API only returns
predictions for vehicles already in service. The 12-hour threshold leaves a
~4× safety margin.

If SPTrans ever ships longer-horizon predictions (e.g. "next bus in 14
hours" for an end-of-day stop), this macro will flip them by a day. We
accept that risk because:

- It has not happened in any data captured to date.
- The downstream `minutes_until_arrival` check (`>= 0 and < 720`) in
  `int_previsao_calculated.yml` would fail loudly if it did, surfacing the
  regression rather than silently corrupting data.

## Consequences

**Positive**

- All overnight cases handled symmetrically with a single conditional.
- Logic is self-contained in one macro, easy to audit.

**Negative**

- The 720-minute / 12-hour assumption is invisible at call sites; anyone
  reusing this macro for a different data source must re-validate it.
- A bus genuinely delayed by 13+ hours would be misclassified. Possible but
  vanishingly rare in São Paulo bus traffic.

## Related

- Depends on ADR-0002 (UTC storage) — the 12-hour comparison is meaningful
  only if both sides are in the same timezone.
- Consumed by ADR-0004 (dual-ETA fallback), which checks the resulting ETA
  for negativity to decide whether to fall back.
