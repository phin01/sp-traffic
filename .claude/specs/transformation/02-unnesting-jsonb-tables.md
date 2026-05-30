# Implementation Specification: Unnesting JSONB Tables in dbt

## Overview

This specification defines the implementation details for unnesting the `data` JSONB column from staging tables (`staging.stg_previsao_raw` and `staging.stg_weather_raw`) into normalized tables within the `sptraffic_transform` dbt project.

---

## Context

Raw data is ingested from blob storage into PostgreSQL staging tables with a unified schema:
- `source`: TEXT (blob filename)
- `data`: JSONB (full nested API payload)  
- `loaded_at`: TIMESTAMP WITH TIME ZONE (ingestion timestamp)

The goal is to materialize these as incremental tables in the `stg` schema using dbt.

---

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   PostgreSQL │────▶│    dbt Project  │────▶│   Materialized  │────▶│   stg Tables    │
│ (staging)   │     │  (models/)       │     │   Incremental   │     │   (unnested)    │
└─────────────┘     └──────────────────┘     └─────────────────┘     └──────────────────┘
```

**Data Flow:**
1. dbt reads from `staging.stg_previsao_raw` and `staging.stg_weather_raw` (raw JSONB)
2. Unnesting models parse nested API payloads using PostgreSQL's `jsonb_path_query()` or `->>` operators
3. Results are materialized as incremental tables in the `stg` schema

---

## Dependencies

### Required Packages (from requirements.txt)

- `dbt-core` - dbt core engine
- `dbt-postgres` - PostgreSQL adapter for dbt
- `psycopg2-binary` - PostgreSQL driver (used by dbt internally)

---

## File Structure

```
transformation/
├── models/
│   └── stg/
│       ├── __init__.sql          # Source configuration and model definitions
│       ├── previsao_raw.sql      # Unnested bus forecast tables
│       └── weather_raw.sql       # Unnested weather data tables
├── dbt_project.yml               # Project configuration (already exists)
└── profiles.yml                   # Profile configuration (already exists)
```

---

## Implementation Guidelines

### 1. dbt Project Configuration

Update `dbt_project.yml`:

```yaml
name: 'sptraffic_transform'
version: '1.0.0'
profile: 'sptraffic_transform'

model-paths: ["models"]
analysis-paths: ["analyses"]
test-paths: ["tests"]
seed-paths: ["seeds"]
macro-paths: ["macros"]
snapshot-paths: ["snapshots"]

clean-targets:
  - "target"
  - "dbt_packages"

models:
  sptraffic_transform:
    +materialized: incremental
```

### 2. Source Configuration (models/stg/__init__.sql)

Define sources for the staging tables:

```sql
-- models/stg/__init__.sql

{% source staging as staging %}

{{
    source(
        target_schema='staging',
        source_name='staging',
        columns={
            'source': {'name': 'source'},
            'data': {'name': 'data_raw'},  # Keep raw JSONB for reference
            'loaded_at': {'name': 'loaded_at'}
        }
    )
}}
```

### 3. Unnesting Strategy

#### Weather Data Structure (Open Meteo API)

Based on the sample data, weather payloads have this structure:
- Root object with multiple location IDs as keys
- Each location contains `hourly` and `current` objects
- `hourly`: array of hourly readings (time, precipitation, etc.)
- `current`: current conditions snapshot

**Unnesting approach:**
1. Use `jsonb_path_query()` to extract each location ID from the root object
2. For each location, unnest `hourly` arrays into rows
3. Extract `current` weather as a single row per location

#### Bus Forecast Data Structure (Olho Vivo API)

Based on plan context, bus forecast payloads have:
- Root object with line IDs as keys  
- Each line contains schedule data (`HR`, `PS`) arrays

**Unnesting approach:**
1. Use `jsonb_path_query()` to extract each line ID from the root object
2. Unnest `HR` (hourly) and `PS` (periodic) arrays into rows

### 4. Model Definitions

#### Weather Raw Table (models/stg/weather_raw.sql)

```sql
-- models/stg/weather_raw.sql

{{
    config(
        materialized='incremental',
        target_schema='stg',
        unique_key='location_id',
        incremental_strategy='merge',
        increment_by='time',
        timestamp_column_for_increments='loaded_at'
    )
}}

WITH raw_data AS (
    SELECT 
        jsonb_path_extract_array(data::jsonb, '$') AS locations,
        loaded_at
    FROM staging.stg_weather_raw
),
expanded_locations AS (
    SELECT 
        loc.value::text AS location_id,
        loc.data AS location_data,
        loaded_at
    FROM unnested_weather
    CROSS JOIN jsonb_path_each(locations::jsonb, '$') AS loc
)
SELECT 
    location_id,
    -- Current weather conditions
    CAST(location_data->>'current' AS JSONB) AS current_conditions,
    -- Hourly precipitation
    jsonb_path_extract_array(
        location_data->'hourly'->'precipitation',
        '$[*]'
    )::INTEGER[] AS hourly_precipitation_mm,
    -- Hourly timestamps  
    jsonb_path_extract_array(
        location_data->'hourly'->'time',
        '$[*]'
    )::TEXT[] AS hourly_timestamps,
    loaded_at
FROM expanded_locations
```

#### Bus Forecast Raw Table (models/stg/previsao_raw.sql)

```sql
-- models/stg/previsao_raw.sql

{{
    config(
        materialized='incremental',
        target_schema='stg',
        unique_key='line_id',
        incremental_strategy='merge',
        increment_by='time',
        timestamp_column_for_increments='loaded_at'
    )
}}

WITH unnested_forecasts AS (
    SELECT 
        jsonb_path_extract_array(data::jsonb, '$') AS lines,
        loaded_at
    FROM staging.stg_previsao_raw
),
expanded_lines AS (
    SELECT 
        loc.value::text AS line_id,
        loc.data AS line_data,
        loaded_at
    FROM unnested_forecasts
    CROSS JOIN jsonb_path_each(lines::jsonb, '$') AS loc
)
SELECT 
    line_id,
    -- Hourly schedule data
    CAST(line_data->>'HR' AS JSONB) AS hourly_schedule,
    -- Periodic schedule data  
    CAST(line_data->>'PS' AS JSONB) AS periodic_schedule,
    loaded_at
FROM expanded_lines
```

### 5. Incremental Materialization Strategy

For incremental updates using `loaded_at`:

1. **MERGE strategy**: Update existing rows when new data arrives for same location/line
2. **increment_by='time'**: Use `loaded_at` column to determine what's new
3. **unique_key**: Primary identifier (location_id or line_id)

```sql
{% if is_incremental() %}
-- Only insert updates/new records in incremental runs
WHERE loaded_at > (SELECT MAX(loaded_at) FROM {{ this }})
{% endif %}
```

---

## Expected Output Tables

### stg.weather_raw
| Column | Type | Description |
|--------|------|-------------|
| location_id | TEXT | Open Meteo station ID |
| current_conditions | JSONB | Current weather snapshot |
| hourly_precipitation_mm | INTEGER[] | Array of 24-hour precipitation values (mm) |
| hourly_timestamps | TEXT[] | Array of 24 ISO8601 timestamps |
| loaded_at | TIMESTAMP WITH TIME ZONE | Ingestion timestamp |

### stg.previsao_raw  
| Column | Type | Description |
|--------|------|-------------|
| line_id | TEXT | Bus line identifier |
| hourly_schedule | JSONB | Hourly schedule data |
| periodic_schedule | JSONB | Periodic schedule data |
| loaded_at | TIMESTAMP WITH TIME ZONE | Ingestion timestamp |

---

## Testing Strategy

### Unit Tests (dbt tests)

1. **Source validation**: Verify source columns exist and are not null
2. **Data type checks**: Ensure JSONB extractions return expected types
3. **Incremental logic**: Test that incremental strategy correctly identifies new records

```sql
-- models/stg/tests/init.sql

{{ config(materialized='test') }}

SELECT 1 as test_id
UNION ALL
SELECT 2
UNION ALL
SELECT 3
```

---

## Deployment Checklist

- [ ] Create `models/stg/` directory structure
- [ ] Implement source configuration in `__init__.sql`
- [ ] Create weather_raw unnesting model
- [ ] Create previsao_raw unnesting model  
- [ ] Add dbt tests for data validation
- [ ] Run `dbt run --full-refresh` to test initial materialization
- [ ] Run `dbt run` to verify incremental updates work correctly
- [ ] Verify output tables in PostgreSQL stg schema

---

## Verification Steps

1. **Initial load**:
   ```bash
   dbt run --models "stg/weather_raw" --full-refresh
   dbt run --models "stg/previsao_raw" --full-refresh
   ```

2. **Verify table creation**:
   ```sql
   \d stg.weather_raw
   \d stg.previsao_raw
   SELECT COUNT(*) FROM stg.weather_raw;
   SELECT COUNT(*) FROM stg.previsao_raw;
   ```

3. **Incremental update test**:
   - Manually insert new row into staging table with future `loaded_at` timestamp
   - Run: `dbt run --models "stg/weather_raw"`
   - Verify new record appears in output table

---

## Future Enhancements

1. Add schema validation for API response structures
2. Create derived tables with aggregated weather metrics (avg temp, total precip)
3. Build models that join weather data to bus routes
4. Implement caching layer for frequently accessed locations/lines

---

## References

- [dbt Documentation - Incremental Models](https://docs.getdbt.com/docs/building-an-dbt-project/incremental-models)
- [PostgreSQL JSON Functions](https://www.postgresql.org/docs/current/functions-json.html)
- [jsonb_path_query() Reference](https://www.postgresql.org/docs/current/functions-json.html#FUNCTIONS-JSON-PATH)
