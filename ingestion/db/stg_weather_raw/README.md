# Weather Blob Ingestion Script

Fetches weather blobs from Azure Blob Storage and loads them into the `staging.stg_weather_raw` table.

## Usage

```bash
python -m db.stg_weather_raw.main
```

## Workflow

1. Lists all blobs matching prefix `weather_` in Azure storage
2. Identifies earliest blob timestamp for incremental loading
3. Downloads only new blobs (those with timestamps >= earliest)
4. Inserts into PostgreSQL staging table as JSONB
5. Verifies row count and reports errors

## Output

- Console output showing progress per blob
- Summary of inserted/skipped blobs
- Total row count in staging table
