"""Fetch bus stops from Azure Blob Storage and insert into PostgreSQL."""

import os
from sqlalchemy import create_engine, text
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv, find_dotenv
import json
from utils.logging import get_logger


# Load environment variables from .env file at project root
load_dotenv(dotenv_path=find_dotenv())

# Configuration
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME')
AZURE_STORAGE_KEY = os.getenv('AZURE_STORAGE_KEY')
AZURE_CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME')

# Database connection
engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    pool_pre_ping=True,
)


def fetch_latest_blob() -> tuple[list[dict], str] | None:
    """Fetch latest bus stops data from Azure Blob Storage.

    Returns:
        Tuple of (list of stop records, filename) or None if no JSON files found.
    """
    print("Fetching latest bus stops data from Azure Blob Storage...")

    # Connect to Azure storage
    client = BlobServiceClient.from_connection_string(AZURE_STORAGE_KEY)
    container_client = client.get_container_client(AZURE_CONTAINER_NAME)

    # List all blobs, filter for .json files only
    try:
        blobs = list(container_client.list_blobs())
    except Exception as e:
        print(f"Error listing blobs in Azure storage: {e}")
        return None

    if not blobs:
        print("No blobs found in container")
        return None

    # Filter for .json files and sort by last_modified timestamp
    json_blobs = [b for b in blobs if b.name.endswith('.json')]

    if not json_blobs:
        print("No JSON files found in container")
        return None

    # Sort by last_modified (newest first)
    json_blobs.sort(key=lambda b: b.last_modified, reverse=True)
    latest_blob = json_blobs[0]

    print(f"Found {len(json_blobs)} JSON files. Using latest: {latest_blob.name}")

    # Download blob content using stream method (v12+ API)
    try:
        blob_client = container_client.get_blob_client(latest_blob.name)
        data = json.loads(blob_client.download_blob().read().decode())
    except Exception as e:
        print(f"Error downloading blob: {e}")
        return None

    # Extract bus stops from JSON structure
    stops = extract_stops(data)
    print(f"Extracted {len(stops)} bus stops")

    return stops, latest_blob.name


def extract_stops(data: list[dict]) -> list[dict]:
    """Extract bus stop records from the nested JSON structure.

    The API returns an array where each item has:
        - line_id: bus line identifier
        - ps: array of stop objects with cp, np, py, px fields

    Returns:
        List of stop records with lowercase keys (cp, np, py, px, line_id).
    """
    stops = []

    for item in data:
        if 'ps' not in item or not isinstance(item['ps'], list):
            continue

        line_id = str(item.get('line_id', ''))

        for stop in item['ps']:
            # Build record with lowercase keys as per spec
            stop_record = {
                'cp': int(stop.get('cp', 0)),
                'np': str(stop.get('np', '')),
                'py': float(stop.get('py', 0)),
                'px': float(stop.get('px', 0)),
                'line_id': line_id,
            }
            stops.append(stop_record)

    print(f"Extracted {len(stops)} bus stops from {len(data)} lines")
    return stops


def create_table_if_not_exists():
    """Create staging table if it doesn't exist."""
    query = text("""
        CREATE TABLE IF NOT EXISTS staging.stg_bus_stops (
            cp integer PRIMARY KEY,
            np text,
            py numeric(10, 7),
            px numeric(10, 7),
            line_id text,
            source_file text DEFAULT 'paradas_staging/latest.json',
            loaded_at timestamp with time zone DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_stg_bus_stops_line_id ON staging.stg_bus_stops(line_id);
        CREATE INDEX IF NOT EXISTS idx_stg_bus_stops_py_px ON staging.stg_bus_stops(py, px);
    """)

    with engine.connect() as conn:
        conn.execute(query)
        conn.commit()


def insert_stops(stops: list[dict], source_file: str):
    """Insert bus stops into PostgreSQL with deduplication.

    Deduplicates by cp, keeping first occurrence.
    """
    seen_cps = set()
    unique_stops = []

    for stop in stops:
        if stop['cp'] not in seen_cps:
            seen_cps.add(stop['cp'])
            unique_stops.append(stop)

    print(f"Unique stops after deduplication: {len(unique_stops)}")

    # Insert all stops in bulk
    insert_query = text("""
        INSERT INTO staging.stg_bus_stops (cp, np, py, px, line_id, source_file, loaded_at)
        VALUES (:cp, :np, :py, :px, :line_id, :source_file, NOW())
    """)

    with engine.connect() as conn:
        for stop in unique_stops:
            params = {
                'cp': stop['cp'],
                'np': stop['np'],
                'py': stop['py'],
                'px': stop['px'],
                'line_id': stop['line_id'],
                'source_file': source_file,
            }
            conn.execute(insert_query, params)

        conn.commit()

    print(f"Inserted {len(unique_stops)} records")


def deduplicate_stops():
    """Remove duplicates by cp, keeping oldest record based on loaded_at."""
    # Delete rows where same cp has later loaded_at timestamp
    delete_query = text("""
        DELETE FROM staging.stg_bus_stops s1
        USING staging.stg_bus_stops s2
        WHERE s1.cp = s2.cp
          AND s1.loaded_at < s2.loaded_at
    """)

    with engine.connect() as conn:
        deleted_count = conn.execute(delete_query).rowcount
        conn.commit()

    print(f"Removed {deleted_count} duplicate records")


def verify_results():
    """Verify the ingestion results."""
    # Check total count
    count_query = text("SELECT COUNT(*) FROM staging.stg_bus_stops")
    with engine.connect() as conn:
        result = conn.execute(count_query).fetchone()[0]

    print(f"\nVerification:")
    print(f"  Total bus stops in table: {result}")

    # Check for duplicates (should return 0 rows)
    dup_query = text("""
        SELECT cp, COUNT(*) as cnt
        FROM staging.stg_bus_stops
        GROUP BY cp
        HAVING COUNT(*) > 1
    """)
    with engine.connect() as conn:
        dups = conn.execute(dup_query).fetchall()

    if dups:
        print(f"  WARNING: Found {len(dups)} duplicate bus stop codes!")
    else:
        print(f"  No duplicates found (as expected)")


def main():
    """Main ingestion workflow."""
    try:
        # Step 1: Create table if not exists
        create_table_if_not_exists()

        # Step 2: Fetch latest blob from Azure
        stops, source_file = fetch_latest_blob()

        if stops is None or not stops:
            print("No bus stop data available. Exiting gracefully.")
            return

        # Step 3: Insert into PostgreSQL
        insert_stops(stops, source_file)

        # Step 4: Deduplicate by cp (keeping oldest loaded_at)
        deduplicate_stops()

        # Step 5: Verify results
        verify_results()

    except Exception as e:
        print(f"Error during ingestion: {e}")
        raise


if __name__ == "__main__":
    logger = get_logger("olho_vivo.paradas_staging")
    try:
        main()
        logger.log_run(succeeded=True)
    except Exception as e:
        logger.log_run(succeeded=False, error_message=str(e))