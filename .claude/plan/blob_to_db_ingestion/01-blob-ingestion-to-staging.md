# Blob Ingestion to PostgreSQL Staging

## Context
The ingestion scripts (`previsao_staging` and `weather_staging`) currently fetch data from APIs and save raw JSON payloads to Azure Blob Storage. The next step is to load these blobs into PostgreSQL staging tables for downstream dbt transformation. 

Schema drift is a primary concern — we want to avoid unnesting JSON in Python code so that API changes don't break ingestion scripts. Instead, the full nested payload should be stored as-is and handled by dbt via `json_and_schema`.

## Recommended Approach

### 1. Shared Blob Utility (utils/cloud.py)
Extend `CloudStorage` class with read operations:
- `list_blobs_by_source(source_prefix: str) -> list[BlobInfo]`: Lists blobs matching a source prefix, filtered by earliest timestamp
- `get_blob_timestamps() -> dict[str, datetime]`: Returns blob metadata including last_modified

### 2. Ingestion Scripts (db/stg_previsao_raw/main.py, db/stg_weather_raw/main.py)
Each script:
1. Lists blobs in Azure using the shared utility
2. Filters by earliest `loaded_at` timestamp for incremental loading
3. Downloads only new blobs
4. Inserts into staging table with blob filename as `source` column

### 3. PostgreSQL Staging Tables
```sql
CREATE TABLE stg_previsao_raw (
    source TEXT,           -- e.g., "previsao_2026-05-24T14:30:00.json"
    data JSONB,            -- Full nested API payload
    loaded_at TIMESTAMP    -- NOW() on insert
);

CREATE TABLE stg_weather_raw (
    source TEXT,           -- e.g., "weather_2026-05-24T14:30:00.json"
    data JSONB,            -- Full nested API payload
    loaded_at TIMESTAMP
);
```

## Critical Files to Modify
- `utils/cloud.py` (extend with blob listing methods)
- `db/stg_previsao_raw/main.py` (new file)
- `db/stg_weather_raw/main.py` (new file)

## Verification
1. Run db/stg_previsao_raw/main.py → verify rows in `stg_previsao_raw` with blob filenames
2. Run db/stg_weather_raw/main.py → verify rows in `stg_weather_raw` with blob filenames
3. Re-run ingestion → confirm only new blobs are loaded (incrementality works)
