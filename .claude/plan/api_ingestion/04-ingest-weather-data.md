# Weather Data Ingestion Plan

## Context

This step creates a Python script responsible for fetching real-time weather data from Open Meteo API using bus stop locations as geographical reference. Due to the 400 bus stops × 15-minute interval = ~40,000 daily calls exceeding the 10,000/day API limit, we implement grid-based spatial clustering to reduce query volume.

---

## Grid Design

### São Paulo Bounding Box
- **Latitude (py)**: -23.8265890 to -23.4891720 (range: 0.337°)
- **Longitude (px)**: -46.7636250 to -46.3830080 (range: 0.381°)

### Grid Configuration
| Parameter | Value |
|-----------|-------|
| Cell size | 0.025° × 0.025° |
| Total cells | ~64 unique grid cells |
| Daily API calls | ~256 (64 cells × 4 intervals) |
| API limit usage | 2.56% of 10,000/day limit |

### Cell Coverage
Each cell covers approximately:
- **Area**: ~8 km²
- **Distance**: ~3.5 km in any direction from center point

---

## Files to be created/modified

- Create local script at `ingestion/open_meteo/weather_staging/main.py`
- No other local files should be created or modified

---

## Implementation Details

### Step 1: Fetch Bus Stop Coordinates from PostgreSQL

- Connect to PostgreSQL database using **sqlalchemy**
- Credentials stored as DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME in **.env file at project root**
- Query `staging.stg_bus_stops` table for all records with `py` (latitude) and `px` (longitude) columns
- Extract unique coordinate pairs to determine actual grid cells needed

### Step 2: Assign Bus Stops to Grid Cells

For each bus stop, calculate its grid cell index:

```python
cell_row = int((stop_py - min_lat) / cell_size)
cell_col = int((stop_px - min_lon) / cell_size)
grid_key = f"{cell_row}_{cell_col}"
```

- Group all stops by their `grid_key`
- Select one representative stop per grid cell (e.g., first encountered or centroid)

### Step 3: Query Open Meteo API for Each Grid Cell

For each unique grid cell, query Open Meteo with parameters:

| Parameter | Value |
|-----------|-------|
| latitude | Representative cell center point |
| longitude | Representative cell center point |
| daily=precipitation_probability_percent | Rain probability variable |
| timezone=America/Sao_Paulo | Local time zone |
| precision=10m | High spatial resolution |

- Use **Session** from **requests** library for all API calls
- Store raw JSON response in memory (no intermediate file save)

### Step 4: Save Weather Data to Azure Blob Storage

- Authenticate using AZURE_STORAGE_KEY and AZURE_CONTAINER_NAME from **.env file at project root**
- Create filename format: `weather_TIMESTAMP.json` with ISO 8601 UTC timestamp
- Save JSON file under path: `sp-traffic/openmeteo/`
- Store complete weather data for all grid cells in single file

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

| Variable | Description | Required |
|----------|-------------|----------|
| `DB_USER` | PostgreSQL username | Yes |
| `DB_PASSWORD` | PostgreSQL password | Yes |
| `DB_HOST` | PostgreSQL host | Yes |
| `DB_PORT` | PostgreSQL port (default: 5432) | Yes |
| `DB_NAME` | PostgreSQL database name | Yes |
| `AZURE_STORAGE_KEY` | Azure Storage account key | Yes |
| `AZURE_CONTAINER_NAME` | Azure container for weather data | Yes |

### Grid Constants

```python
MIN_LAT = -23.8265890   # Southernmost point of São Paulo
MAX_LAT = -23.4891720   # Northernmost point of São Paulo
MIN_LON = -46.7636250   # Westernmost point of São Paulo
MAX_LON = -46.3830080   # Easternmost point of São Paulo
CELL_SIZE_LAT = 0.025
CELL_SIZE_LON = 0.025
```

---

## Database Schema

### Table: `staging.stg_weather_daily`

```sql
CREATE TABLE IF NOT EXISTS staging.stg_weather_daily (
    grid_key text PRIMARY KEY,            -- Unique identifier for each grid cell
    precipitation_probability_percent numeric(5,2),  -- Rain probability (%)
    source_file text DEFAULT 'weather_staging/latest.json',
    loaded_at timestamp with time zone DEFAULT NOW()
);

CREATE INDEX idx_stg_weather_daily_loaded_at ON staging.stg_weather_daily(loaded_at DESC);
```

**Field definitions:**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `grid_key` | text | PRIMARY KEY | Unique cell identifier (row_col format) |
| `precipitation_probability_percent` | numeric(5,2) | NOT NULL | Probability of rain (%) from Open Meteo API |
| `source_file` | text | DEFAULT 'weather_staging/latest.json' | Source filename for audit trail |
| `loaded_at` | timestamp with time zone | DEFAULT NOW() | When the record was loaded |

---

## JSON Structure (from Open Meteo API)

Expected response format:

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

**Expected counts:**
- Total grid cells: ~64 (actual count depends on bus stop distribution)
- Time intervals per cell: 168 (hourly forecast for 24 hours) or 72 (every 3 hours) depending on API parameters

---

## Implementation Steps

### Step 1: Environment Setup & Database Connection

Follow the same pattern as `paradas_staging/main.py`:
- Load `.env` using `find_dotenv()` from `python-dotenv`
- Import SQLAlchemy and read DB credentials from env vars
- Create database engine with `pool_pre_ping=True`

### Step 2: Fetch Bus Stop Coordinates from PostgreSQL

1. Query all records from `staging.stg_bus_stops` table
2. Extract unique `(py, px)` coordinate pairs
3. Log total count of bus stops and unique coordinates (expected ~400 stops)

### Step 3: Assign Stops to Grid Cells

For each bus stop:
1. Calculate cell row: `int((stop_py - MIN_LAT) / CELL_SIZE_LAT)`
2. Calculate cell col: `int((stop_px - MIN_LON) / CELL_SIZE_LON)`
3. Build grid key: `f"{cell_row}_{cell_col}"`
4. Group stops by grid key, selecting one representative per cell

### Step 4: Query Open Meteo API for Each Grid Cell

For each unique grid cell:
1. Calculate cell center point from representative stop coordinates
2. Call Open Meteo API with `daily=precipitation_probability_percent` and `precision=10m`
3. Store raw JSON response in memory (don't save to file yet)
4. Log successful API call per grid cell

### Step 5: Save Weather Data to Azure Blob Storage

1. Connect to Azure storage using `BlobServiceClient.from_connection_string(AZURE_STORAGE_KEY)`
2. Get container client for `AZURE_CONTAINER_NAME`
3. Create filename with ISO 8601 UTC timestamp format
4. Upload JSON data to path: `sp-traffic-data/weather_staging/`
5. Log successful upload

### Step 6: Load Weather Data into PostgreSQL Staging Table

1. Create table `staging.stg_weather_daily` if not exists using parameterized SQL
2. Parse weather data from Open Meteo API response (extract precipitation_probability_percent)
3. Insert records into staging table with deduplication by grid_key
4. Log total records inserted

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
cd ingestion/open_meteo/weather_staging
python main.py
```

**Expected Output:**
- "Fetching bus stop coordinates from PostgreSQL..."
- "Found X bus stops in database"
- "Assigned to Y unique grid cells"
- "Querying Open Meteo API for Z locations..."
- "Saved weather data to Azure Blob Storage: weather_staging_TIMESTAMP.json"
- "Inserted N records into staging.stg_weather_daily"

### Database Verification Queries

```sql
-- Check total count (expected ~64)
SELECT COUNT(*) FROM staging.stg_weather_daily;

-- Verify sample record structure
SELECT * FROM staging.stg_weather_daily LIMIT 5;

-- Check for duplicates (should return 0 rows)
SELECT grid_key, COUNT(*) as cnt 
FROM staging.stg_weather_daily 
GROUP BY grid_key 
HAVING COUNT(*) > 1;

-- Verify precipitation values are in valid range (0-100)
SELECT * FROM staging.stg_weather_daily 
WHERE precipitation_probability_percent < 0 OR precipitation_probability_percent > 100;
```

### Azure Blob Storage Verification

Verify the latest file exists in Azure Portal:
- Container: configured `AZURE_CONTAINER_NAME` (e.g., `sp-traffic-data`)
- Path: `/weather_staging/weather_staging_TIMESTAMP.json`
- Filename format: ISO 8601 timestamp with microseconds

---

## Performance Considerations

### Memory Management
- All bus stop coordinates loaded into memory before grid assignment (~400 records)
- Weather API responses stored in dict keyed by grid_key (expected ~256KB total)
- For larger datasets, consider streaming approach or chunked processing

### Database Performance
- SQLAlchemy connection pool handles inserts efficiently
- Index on `loaded_at` supports time-series queries
- Primary key on `grid_key` ensures fast deduplication

### API Rate Limiting
- 256 daily calls = 17 calls/minute (well under typical 10,000/day limit)
- Open Meteo's precision=10m parameter may increase call volume slightly
- Monitor actual usage and adjust grid size if approaching limits

---

## Testing Strategy

### Unit Tests (pytest)

1. **Grid cell assignment**: Given bus stop coordinates, verify correct grid_key calculation
2. **Open Meteo API query**: Mock requests library, verify correct parameters passed to API
3. **Data parsing**: Parse sample Open Meteo response, verify precipitation values extracted correctly
4. **Deduplication logic**: Insert duplicate records with same grid_key, verify only latest kept

### Integration Tests

- [ ] Test full pipeline with mocked PostgreSQL and Azure Blob Storage
- [ ] Test grid cell assignment with edge cases (boundary coordinates)
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

1. **Dynamic Grid Size**: Adjust cell size based on bus stop density in different regions
2. **Historical Weather**: Fetch past weather data for time-lapse visualization
3. **Multiple Variables**: Extend to include temperature, humidity, wind speed
4. **Incremental Updates**: Compare timestamps and only re-fetch changed grid cells
5. **Parallel Processing**: Use `asyncio` or `concurrent.futures` to query multiple grid cells simultaneously

---

## References

- [Open Meteo API Documentation](https://open-meteo.com/en/docs)
- [Azure Blob Storage Python SDK](https://docs.microsoft.com/en-us/python/api/azure-storage-blob/azure.storage.blob.blobserviceclient?view=azure-python)
- [São Paulo Coordinates Reference](https://en.wikipedia.org/wiki/S%C3%A3o_Paulo_(city))
