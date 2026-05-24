# Implementation Roadmap

## Phase 1: Shared Blob Utility (utils/cloud.py)

### Tasks
1. Add `BlobInfo` dataclass to track blob metadata:
   ```python
   from dataclasses import dataclass
   @dataclass
   class BlobInfo:
       name: str
       last_modified: datetime
       size: int
   ```

2. Extend `CloudStorage` class with read methods:
   - `list_blobs_by_source(source_prefixes: list[str]) -> list[BlobInfo]`
   - `get_blob_timestamps() -> dict[str, datetime]`
   - `get_blob_content(blob_name: str) -> str`

3. Add type hints and docstrings following existing patterns

### Files Modified
- `utils/cloud.py`

---

## Phase 2: Previsao Ingestion Script (db/stg_previsao_raw/main.py)

### Tasks
1. Create new file at `db/stg_previsao_raw/main.py`
2. Implement workflow:
   - Connect to Azure storage using shared utility
   - List blobs and filter by earliest timestamp
   - Download only new blobs
   - Insert into `stg_previsao_raw` with blob filename as source
3. Add verification step (check row count in DB)

### Files Created/Modified
- `db/stg_previsao_raw/main.py` (new)

---

## Phase 3: Weather Ingestion Script (db/stg_weather_raw/main.py)

### Tasks
1. Create new file at `db/stg_weather_raw/main.py`
2. Implement similar workflow as previsao script but for weather data
3. Insert into `stg_weather_raw` table

### Files Created/Modified
- `db/stg_weather_raw/main.py` (new)

---

## Phase 4: Database Schema Creation

### Tasks
1. Create SQL scripts to create staging tables:
   - `scripts/create_staging_tables.sql`
2. Add indexes for efficient incremental loading queries
3. Document table schemas in README or separate spec file

### Files Created/Modified
- `scripts/create_staging_tables.sql` (new)

---

## Phase 5: Testing and Verification

### Tasks
1. Run db/stg_previsao_raw/main.py → verify rows in staging table
2. Run db/stg_weather_raw/main.py → verify rows in staging table  
3. Re-run both scripts → confirm only new blobs are loaded
4. Verify blob filenames appear correctly as source column values

### Files Modified
- Existing ingestion scripts (for testing)

---

## Success Criteria
- [ ] Both ingestion scripts run without errors
- [ ] Staging tables contain raw nested JSON data
- [ ] Blob filenames appear in `source` column
- [ ] Re-running scripts only loads new blobs (incrementality works)
- [ ] Logs show clear progress and any failures
