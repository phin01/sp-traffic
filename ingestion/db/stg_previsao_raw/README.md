# Previsao Blob Ingestion Script

Fetches previsao (schedule) blobs from Azure Blob Storage and loads them into the `staging.stg_previsao_raw` table.

## Usage

```bash
python -m db.stg_previsao_raw.main
```

## Workflow

1. Lists all blobs matching prefix `previsao_` in Azure storage
2. Identifies earliest blob timestamp for incremental loading
3. Downloads only new blobs (those with timestamps >= earliest)
4. Inserts into PostgreSQL staging table as JSONB
5. Verifies row count and reports errors

## Output

- Console output showing progress per blob
- Summary of inserted/skipped blobs
- Total row count in staging table
