# SP-Traffic Domain Glossary

## Project Overview
SP-Traffic analyzes how weather conditions and traffic accidents impact bus route delays in São Paulo, Brazil. The system ingests data from multiple sources into PostgreSQL staging tables for downstream transformation (dbt) and analytics.

## Language

**Bus Line (`linha`)**
- Definition: {A specific bus route operating between two terminals
- Identifier: `line_id` (string code from SPTrans)
- **Directionality**: `line_id` is per-direction — the same physical route
  uses two distinct ids, one for A→B and one for B→A. No further direction
  flag is needed in derived models.
- Storage: PostgreSQL table `staging.stg_lines`
- Count: ~40 active lines in system

**Bus Stop (`parada`)**
- Definition: Physical location where passengers board/alight buses
- Unique Code: `cp` (integer, primary key for deduplication)
- Coordinates: `py` (latitude), `px` (longitude)
- Storage: PostgreSQL table `staging.stg_bus_stops`
- Also used as the **reference point for weather queries** — for each grid
  cell, one stop inside that cell is picked and its coordinates are sent to
  Open-Meteo. Its `cp` ends up as `location_id` in `stg_weather_raw`.

**Vehicle (`veículo`)**
- Definition: A single physical bus
- Identifier: `vehicle_id` (string code from SPTrans, the value of the `p`
  field in the Olho Vivo response)
- Reported with: GPS coordinates (`vehicle_longitude`, `vehicle_latitude`),
  accessibility flag (`is_accessible`), and ETAs to every stop it is
  currently approaching on its line
- A vehicle appears in many snapshots, on one `line_id` at a time

**Stop Order (`stop_order`)**
- Definition: 1-indexed position of a stop along its directional line, from
  first to last stop in the trip direction.
- Source: Inferred from sequential ETAs observed in vehicle snapshots — there
  is no SPTrans endpoint that exposes it directly.
- Storage: `int.int_line_stops` (one row per `(line_id, stop_id)`).
- Method: pairwise voting on snapshot ETAs — see
  `docs/adr/0001-bus-stop-order-via-pairwise-voting.md`.
- Range: lines typically have 30–80 stops.

**Snapshot (`source`)**
- Definition: One capture of the Olho Vivo (or Open-Meteo) API, stored as a
  single JSON blob in Azure and unnested into staging.
- Identifier: `source` column — the blob filename, e.g.
  `previsao_2026-05-30T08:00:00.json`. Acts as the snapshot primary key.
- Two timestamps are attached to every prediction row in a snapshot:
  - `blob_timestamp` — when our ingestion script wrote the blob (UTC,
    parsed from the filename). Monotonic and trustworthy.
  - `snapshot_timestamp` — the `ta` field from SPTrans, i.e. the vehicle's
    GPS fix time (UTC). Closer to reality when fresh, but can go stale due
    to on-board communication issues.
  See ADR-0004 for which one is used when.

**Prediction time (`prediction_time` / `snapshot_hour`)**
- Definition: The SPTrans `t` (per-vehicle) or `hr` (per-snapshot) field —
  a bare `HH:MM` string with no date and no timezone.
- Convention: these strings are São Paulo local time
  (`America/Sao_Paulo`), the only place local BR time appears in the
  warehouse. They are converted to a UTC timestamp via the
  `get_same_day_prediction_utc` and `get_prediction_timestamp_utc` macros
  before any arithmetic — see ADR-0002 and ADR-0003.

**ETA (`minutes_until_arrival`)**
- Definition: Minutes from the snapshot's capture time until the bus is
  predicted to arrive at a stop.
- Storage: `int_previsao_calculated.minutes_until_arrival` (the only ETA
  column exposed; the dual blob/snapshot computation is internal to the
  model). See ADR-0004.
- Range: must satisfy `0 <= minutes_until_arrival < 720` (12 h cap from
  ADR-0003).

**Grid Cell (`célula`)**
- Definition: Spatial bucket used to cluster bus stops for weather queries
- Size: 0.025° × 0.025° (approximately 8 km², ~3.5 km radius)
- Coordinate System: São Paulo bounding box
  - Latitude: -23.8265890 to -23.4891720
  - Longitude: -46.7636250 to -46.3830080
- Count: ~64 unique cells (reduces 400 stops to 64 API calls)
- For each cell, **one bus stop inside the cell is chosen as the
  representative location** for the weather query; that stop's `cp` is what
  appears as `location_id` in `stg_weather_raw`.

**Grid Key (`grid_key`)**
- Definition: Unique identifier for a grid cell in format `row_col`
- Example: `"10_14"` represents row 10, column 14
- Used as primary key in weather staging table

## Conventions

- **All warehouse timestamps are UTC.** Local São Paulo time appears only
  inside `prediction_time` / `snapshot_hour` raw strings; everything else
  is UTC. See ADR-0002.
- **`source` is the snapshot identifier** everywhere — it is the blob
  filename for both Olho Vivo and Open-Meteo data.
- **dbt schemas**: staging models land in `stg.`, intermediate models land
  in `int.` (configured in `transformation/dbt_project.yml` and
  `transformation/macros/generate_schema_name.sql`).