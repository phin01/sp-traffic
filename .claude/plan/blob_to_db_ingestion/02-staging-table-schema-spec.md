# PostgreSQL Staging Table Schema Specification

## Purpose
Define the staging table structure for raw JSON data ingestion, enabling dbt to handle schema evolution via `json_and_schema` transformation.

## Tables

### stg_previsao_raw
Stores Olho Vivo API schedule data as raw nested JSON.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| source | TEXT | NOT NULL, UNIQUE | Blob filename (e.g., "previsao_2026-05-24T14:30:00.json") |
| data | JSONB | NOT NULL | Full nested API payload from Olho Vivo |
| loaded_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | Ingestion timestamp |

**Indexes:**
```sql
CREATE INDEX idx_stg_previsao_raw_loaded_at ON stg_previsao_raw(loaded_at DESC);
CREATE INDEX idx_stg_previsao_raw_source ON stg_previsao_raw(source);
```

### stg_weather_raw
Stores Open Meteo weather data as raw nested JSON.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| source | TEXT | NOT NULL, UNIQUE | Blob filename (e.g., "weather_2026-05-24T14:30:00.json") |
| data | JSONB | NOT NULL | Full nested API payload from Open Meteo |
| loaded_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | Ingestion timestamp |

**Indexes:**
```sql
CREATE INDEX idx_stg_weather_raw_loaded_at ON stg_weather_raw(loaded_at DESC);
CREATE INDEX idx_stg_weather_raw_source ON stg_weather_raw(source);
```

## Schema Evolution Strategy
- Staging tables store **immutable** raw JSON payloads
- API changes (new fields, structure modifications) do not require ingestion script updates
- dbt models use `json_and_schema` to unnest and transform data
- Gold layer schemas are explicitly defined in dbt
