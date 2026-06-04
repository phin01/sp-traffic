# ADR-0002: All warehouse timestamps in UTC; local BR time only at the API boundary

- **Status:** Accepted
- **Date:** 2026-06-04
- **Scope:** All `stg_*` and `int_*` models in `transformation/`, and the
  `get_same_day_prediction_utc` macro in `transformation/macros/`.

## Context

SP-Traffic ingests two kinds of timestamps from external APIs:

- **Wall-clock timestamps** — e.g. `ta` (vehicle GPS fix time) from Olho Vivo,
  `time` from Open-Meteo. These are absolute moments in time.
- **Loose time strings** — Olho Vivo's `t` field, the predicted arrival time
  of a bus at a stop, is given as a bare `HH:MM` string with no date and no
  timezone. By inspection these strings are São Paulo local time
  (`America/Sao_Paulo`).

The warehouse needs to do arithmetic between these — e.g. "how many minutes
until the bus arrives?" — and they cannot be compared until both sides
agree on a calendar date and a timezone.

## Decision

1. **All timestamps stored in warehouse tables are UTC.** Every absolute
   timestamp (`blob_timestamp`, `snapshot_timestamp`, `loaded_at`,
   `snapshot_time`, every `*_prediction_timestamp_utc`) is UTC, no
   exceptions.
2. **Local São Paulo time appears only as raw `HH:MM` strings inside
   `prediction_time` (column) and `snapshot_hour` (column).** These are
   API-provided strings preserved verbatim from the source; they are never
   used directly in arithmetic.
3. **The conversion happens in exactly one place**: the
   `get_same_day_prediction_utc` macro. It takes a UTC reference timestamp
   and a local `HH:MM` string, locks in the correct São Paulo calendar date
   from the reference, then converts the resulting BR-local timestamp back
   to UTC.

```sql
-- get_same_day_prediction_utc(reference_timestamp, prediction_time)
(( reference at time zone 'UTC' at time zone 'America/Sao_Paulo')::date
   || ' ' || prediction_time
)::timestamp at time zone 'America/Sao_Paulo' at time zone 'UTC'
```

## Consequences

**Positive**

- One unambiguous timezone in every table; downstream consumers never have
  to ask.
- DST transitions (which Brazil currently does not observe, but might in the
  future) are handled by Postgres at the boundary, not in app code.
- Time-zone bugs are confined to one macro.

**Negative**

- Anyone displaying timestamps to a São Paulo user must remember to convert
  to `America/Sao_Paulo` at the display layer.
- The double-cast incantation
  (`at time zone 'UTC' at time zone 'America/Sao_Paulo'`) is non-obvious; it
  forces Postgres to first treat the value as UTC and then re-anchor it as
  BR local — without that, the resulting `::date` can land on the wrong
  calendar day.

## Related

- ADR-0003 builds on this: once both timestamps are UTC, the overnight
  adjustment can use a 12-hour rule.
