# dbt Data Transformation Plan - SP Traffic Gold Layer

## Context
Ingestion is complete with daily 15-minute snapshots of bus positions and weather in PostgreSQL `staging` schema (one table per source, JSONB payloads). Building a dbt project for medallion architecture transformation to support frontend map visualization showing segment-level performance vs. historical averages with weather context.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    STAGING LAYER (PostgreSQL)               │
│  ┌──────────────────┬──────────────────┬──────────────────┐ │
│  │ bus_snapshots    │ weather_snapshots │ loaded_at       │ │
│  │ JSONB payload    │ JSONB payload    │ ingestion time   │ │
│  └──────────────────┴──────────────────┴──────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              ↓ (dbt bronze)
┌─────────────────────────────────────────────────────────────┐
│                    BRONZE LAYER                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ staging_bus_snapshots                                  │ │
│  │ staging_weather_snapshots                              │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              ↓ (dbt silver)
┌─────────────────────────────────────────────────────────────┐
│                    SILVER LAYER                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ bus_snapshots_enriched                                 │ │
│  │   - Extract JSONB → proper columns                     │ │
│  │   - Infer stop order per route from ETAs               │ │
│  │   - Create segment_id = route_id + stop_index         │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ weather_snapshots_enriched                             │ │
│  │   - Extract JSONB → proper columns                     │ │
│  │   - WMO code → severity base score                     │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              ↓ (dbt gold)
┌─────────────────────────────────────────────────────────────┐
│                    GOLD LAYER                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ route_segment_performance                              │ │
│  │   - avg_segment_duration (arithmetic mean)             │ │
│  │   - median_segment_duration                            │ │
│  │   - weather_severity_score                             │ │
│  │   - is_above_average                                   │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## dbt Project Structure

```
transformation/
├── dbt_project.yml
├── models/
│   ├── staging/          # Read-only, mirrors PostgreSQL staging schema
│   │   ├── bus_snapshots.sql
│   │   └── weather_snapshots.sql
│   ├── bronze/           # JSONB extraction (read-only transformations)
│   │   ├── bus_snapshots_bronze.sql
│   │   └── weather_snapshots_bronze.sql
│   ├── silver/           # Data standardization and inference
│   │   ├── bus_snapshots_silver.sql          # Stop order inference
│   │   └── weather_snapshots_silver.sql      # WMO code mapping
│   └── gold/             # Business metrics
│       └── route_segment_performance.sql     # Final analytics table
├── tests/                # Minimal data quality tests
│   ├── staging/
│   ├── bronze/
│   ├── silver/
│   └── gold/
└── macros/               # Reusable logic (if needed)
```

## Model Specifications

### Bronze Layer
**Purpose**: Extract JSONB fields into proper columns, no computation.

`models/bronze/bus_snapshots_bronze.sql`:
- `file_name` (text): snapshot identifier from filename
- `loaded_at` (timestamp): ingestion timestamp
- `snapshot_timestamp` (timestamp): extracted from JSONB payload
- `route_id` (integer), `bus_id` (integer), `stop_id` (integer)
- `x_coord`, `y_coord` (numeric)
- `eta_seconds` (numeric): arrival time converted to seconds from snapshot

`models/bronze/weather_snapshots_bronze.sql`:
- `file_name` (text)
- `loaded_at` (timestamp)
- `snapshot_timestamp` (timestamp)
- `x_coord`, `y_coord` (numeric)
- `weather_code` (integer): WMO code
- `precipitation_mm` (numeric)
- `temperature_celsius` (numeric)

### Silver Layer
**Purpose**: Data standardization, stop order inference.

`models/silver/bus_snapshots_silver.sql`:
- All bronze columns + derived:
- `route_name` (text): inferred from route_id
- `stop_index` (integer): position in route (1 = first stop)
- `segment_id` (text): `route_id || '_' || stop_index`
- `eta_difference_seconds` (numeric): time to next stop on same bus

Stop order inference logic:
```sql
-- For each snapshot, order stops by ETA within each route
WITH ordered_stops AS (
  SELECT *,
         ROW_NUMBER() OVER (
           PARTITION BY route_id 
           ORDER BY eta_seconds
         ) as stop_index
  FROM staging_bus_snapshots_bronze
)
SELECT * FROM ordered_stops;
```

`models/silver/weather_snapshots_silver.sql`:
- All bronze columns + derived:
- `weather_severity_base` (integer): WMO code mapped to severity
  - sunny (0,1,2,3): 1
  - partly cloudy (45,46,47,48): 2
  - clear (80,81,82,85): 1
  - fog (96-99): 3
  - drizzle (55-57): 2
  - rain (60-69): 4
  - snow (70-79): 5
  - thunderstorm (80+): 5

### Gold Layer
**Purpose**: Business metrics and analytics.

`models/gold/route_segment_performance.sql`:
```sql
SELECT 
  route_id,
  segment_id,
  snapshot_timestamp,
  -- Duration metrics
  AVG(eta_difference_seconds) as avg_segment_duration,
  MEDIAN(eta_difference_seconds) as median_segment_duration,
  COUNT(*) as bus_count,
  
  -- Weather severity (weather code base + precipitation modifier)
  MAX(weather_severity_base) as weather_severity_score,
  
  -- Comparison to historical average
  AVG(eta_difference_seconds) OVER (
    PARTITION BY route_id, segment_id 
    ORDER BY snapshot_timestamp 
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  ) as running_avg_duration,
  CASE WHEN eta_difference_seconds > running_avg_duration THEN true ELSE false END as is_above_average

FROM staging_bus_snapshots_silver
JOIN staging_weather_snapshots_silver 
  ON snapshots.snapshot_timestamp = weather.snapshot_timestamp
GROUP BY route_id, segment_id, snapshot_timestamp;
```

## Development Phases (Incremental)

### Phase 1: Bronze Layer (Week 1)
- Initialize dbt project
- Create staging models (read-only views of PostgreSQL tables)
- Create bronze extraction models
- Add minimal tests (row counts, null checks)
- Validate with `dbt run`

### Phase 2: Silver Layer (Week 2)
- Implement stop order inference logic
- Add WMO code severity mapping
- Test segment ordering correctness
- Validate weather code mappings

### Phase 3: Gold Layer (Week 3)
- Create route_segment_performance model
- Implement running average calculation
- Add is_above_average flag
- Final validation against frontend requirements

## Key Decisions Made

1. **Segment definition**: `route_id` + `stop_index` (inferred from ETA ordering)
2. **Weather severity**: WMO code base score + precipitation modifier
3. **Temporal resolution**: 15-minute snapshots aligned between bus and weather data
4. **Aggregation method**: Arithmetic mean + median for segment durations
5. **Average baseline**: Overall historical average (can add stratified later)
6. **Test strategy**: Minimal tests initially, expand as needed

## Unresolved Questions

- [ ] Confirm WMO code severity mapping accuracy with domain experts
- [ ] Decide on running vs. rolling window for "historical average"
- [ ] Handle edge cases: routes with <2 stops, missing weather data
- [ ] Frontend date/time filtering behavior (exact timestamp vs. date-only)
