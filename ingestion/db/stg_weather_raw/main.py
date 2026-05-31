"""Fetch weather blobs from Azure Storage and insert into PostgreSQL staging table."""

import json
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv
from utils.cloud import CloudStorage, BlobInfo


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

def get_latest_load_timestamp() -> datetime:
    """Fetch the latest load timestamp from the staging table."""

    query = text(
        "SELECT MAX(loaded_at) FROM staging.stg_weather_raw"
    )

    with engine.connect() as conn:
        result = conn.execute(query).fetchone()
        return result[0] if result[0] else datetime.min


def main():
    """Main ingestion workflow for weather data."""
    print("Starting weather blob ingestion...")

    # Step 1: Verify database connection
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            row = result.fetchone()
            print(f"Database connection verified (row: {row})")
    except Exception as e:
        print(f"Database connection failed: {e}")
        raise

    # Step 2: Initialize cloud storage client
    if not AZURE_STORAGE_KEY or not AZURE_CONTAINER_NAME:
        raise ValueError("Azure credentials missing. Check .env file.")
    storage = CloudStorage(container_name=AZURE_CONTAINER_NAME)

    # Step 3: List all weather blobs from Azure Storage
    print("\nListing weather blobs in Azure Blob Storage...")
    blob_prefixes = ["openmeteo/weather/weather_"]
    blobs = storage.list_blobs_by_source(blob_prefixes)
    print(f"Found {len(blobs)} weather blobs")

    if not blobs:
        print("No weather blobs found. Exiting gracefully.")
        return

    # Step 4: Get latest load timestamp for incremental loading
    latest_load_timestamp = get_latest_load_timestamp()
    print(f"Latest load timestamp in database: {latest_load_timestamp}")

    # Step 5: Fetch and insert only new blobs (after latest load timestamp)
    inserted_count = 0
    skipped_count = 0
    errors = []

    for blob in blobs:
        if blob.last_modified >= latest_load_timestamp:
            try:
                print(f"\nProcessing blob: {blob.name}")

                # Download blob content
                content = storage.get_blob_content(blob.name)
                data = json.loads(content)  # Parse JSON (eval handles both dict and list)

                # Insert into staging table
                with engine.connect() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO staging.stg_weather_raw (source, data, loaded_at)
                            VALUES (:source, :data, NOW())
                            ON CONFLICT (source) DO NOTHING
                        """),
                        {"source": blob.name, "data": json.dumps(data)},
                    )
                    conn.commit()
                    inserted_count += 1

                print(f"  Inserted: {blob.name}")

            except Exception as e:
                errors.append((blob.name, str(e)))
                # print(f"  Error processing blob: {e}")
        else:
            skipped_count += 1

    # Step 6: Verification and summary
    print("\n" + "=" * 50)
    print("Ingestion Summary:")
    print("=" * 50)
    print(f"Blobs found: {len(blobs)}")
    print(f"New blobs inserted: {inserted_count}")
    print(f"Skipped (already loaded): {skipped_count}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for blob_name, error in errors:
            print(f"  - {blob_name}: {error}")

    # Verify row count in database
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM staging.stg_weather_raw"))
        total_rows = result.fetchone()[0]
        print(f"\nTotal rows in staging.stg_weather_raw table: {total_rows}")

    if errors:
        raise RuntimeError(f"Ingestion completed with {len(errors)} errors")


if __name__ == "__main__":
    try:
        main()
        print("\nIngestion completed successfully!")
    except Exception as e:
        print(f"\nIngestion failed: {e}")
        raise
