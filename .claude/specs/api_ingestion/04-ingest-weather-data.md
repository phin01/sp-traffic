# Implementation Specification: Ingest Weather Data from Open Meteo API Using Grid-Based Clustering

## Overview

This specification defines how to retrieve real-time weather data from Open Meteo API using a grid-based spatial clustering approach. Instead of querying 400 individual bus stops (which would require ~40,000 daily API calls at 15-minute intervals), we cluster bus stops into approximately 64 grid cells, reducing API calls to well within the 10,000/day limit.

---

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│ PostgreSQL  │────▶│   weather_staging│────▶│    In-Memory   │────▶│ Azure Blob       │
│ (bus stops) │     │      main.py     │     │    Data Store  │     │   Storage        │
└─────────────┘     └──────────────────┘     └─────────────────┘     └──────────────────┘
                              │                    │                        
                              ▼                    ▼                        
                       ┌─────────────┐       ┌─────────────┐              
                       │ Grid Cell   │       │ Open Meteo  │   
                       │ Assignment  │◀──────│ API Queries │   
                       └─────────────┘       └─────────────┘   
```

**Data Flow:**
1. Script connects to PostgreSQL and fetches all bus stop coordinates from `staging.stg_bus_stops`
2. Assigns each bus stop to a grid cell based on its latitude/longitude
3. Groups stops by grid key, selecting one representative per cell (~64 cells)
4. Queries Open Meteo API for precipitation probability at each grid cell center
5. Stores raw JSON response in memory (no intermediate file save)
6. Uploads weather data to Azure Blob Storage as `weather_TIMESTAMP.json`

---

## Dependencies

### Required Packages (from requirements.txt)

- `requests` - HTTP client for API calls
- `sqlalchemy` - Database ORM for PostgreSQL connections  
- `python-dotenv` - Environment variable management
- `azure-storage-blob` - Azure Blob Storage client library

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
| `AZURE_STORAGE_KEY` | Azure Storage account key | `storage_key_value` | Yes |
| `AZURE_CONTAINER_NAME` | Azure container for weather data | `sp-traffic` | Yes |

### Grid Constants (hardcoded in script)

```python
MIN_LAT = -23.8265890   # Southernmost bus stop evaluated
MAX_LAT = -23.4891720   # Northernmost bus stop evaluated
MIN_LON = -46.7636250   # Westernmost bus stop evaluated
MAX_LON = -46.3830080   # Easternmost bus stop evaluated
CELL_SIZE_LAT = 0.025
CELL_SIZE_LON = 0.025
```

---

## Database Schema

### Source Table: `staging.stg_bus_stops`

Existing table with bus stop coordinates:

| Field | Type | Description |
|-------|------|-------------|
| `cp` | integer | Bus stop code (unique identifier) |
| `np` | text | Bus stop name |
| `py` | numeric(10, 7) | Y coordinate/latitude (-23.8 to -23.5 for São Paulo) |
| `px` | numeric(10, 7) | X coordinate/longitude (-46.8 to -46.4 for São Paulo) |
| `line_id` | text | Associated bus line ID |

---

## Grid Cell Assignment Algorithm

### Coordinate Ranges (São Paulo)

- **Latitude (py)**: -23.8265890 to -23.4891720 (range: 0.337°)
- **Longitude (px)**: -46.7636250 to -46.3830080 (range: 0.381°)

### Cell Calculation Formula

For each bus stop with coordinates `(py, px)`:

```python
cell_row = int((py - MIN_LAT) / CELL_SIZE_LAT)
cell_col = int((px - MIN_LON) / CELL_SIZE_LON)
grid_key = f"{cell_row}_{cell_col}"
```

### Example Calculations

| Bus Stop | py (lat) | px (lon) | cell_row | cell_col | grid_key |
|----------|----------|----------|----------|----------|----------|
| A | -23.8000000 | -46.5000000 | 10 | 14 | "10_14" |
| B | -23.7000000 | -46.6000000 | 8 | 16 | "8_16" |
| C | -23.5000000 | -46.4000000 | 19 | 17 | "19_17" |

### Representative Selection

For each grid key, select one representative bus stop:
- **Option A**: First encountered (simplest)
- **Option B**: Centroid of all stops in cell (more accurate)
- **Option C**: Stop with highest precipitation probability (weather-focused)

**Recommendation**: Use Option A for simplicity. The 0.025° cell size is small enough that any representative will yield similar weather data.

---

## Open Meteo API Configuration

### Base URL

```
https://api.open-meteo.com/v1/forecast
```

### Request Parameters (per grid cell)

| Parameter | Value | Description |
|-----------|-------|-------------|
| `latitude` | Cell center latitude | e.g., -23.562884 |
| `longitude` | Cell center longitude | e.g., -46.573316 |
| `daily=precipitation_probability_percent` | Required variable | Rain probability |
| `timezone=America/Sao_Paulo` | Local time zone | Correct for Brazil |
| `precision=10m` | High spatial resolution | 10-meter grid |

### Example Request

```python
response = session.get(
    "https://api.open-meteo.com/v1/forecast",
    params={
        "latitude": -23.562884,
        "longitude": -46.573316,
        "daily=precipitation_probability_percent",
        "timezone=America/Sao_Paulo",
        "precision=10m"
    }
)
```

### Expected Response Structure

```json
{
  "latitude": -23.562884,
  "longitude": -46.573316,
  "time": {
    "start": "2026-05-23T00:00:00Z",
    "end": "2026-05-24T00:00:00Z"
  },
  "daily": {
    "precipitation_probability_percent": [
      {"time": "2026-05-23T00:00:00Z", "value": 15.0},
      {"time": "2026-05-23T03:00:00Z", "value": 20.0},
      ...
    ]
  }
}
```

**Note**: The API returns hourly data for 24 hours (168 time intervals). For the project's use case (15-minute updates), we'll store all available data and let downstream queries select specific timestamps.

---

## Azure Blob Storage Configuration

### Container Path

All weather files stored under: `sp-traffic/openmeteo/`

### Filename Format

```
weather_TIMESTAMP.json
```

Where TIMESTAMP is UTC datetime in ISO 8601 format with microseconds:
- Example: `weather_2026-05-23T14:30:00.000000Z.json`

### Storage Pattern

```
sp-traffic-data/
└── weather_staging/
    ├── weather_staging_2026-05-23T06:00:00.000000Z.json
    ├── weather_staging_2026-05-23T06:15:00.000000Z.json
    └── ... (up to 256 files per day)
```

---

## Implementation Steps

### Step 1: Environment Setup & Database Connection

Follow the same pattern as `paradas_staging/main.py`:

```python
from dotenv import load_dotenv, find_dotenv
import os
from sqlalchemy import create_engine

load_dotenv(dotenv_path=find_dotenv())

DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME')

engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    pool_pre_ping=True,
)
```

### Step 2: Fetch Bus Stop Coordinates from PostgreSQL

```python
def fetch_bus_stop_coordinates():
    """Fetch all bus stop coordinates from staging table."""
    query = text("SELECT py, px FROM staging.stg_bus_stops")
    
    with engine.connect() as conn:
        stops = conn.execute(query).fetchall()
    
    print(f"Found {len(stops)} bus stops in database")
    return stops
```

### Step 3: Assign Stops to Grid Cells and Select Representatives

```python
def assign_to_grid_cells(stops):
    """Assign each stop to a grid cell, returning one representative per cell."""
    from collections import defaultdict
    
    MIN_LAT = -23.8265890
    MAX_LAT = -23.4891720
    MIN_LON = -46.7636250
    MAX_LON = -46.3830080
    CELL_SIZE_LAT = 0.025
    CELL_SIZE_LON = 0.025
    
    grid_representatives = defaultdict(list)
    
    for stop in stops:
        py, px = stop[0], stop[1]
        
        cell_row = int((py - MIN_LAT) / CELL_SIZE_LAT)
        cell_col = int((px - MIN_LON) / CELL_SIZE_LON)
        grid_key = f"{cell_row}_{cell_col}"
        
        grid_representatives[grid_key].append({
            'py': py,
            'px': px,
            'cp': stop[2]  # bus stop code
        })
    
    # Select first representative per cell (simplest approach)
    representatives = {
        key: rep for key, reps in grid_representatives.items() 
        for rep in [reps[0]]
    }
    
    print(f"Assigned to {len(representatives)} unique grid cells")
    return list(representatives.values())
```

### Step 4: Query Open Meteo API for Each Grid Cell

```python
def query_open_meteo(representatives):
    """Query Open Meteo API for precipitation probability at each grid cell."""
    from requests import Session
    
    session = Session()
    weather_data = {}
    
    for rep in representatives:
        py, px = rep['py'], rep['px']
        
        response = session.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": py,
                "longitude": px,
                "daily=precipitation_probability_percent",
                "timezone=America/Sao_Paulo",
                "precision=10m"
            }
        )
        
        if response.status_code != 200:
            print(f"API error for cell ({py}, {px}): {response.status_code}")
            continue
        
        data = response.json()
        weather_data[rep['cp']] = data
    
    return weather_data
```

### Step 5: Save Weather Data to Azure Blob Storage

```python
def save_to_azure_blob(weather_data):
    """Save weather data to Azure Blob Storage."""
    from azure.storage.blob import BlobServiceClient
    
    AZURE_STORAGE_KEY = os.getenv('AZURE_STORAGE_KEY')
    AZURE_CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME')
    
    client = BlobServiceClient.from_connection_string(AZURE_STORAGE_KEY)
    container_client = client.get_container_client(AZURE_CONTAINER_NAME)
    
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'
    blob_name = f"weather_staging/{timestamp}.json"
    
    # Create file in container
    container_client.create_blob(blob_name, data=json.dumps(weather_data).encode())
    
    print(f"Saved weather data to Azure Blob Storage: {blob_name}")
```

---

## Error Handling Strategy

| Scenario | Action | Retry Policy |
|----------|--------|--------------|
| PostgreSQL connection failure | Log error, exit with code 1 | No retry |
| No bus stops found in database | Log warning, exit gracefully (no crash) | No retry |
| Open Meteo API rate limit | Log error, implement exponential backoff | Retry after delay |
| Invalid/missing API response | Log error, skip affected grid cell | Skip and continue |
| Azure Blob Storage connection failure | Log error, exit with code 1 | No retry |
| Upload failure | Log error, exit with code 1 | No retry |

---

## Verification Steps

### Local Execution Test

```bash
python -m ingestion.open_meteo.weather_staging.main
```

**Expected Output:**
- "Fetching bus stop coordinates from PostgreSQL..."
- "Found ~400 bus stops in database"
- "Assigned to ~64 unique grid cells"
- "Querying Open Meteo API for 64 locations..."
- "Saved weather data to Azure Blob Storage: weather_staging_TIMESTAMP.json"
- "Inserted N records into staging.stg_weather_daily"

### Azure Blob Storage Verification

Verify the latest file exists in Azure Portal:
- Container: configured `AZURE_CONTAINER_NAME` (e.g., `sp-traffic-data`)
- Path: `/weather_staging/weather_staging_TIMESTAMP.json`
- Filename format: ISO 8601 timestamp with microseconds

---

## Performance Considerations

### Memory Management
- All bus stop coordinates loaded into memory before grid assignment (~400 records, minimal memory)
- Weather API responses stored in dict keyed by representative CP (expected ~256KB total JSON)
- For larger datasets, consider streaming approach or chunked processing

### API Rate Limiting
- 256 daily calls = ~17 calls/minute (well under typical 10,000/day limit)
- Open Meteo's precision=10m parameter may increase call volume slightly due to higher resolution grid
- Monitor actual usage and adjust grid size if approaching limits

---

## Testing Strategy

### Unit Tests (pytest)

1. **Grid cell assignment**: Given bus stop coordinates, verify correct grid_key calculation using boundary cases
2. **Open Meteo API query**: Mock requests library, verify correct parameters passed to API for each cell
3. **Data parsing**: Parse sample Open Meteo response, verify precipitation values extracted correctly from nested structure
4. **Deduplication logic**: Insert duplicate records with same grid_key, verify only latest kept

### Integration Tests

- [ ] Test full pipeline with mocked PostgreSQL and Azure Blob Storage
- [ ] Test grid cell assignment with edge cases (boundary coordinates at MIN/MAX)
- [ ] Test error handling for API failures or missing data
- [ ] Verify precipitation values within valid range after insert

---

## Deployment Checklist

- [ ] Update `requirements.txt` if new dependencies needed (`azure-storage-blob`)
- [ ] Create `.env.example` template documenting required variables
- [ ] Add script to CI/CD pipeline (e.g., GitHub Actions)
- [ ] Document Azure Blob Storage access permissions required
- [ ] Set up monitoring/alerting for ingestion failures

---

## Future Enhancements

1. **Dynamic Grid Size**: Adjust cell size based on bus stop density in different regions of São Paulo
2. **Historical Weather**: Fetch past weather data for time-lapse visualization feature
3. **Multiple Variables**: Extend to include temperature, humidity, wind speed alongside precipitation
4. **Incremental Updates**: Compare timestamps and only re-fetch changed grid cells instead of full refresh
5. **Parallel Processing**: Use `asyncio` or `concurrent.futures` to query multiple grid cells simultaneously for faster execution

---

## References

- [Open Meteo API Documentation](https://open-meteo.com/en/docs)
- [Azure Blob Storage Python SDK](https://docs.microsoft.com/en-us/python/api/azure-storage-blob/azure.storage.blob.blobserviceclient?view=azure-python)
- [São Paulo Coordinates Reference](https://en.wikipedia.org/wiki/S%C3%A3o_Paulo_(city))

---

## Implementation Checklist

### Stage 1: Environment Setup & Database Connection (Steps 1-2)
- [ ] Create `ingestion/open_meteo/weather_staging/` directory structure
- [ ] Implement environment loading with dotenv and find_dotenv()
- [ ] Configure PostgreSQL connection using SQLAlchemy
- [ ] Create `fetch_bus_stop_coordinates()` function to query `staging.stg_bus_stops`
- [ ] Add logging for "Fetching bus stop coordinates from PostgreSQL..."
- [ ] Add logging for "Found N bus stops in database"

### Stage 2: Grid Cell Assignment (Step 3)
- [ ] Implement grid constants (MIN_LAT, MAX_LAT, MIN_LON, MAX_LON, CELL_SIZE_LAT, CELL_SIZE_LON)
- [ ] Create `assign_to_grid_cells()` function using defaultdict
- [ ] Implement cell calculation formula for each bus stop
- [ ] Select first representative per grid cell (Option A)
- [ ] Add logging for "Assigned to N unique grid cells"
- [ ] Write unit tests for boundary cases

### Stage 3: Open Meteo API Queries (Step 4)
- [ ] Create `query_open_meteo()` function using requests.Session
- [ ] Implement API request with precision=10m parameter
- [ ] Handle API errors and rate limiting
- [ ] Parse JSON response structure
- [ ] Store weather data in dict keyed by representative CP
- [ ] Add logging for "Querying Open Meteo API for N locations..."

### Stage 4: Azure Blob Storage (Step 5)
- [ ] Create `save_to_azure_blob()` function using azure-storage-blob
- [ ] Implement filename format with ISO 8601 timestamp
- [ ] Handle container creation if needed
- [ ] Upload weather data as JSON blob
- [ ] Add logging for "Saved weather data to Azure Blob Storage: ..."
- [ ] Write integration tests for full pipeline

### Error Handling & Verification
- [ ] Implement error handling strategy (PostgreSQL, API, Azure failures)
- [ ] Create verification script for local execution test
- [ ] Set up monitoring for ingestion failures
