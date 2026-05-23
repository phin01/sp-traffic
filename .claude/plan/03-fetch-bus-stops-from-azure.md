# Plan: Fetch Bus Stops from Azure Blob Storage and Insert into PostgreSQL

## Context
The `previsao_staging` script fetches bus line schedule data from Olho Vivo API and saves it to Azure Blob Storage. Now we need a complementary script that retrieves the latest bus stop data from Azure Blob Storage and inserts it into PostgreSQL for use by downstream transformations (dbt) and analytics.

## Critical Files
- `ingestion/olho_vivo/previsao_staging/main.py` - Existing script pattern to reference
- `ingestion/olho_vivo/paradas_staging/` - Target folder for downloaded JSON files
- PostgreSQL database table `staging.stg_bus_stops`

## Implementation Approach

### Step 1: Create New Script
Create `ingestion/olho_vivo/paradas_staging/main.py` following a similar structure as `previsao_staging/main.py`:

**Step 1.1: Environment Setup**
- Load `.env` using existing pattern (`find_dotenv()`)
- Import Azure Blob Storage, SQLAlchemy, requests libraries
- Configure database connection string from env vars

**Step 1.2: Fetch Latest File from Azure Blob Storage**
- Use `BlobServiceClient` to connect to storage account
- List blobs in `previsao/` container and find the most recent `.json` file
- Download the blob content using `download_blob()`
- Keep the file in memory for processing

**Step 1.3: Parse JSON Data**
- Load JSON file into Python dict/list structure
- Extract all bus stops from nested `ps` arrays under each line item
- Build a list of stop records with fields: `cp`, `np`, `py`, `px` (and any other relevant fields)

**Step 1.4: Insert into PostgreSQL**
- Insert data to existing `staging.stg_bus_stops` table
- Use parameterized queries to prevent SQL injection
- Batch inserts for performance (e.g., insert in chunks of 500-1000 rows)
- Log success/failure counts
- Make sure all bus stops in the table are unique (no duplicates), by removing any duplicate records after insert based on `cp` key, keeping the older ones based on `loaded_at` timestamp

### Step 2: Database Schema Design
Table `staging.stg_bus_stops` follows the following schema, with columns matching the JSON structure:
```sql
CREATE TABLE IF NOT EXISTS staging.stg_bus_stops (
    cp integer,              -- Bus stop code (primary key candidate)
    np text,                 -- Bus stop name
    py numeric(10, 7),       -- Y coordinate (latitude)
    px numeric(10, 7),       -- X coordinate (longitude)
    line_id text,            -- Associated bus line ID
    source_file text,        -- Source filename for audit trail
    loaded_at timestamp with time zone DEFAULT NOW()
);
```

## Verification Steps
- Run the script manually: `python ingestion/olho_vivo/paradas_staging/main.py`
- Check that JSON file is loaded to memory properly
- Verify rows inserted into PostgreSQL using psql or Python query
- Guarantee no duplicate bus stops are present in `staging.stg_bus_stops` table after script execution
- In case JSON file has 0 bus stops, log as a failed execution
