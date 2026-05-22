# Implementation Specification: Bus Data Ingestion from Olho Vivo API

## Overview

This specification defines the implementation details for fetching bus schedule data from the Olho Vivo API and storing aggregated results in Azure Blob Storage.

---

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   PostgreSQL │────▶│  olhovivo/main.py │────▶│    In-Memory   │────▶│ Azure Blob       │
│ (stg_lines) │     │  (Olho Vivo API) │     │    Data Store   │     │ Storage         │
└─────────────┘     └──────────────────┘     └─────────────────┘     └──────────────────┘
```

---

## Dependencies

### Required Packages (from requirements.txt)

- `requests` - HTTP client for API calls
- `sqlalchemy` - Database ORM for PostgreSQL connections
- `python-dotenv` - Environment variable management
- `azure-storage-blob` - Azure Blob Storage client library

### Optional Development Dependencies

- `pytest` - Testing framework
- `pytest-cov` - Code coverage reporting

---

## File Structure

```
ingestion/olho_vivo/previsao_staging/
├── main.py              # Main ingestion script
├── .env                 # Local environment configuration (optional)
└── __init__.py          # Package marker (optional)
```

---

## Configuration

### Environment Variables (.env at project root)

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `DB_USER` | PostgreSQL username | `postgres_user` | Yes |
| `DB_PASSWORD` | PostgreSQL password | `secure_password` | Yes |
| `DB_HOST` | PostgreSQL host | `localhost` or IP | Yes |
| `DB_PORT` | PostgreSQL port | `5432` | Yes |
| `DB_NAME` | PostgreSQL database name | `sp_traffic_db` | Yes |
| `OLHO_VIVO_URL` | Olho Vivo API base URL | `https://api.sptrans.com.br` | Yes |
| `SPTRANS_TOKEN` | SPTrans authentication token | `Bearer_token_here` | Yes |
| `AZURE_STORAGE_KEY` | Azure Storage account key | `storage_key_value` | Yes |
| `AZURE_CONTAINER_NAME` | Azure container name | `sp-traffic-data` | Yes |

### Environment Variables (optional, for local testing)

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_USER_LOCAL` | Local PostgreSQL user | - |
| `DB_PASSWORD_LOCAL` | Local PostgreSQL password | - |
| `OLHO_VIVO_URL_LOCAL` | Local API URL | - |
| `SPTRANS_TOKEN_LOCAL` | Local auth token | - |

---

## Implementation Details

### 1. Database Connection (main.py)

```python
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Database connection string
DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME'),
}

engine = create_engine(
    f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
    f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
    pool_pre_ping=True,
)
```

### 2. Fetch Bus Lines from PostgreSQL

```python
def fetch_bus_lines() -> list[str]:
    """Fetch all bus line IDs from the staging schema."""
    
    query = """
        SELECT DISTINCT line_id 
        FROM staging.stg_lines 
        ORDER BY line_id
    """
    
    with engine.connect() as conn:
        lines = conn.execute(text(query)).fetchall()
        return [str(line[0]) for line in lines]
```

**Expected:** 40 bus line IDs

### 3. Olho Vivo API Authentication

```python
class OlhoVivoAuth:
    def __init__(self, token: str):
        self.token = token
        self.session: requests.Session | None = None
    
    def authenticate(self) -> bool:
        """Authenticate with Olho Vivo API using session for cookies."""
        
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
```

### 4. Fetch Bus Data from API

The Olho Vivo API returns data with only two keys (`HR` and `PS`). We enrich the response by adding the `line_id` key to track which bus line each record belongs to.

```python
def fetch_bus_data(line_id: str, session: requests.Session) -> dict | None:
    """Fetch schedule data for a specific bus line."""
    
    url = f"{OLHO_VIVO_URL.rstrip('/')}/Previsao/Linha?codigoLinha={line_id}"
    response = session.get(url, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        # API returns only HR and PS keys; add line_id for tracking
        data["line_id"] = line_id
        return data
    return None
```

### 5. Data Aggregation and Storage

```python
from datetime import datetime
import json
from azure.storage.blob import BlobServiceClient

def save_to_azure_blob(data: list[dict]) -> str:
    """Save aggregated data to Azure Blob Storage."""
    
    # Generate filename with timestamp in ISO 8601 format
    timestamp = datetime.utcnow().isoformat()
    container_url = f"sptrans-olhovivo/previsao/previsao_{timestamp}.json"
    
    # Connect to Azure storage
    client = BlobServiceClient.from_connection_string(AZURE_STORAGE_KEY)
    container_client = client.get_container_client(AZURE_CONTAINER_NAME)
    
    # Upload file
    blob_client = container_client.get_blob_client(container_url)
    blob_client.upload_blob(
        data=json.dumps(data, indent=2).encode(),
        content_type="application/json",
        overwrite=True,
    )
    
    return container_url

def main():
    """Main ingestion workflow."""
    
    # Step 1: Fetch bus lines from database
    print("Fetching bus lines from PostgreSQL...")
    bus_lines = fetch_bus_lines()
    print(f"Found {len(bus_lines)} bus lines")
    
    if len(bus_lines) != 40:
        raise ValueError(f"Expected 40 bus lines, found {len(bus_lines)}")
    
    # Step 2: Authenticate with Olho Vivo API (creates session first)
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
    storage_url = save_to_azure_blob(all_data)
    print(f"Data saved to: {storage_url}")

if __name__ == "__main__":
    main()
```

---

## Error Handling Strategy

| Scenario | Action | Retry Policy |
|----------|--------|--------------|
| Database connection failure | Log error, exit with code 1 | No retry |
| Olho Vivo auth failure | Log error, exit with code 1 | No retry |
| Single bus line timeout | Log warning, continue to next line | Exponential backoff (max 3 retries) |
| Network error during fetch | Log error, continue to next line | Retry up to 2 times |
| Azure upload failure | Log error, exit with code 1 | No retry |

---

## Verification Steps

### 1. Database Verification

```bash
# Verify bus lines count in PostgreSQL
psql -h localhost -U postgres -d sp_traffic_db -c "SELECT COUNT(*) FROM staging.stg_lines;"
```

**Expected:** 40 rows

### 2. Local Execution Test

```bash
cd ingestion/olho_vivo/previsao_staging
python main.py
```

**Expected Output:**
- "Found 40 bus lines"
- Authentication success message
- Progress report (e.g., "Successfully fetched 40/40 bus lines")
- Storage URL confirmation

### 3. Azure Blob Verification

1. Navigate to Azure Portal → Storage Accounts
2. Select the storage account containing `sp-traffic` container
3. Browse to `sptrans-olhovivo/previsao/` folder
4. Verify JSON file exists with timestamp in filename
5. Download and validate structure:

```python
import json

with open("previsao_TIMESTAMP.json", "r") as f:
    data = json.load(f)

# Validate record count
print(f"Total records: {len(data)}")

# Sample first record
print(json.dumps(data[0], indent=2))
```

**Expected:** At least 40 records (one per bus line)

---

## Performance Considerations

### Rate Limiting

- Implement request delay between API calls to avoid rate limiting
- Recommended: 1-2 second delay between requests
- Total estimated time for 40 lines: ~80-120 seconds

```python
import time

for line_id in bus_lines:
    data = fetch_bus_data(line_id, session)
    if data:
        all_data.append(data)
    
    # Rate limiting - avoid API throttling
    time.sleep(1.5)  # 1.5 second delay between requests
```

### Memory Management

- Data is stored in-memory during processing
- For production use, consider streaming to disk if dataset exceeds memory capacity
- Current implementation assumes < 100MB JSON payload

---

## Testing Strategy

### Unit Tests (pytest)

```python
# tests/test_olhovo.py
import pytest
from unittest.mock import Mock, patch
import requests

class TestOlhoVivoAuth:
    def test_authenticate_success(self):
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "true"
            mock_post.return_value = mock_response
            
            auth = OlhoVivoAuth("test_token")
            assert auth.authenticate() is True
    
    def test_authenticate_failure(self):
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "false"
            mock_post.return_value = mock_response
            
            auth = OlhoVivoAuth("test_token")
            assert auth.authenticate() is False

class TestFetchBusData:
    def test_fetch_success(self):
        with patch('requests.Session.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"test": "data"}
            mock_get.return_value = mock_response
            
            session = requests.Session()
            result = fetch_bus_data("LINE_1", session)
            
            assert result == {"test": "data"}
```

### Integration Tests

- [ ] Test full pipeline with mocked PostgreSQL and Azure Blob Storage
- [ ] Test timeout handling for slow API responses
- [ ] Test error recovery when individual bus lines fail
- [ ] Verify JSON structure matches expected schema

---

## Deployment Checklist

- [ ] Update `requirements.txt` with new dependencies
- [ ] Create `.env.example` template file
- [ ] Add script to CI/CD pipeline (e.g., GitHub Actions)
- [ ] Document Azure Blob Storage access permissions required
- [ ] Set up monitoring/alerting for ingestion failures
- [ ] Add logging configuration (logging module)

---

## Future Enhancements

1. **Incremental Updates**: Compare timestamps and only re-fetch changed data
2. **Parallel Processing**: Use `asyncio` or `concurrent.futures` to fetch multiple lines simultaneously
3. **Data Validation**: Add schema validation for API responses
4. **Database Storage**: Persist processed data in PostgreSQL for querying
5. **Webhook Notifications**: Alert on ingestion failures

---

## References

- [Olho Vivo API Documentation](https://www.sptrans.com.br/desenvolvedores/api-do-olho-vivo-guia-de-referencia/documentacao-api/)
- [Azure Blob Storage Python SDK](https://docs.microsoft.com/en-us/python/api/azure-storage-blob/azure.storage.blob.blobserviceclient?view=azure-python)
