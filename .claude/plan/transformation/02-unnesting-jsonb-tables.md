# Context

Raw data for this project is being saved from blob storage into a PostgreSQL database. 
All data transformation should be performed in dbt, using the sptraffic-transform project in the project's /transformation folder

## Tables 

The following tables contain the necessary data for the project:

- `staging.stg_previsao_raw`
- `staging.stg_weather_raw`

## Table schema

All tables follow the same schema

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| source | TEXT | NOT NULL, UNIQUE | Blob filename (e.g., "weather/previsao_2026-05-24T14:30:00.json") |
| data | JSONB | NOT NULL | Full nested API payload, from Open Meteo or Olho Vivo |
| loaded_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | Ingestion timestamp |

## Example `data` payload

### `staging.stg_previsao_raw` Table

- @.claude/plan/transformation/references/data_staging_stg_previsao_raw.txt

### `staging.stg_weather_raw` Table

- @.claude/plan/transformation/references/data_staging_stg_weather_raw.txt

## Implementation Steps

- Create a sources.yml file to ingest the staging tables.
- Define a strategy for un-nesting the JSONB column for each staging table, using the example data payload files as a reference. 
- Save new tables with the unnested JSON data in the `stg` schema. 
- Data should be materialized as incremental tables using the `loaded_at` column as an ingestion criteria. 