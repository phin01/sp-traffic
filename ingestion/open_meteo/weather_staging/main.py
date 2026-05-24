"""Fetch bus stop coordinates from PostgreSQL and assign to grid cells."""

import os
from collections import defaultdict
from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv


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

        # Display sample of first 5 representatives for verification
        print("\nSample of grid cell representatives (first 5):")
        for i, rep in enumerate(representatives[:5], 1):
            cp, py, px = rep['cp'], rep['py'], rep['px']
            print(f"  {i}. CP={cp}, Lat={py:.6f}, Lon={px:.6f}")

    except Exception as e:
        print(f"Error during ingestion: {e}")
        raise


if __name__ == "__main__":
    main()
