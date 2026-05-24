"""Fetch previsao blobs from Azure Storage and insert into PostgreSQL staging table."""

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

# Database connection
engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    pool_pre_ping=True,
)


def main():
    """Main ingestion workflow for previsao data."""
    print("Starting previsao blob ingestion...")

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
    storage = CloudStorage()

    # Step 3: List all previsao blobs from Azure Storage
    print("\nListing previsao blobs in Azure Blob Storage...")
    blob_prefixes = ["sptrans-olhovivo/previsao/previsao_"]
    blobs = storage.list_blobs_by_source(blob_prefixes)
    print(f"Found {len(blobs)} previsao blobs")

    if not blobs:
        print("No previsao blobs found. Exiting gracefully.")
        return

    # Step 4: Get earliest timestamp for incremental loading
    earliest_timestamp = min(b.last_modified for b in blobs)
    print(f"Earliest blob timestamp: {earliest_timestamp}")

    # Step 5: Fetch and insert only new blobs (after earliest timestamp)
    inserted_count = 0
    skipped_count = 0
    errors = []

    for blob in blobs:
        if blob.last_modified >= earliest_timestamp:
            try:
                print(f"\nProcessing blob: {blob.name}")

                # Download blob content
                import json
                content = storage.get_blob_content(blob.name)
                data = json.loads(content)  # Properly parse JSON

                # Insert into staging table
                with engine.connect() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO staging.stg_previsao_raw (source, data, loaded_at)
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
                print(f"  Error processing blob: {e}")
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
        result = conn.execute(text("SELECT COUNT(*) FROM staging.stg_previsao_raw"))
        total_rows = result.fetchone()[0]
        print(f"\nTotal rows in staging.stg_previsao_raw table: {total_rows}")

    if errors:
        raise RuntimeError(f"Ingestion completed with {len(errors)} errors")


if __name__ == "__main__":
    try:
        main()
        print("\nIngestion completed successfully!")
    except Exception as e:
        print(f"\nIngestion failed: {e}")
        raise
