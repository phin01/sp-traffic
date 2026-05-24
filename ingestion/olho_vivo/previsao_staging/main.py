import os
from sqlalchemy import create_engine, text
from utils.cloud import CloudStorage
from dotenv import load_dotenv, find_dotenv
import requests
from utils.logging import get_logger

# Load environment variables from .env file at project root
load_dotenv(dotenv_path=find_dotenv())

# Configuration
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME')
OLHO_VIVO_URL = os.getenv('OLHO_VIVO_URL')
SPTRANS_TOKEN = os.getenv('SPTRANS_TOKEN')

# Database connection
engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    pool_pre_ping=True,
)


def fetch_bus_lines() -> list[str]:
    """Fetch all bus line IDs from the staging schema, excluding short lines."""

    query = text(
        "SELECT DISTINCT sl.line_id "
        "FROM staging.stg_lines sl "
        "LEFT JOIN staging.stg_short_lines ssl ON sl.line_id = ssl.line_id "
        "WHERE ssl.line_id IS NULL "
        "ORDER BY sl.line_id"
    )

    with engine.connect() as conn:
        lines = conn.execute(query).fetchall()
        return [str(line[0]) for line in lines]


class OlhoVivoAuth:
    """Handle authentication with Olho Vivo API."""

    def __init__(self, token: str):
        self.token = token
        self.session: requests.Session | None = None

    def authenticate(self) -> bool:
        """Authenticate with Olho Vivo API. Returns True if successful."""

        url = f"{OLHO_VIVO_URL.rstrip('/')}/Login/Autenticar?token={self.token}"
        response = self.session.post(url, timeout=10)

        return (response.status_code == 200 and
                response.text.strip() == "true")

    def get_session(self) -> requests.Session:
        """Get authenticated session."""
        if self.session is None or not self.session.is_active:
            self.session = requests.Session()
            self.authenticate()

        return self.session


def fetch_bus_data(line_id: str, session: requests.Session) -> dict | None:
    """Fetch schedule data for a specific bus line."""

    url = f"{OLHO_VIVO_URL.rstrip('/')}/Previsao/Linha?codigoLinha={line_id}"
    response = session.get(url, timeout=30)

    if response.status_code == 200:
        data = response.json()
        # Add line_id to the response (API returns HR and PS keys only)
        data["line_id"] = line_id
        return data
    return None


def save_to_blob(data: list[dict]) -> str:
    """Save aggregated data to Azure Blob Storage."""

    storage = CloudStorage()
    blob_name = storage.generate_blob_name("sptrans-olhovivo/previsao", "previsao")
    return storage.upload_json(data, blob_name)


def main():
    """Main ingestion workflow."""

    # Step 1: Fetch bus lines from database
    print("Fetching bus lines from PostgreSQL...")
    bus_lines = fetch_bus_lines()
    print(f"Found {len(bus_lines)} bus lines")

    if not bus_lines:
        raise ValueError("No bus lines found in database")

    # Step 2: Authenticate with Olho Vivo API
    print("Authenticating with Olho Vivo API...")
    auth = OlhoVivoAuth(os.getenv('SPTRANS_TOKEN'))
    session = auth.get_session()

    if not auth.authenticate():
        raise RuntimeError("Failed to authenticate with Olho Vivo API")

    # Step 3: Fetch data for each bus line
    print("Fetching bus schedule data...")
    all_data = []
    success_count = 0

    for line_id in bus_lines:
        try:
            data = fetch_bus_data(line_id, session)
            if data:
                all_data.append(data)
                success_count += 1
        except requests.exceptions.Timeout:
            print(f"Timeout fetching data for line {line_id}")
        except Exception as e:
            print(f"Error fetching data for line {line_id}: {e}")

    print(f"\nSuccessfully fetched {success_count}/{len(bus_lines)} bus lines")

    # Step 4: Save to Azure Blob Storage
    print("Saving to Azure Blob Storage...")
    storage_url = save_to_blob(all_data)
    print(f"Data saved to: {storage_url}")


if __name__ == "__main__":
    logger = get_logger("olho_vivo.previsao_staging")

    try:
        main()
        logger.log_run(succeeded=True)
    except Exception as e:
        logger.log_run(succeeded=False, error_message=str(e))
