"""Fetch bus stop coordinates from PostgreSQL and assign to grid cells."""

import os
from collections import defaultdict
from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv
from utils.logging import get_logger
from requests import Session
from utils.cloud import CloudStorage


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

# Grid constants (São Paulo coordinates)
MIN_LAT = -23.8265890   # Southernmost bus stop evaluated
MAX_LAT = -23.4891720   # Northernmost bus stop evaluated
MIN_LON = -46.7636250   # Westernmost bus stop evaluated
MAX_LON = -46.3830080   # Easternmost bus stop evaluated
CELL_SIZE_LAT = 0.025
CELL_SIZE_LON = 0.025


def fetch_bus_stop_coordinates():
    """Fetch all bus stop coordinates from staging table.

    Returns:
        List of tuples containing (py, px, cp) for each bus stop.
    """
    print("Fetching bus stop coordinates from PostgreSQL...")

    query = text("SELECT py, px, cp FROM staging.stg_bus_stops ORDER BY cp")

    with engine.connect() as conn:
        stops = conn.execute(query).fetchall()

    print(f"Found {len(stops)} bus stops in database")
    return stops


def assign_to_grid_cells(stops):
    """Assign each stop to a grid cell, returning one representative per cell.

    Uses Option A (first encountered) for simplicity. The 0.025° cell size is small enough that any representative will yield similar weather data.

    Args:
        stops: List of tuples containing (py, px, cp) for each bus stop.

    Returns:
        List of dictionaries with keys 'cp', 'py', 'px' representing one bus stop per grid cell.
    """
    grid_representatives = defaultdict(list)

    for stop in stops:
        py, px, cp = float(stop[0]), float(stop[1]), int(stop[2])

        # Calculate grid cell coordinates
        cell_row = int((py - MIN_LAT) / CELL_SIZE_LAT)
        cell_col = int((px - MIN_LON) / CELL_SIZE_LON)
        grid_key = f"{cell_row}_{cell_col}"

        grid_representatives[grid_key].append({
            'cp': cp,
            'py': py,
            'px': px
        })

    # Select first representative per cell (simplest approach - Option A)
    representatives = {
        key: rep for key, reps in grid_representatives.items()
        for rep in [reps[0]]
    }

    print(f"Assigned to {len(representatives)} unique grid cells")
    return list(representatives.values())


def verify_database_connection():
    """Verify that the database connection is working."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            row = result.fetchone()
            print(f"Database connection verified (row: {row})")
            return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        raise


def query_open_meteo(representatives):
    """Query Open Meteo API for precipitation probability at each grid cell.

    Args:
        representatives: List of dictionaries with keys 'cp', 'py', 'px'.

    Returns:
        Dictionary keyed by CP, containing full weather data from API response.
    """
    
    session = Session()
    weather_data = {}

    for rep in representatives:
        py, px = rep['py'], rep['px']

        # Build URL following the sample format
        url = f"https://api.open-meteo.com/v1/forecast"
        params_str = (
            f"latitude={py}&longitude={px}"
            "&hourly=precipitation&current=rain,temperature_2m,"
            "precipitation,showers,relative_humidity_2m,weather_code"
            "&forecast_days=1"
        )
        full_url = f"{url}?{params_str}"

        response = session.get(full_url)

        if response.status_code != 200:
            print(f"API error for cell ({py}, {px}): {response.status_code}")
            continue

        data = response.json()
        weather_data[rep['cp']] = data

    return weather_data


def save_to_blob(weather_data):
    """Save weather data to Azure Blob Storage.

    Args:
        weather_data: Dictionary keyed by CP, containing full weather JSON.
    """

    storage = CloudStorage()
    blob_name = storage.generate_blob_name("openmeteo/weather", "weather")
    storage.upload_json(weather_data, blob_name)

    print(f"Saved weather data to Azure Blob Storage: {blob_name}")


def main():
    """Main ingestion workflow."""
    try:
        # Step 1: Verify database connection
        verify_database_connection()

        # Step 2: Fetch bus stop coordinates from PostgreSQL
        stops = fetch_bus_stop_coordinates()

        if not stops:
            print("No bus stop data available. Exiting gracefully.")
            return

        # Step 3: Assign to grid cells and select representatives
        representatives = assign_to_grid_cells(stops)

        # Step 4: Query Open Meteo API for each representative
        weather_data = query_open_meteo(representatives)

        if not weather_data:
            print("No weather data retrieved. Exiting gracefully.")
            return

        print(f"Retrieved weather data for {len(weather_data)} grid cells")

        # Step 5: Save to Azure Blob Storage
        save_to_blob(weather_data)

    except Exception as e:
        print(f"Error during ingestion: {e}")
        raise


if __name__ == "__main__":
    logger = get_logger("open_meteo.weather_staging")
    
    try:
        main()
        logger.log_run(succeeded=True)
    except Exception as e:
        logger.log_run(succeeded=False, error_message=str(e))
