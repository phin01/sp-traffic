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

**Data Flow:**
1. Script fetches bus line IDs from PostgreSQL staging schema (`staging.stg_lines`), excluding lines in `stg_short_lines`
2. Authenticates with Olho Vivo API using cookie-based session authentication
3. Fetches schedule data for each bus line from the Olho Vivo API
4. Aggregates all responses in-memory, adding `line_id` key to track source
5. Saves aggregated JSON data to Azure Blob Storage

---

## Dependencies

### Required Packages (from requirements.txt)

- `requests` - HTTP client for API calls
- `sqlalchemy` - Database ORM for PostgreSQL connections
- `python-dotenv` - Environment variable management using `find_dotenv()`
- `azure-storage-blob` - Azure Blob Storage client library

---

## File Structure

```
ingestion/olho_vivo/previsao_staging/
├── main.py              # Main ingestion script
└── .env                 # Local environment configuration (optional)
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
| `AZURE_CONTAINER_NAME` | Azure container name | `sp-traffic-data` or `sptrans-olhovivo` | Yes |

---

## Implementation Guidelines

### 1. Database Connection

Use SQLAlchemy with connection pooling enabled:

```python
from sqlalchemy import create_engine
from dotenv import find_dotenv, load_dotenv

# Load environment variables using find_dotenv()
load_dotenv(find_dotenv())

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

Query the staging schema to retrieve all bus line IDs, excluding short lines:

- Expected count: variable number of bus lines (excluding those in `stg_short_lines`)
- Use `SELECT DISTINCT sl.line_id FROM staging.stg_lines sl LEFT JOIN staging.stg_short_lines ssl ON sl.line_id = ssl.line_id WHERE ssl.line_id IS NULL ORDER BY sl.line_id`
- Return as list of strings for API iteration

### 3. Olho Vivo API Authentication

Authentication is cookie-based, requiring session management:

1. Create authenticated session using `requests.Session()`
2. POST to `/Login/Autenticar?token={SPTRANS_TOKEN}` endpoint
3. Verify authentication success by checking response status code and body (`"true"`)
4. Reuse same session for all subsequent API calls to maintain cookies

**Important:** All Olho Vivo API requests must use the authenticated session to include required cookies.

### 4. Fetch Bus Data from API

The Olho Vivo API returns data with only two keys (`HR` and `PS`). Enrich responses by adding `line_id` key for tracking:

- URL pattern: `{OLHO_VIVO_URL}/Previsao/Linha?codigoLinha={line_id}`
- Request timeout: 30 seconds per line
- Response format: JSON with `line_id`, `HR`, and `PS` keys
- Expected response structure: array of schedule records

**Note:** Bus lines in `staging.stg_short_lines` are excluded from API calls to avoid unnecessary processing.

### 5. Data Aggregation

Aggregate all bus line responses into a single list before storage:

- Each record should include `line_id` for traceability
- Preserve original API response structure (`HR`, `PS`)
- Log success/failure counts during processing

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

## Performance Considerations

### Rate Limiting

- Implement request delay between API calls to avoid rate limiting
- Recommended: 1-2 second delay between requests
- Total estimated time for variable bus lines: depends on count

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
- Current implementation assumes < 100MB JSON payload
- For production use, consider streaming to disk if dataset exceeds memory capacity

---

## Testing Strategy

### Unit Tests (pytest)

Test individual components:

1. **Authentication**: Mock `requests.post` to verify auth endpoint call and success/failure conditions
2. **Data fetching**: Mock `requests.Session.get` to verify API calls with correct parameters
3. **Database queries**: Verify line ID retrieval from PostgreSQL staging table, excluding short lines

### Integration Tests

- [ ] Test full pipeline with mocked PostgreSQL and Azure Blob Storage
- [ ] Test timeout handling for slow API responses
- [ ] Test error recovery when individual bus lines fail
- [ ] Verify JSON structure matches expected schema

---

## Deployment Checklist

- [ ] Update `requirements.txt` with new dependencies (`azure-storage-blob`)
- [ ] Create `.env.example` template file documenting required variables
- [ ] Add script to CI/CD pipeline (e.g., GitHub Actions)
- [ ] Document Azure Blob Storage access permissions required
- [ ] Set up monitoring/alerting for ingestion failures

---

## Future Enhancements

1. **Incremental Updates**: Compare timestamps and only re-fetch changed data
2. **Parallel Processing**: Use `asyncio` or `concurrent.futures` to fetch multiple lines simultaneously
3. **Data Validation**: Add schema validation for API responses before storage
4. **Database Storage**: Persist processed data in PostgreSQL for querying
5. **Webhook Notifications**: Alert on ingestion failures

---

## References

- [Olho Vivo API Documentation](https://www.sptrans.com.br/desenvolvedores/api-do-olho-vivo-guia-de-referencia/documentacao-api/)
- [Azure Blob Storage Python SDK](https://docs.microsoft.com/en-us/python/api/azure-storage-blob/azure.storage.blob.blobserviceclient?view=azure-python)
