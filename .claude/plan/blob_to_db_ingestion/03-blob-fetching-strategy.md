# Blob Fetching Strategy for Incremental Loading

## Objective
Efficiently fetch only new blobs from Azure storage between daily ingestion runs.

## Current State
- Blobs are stored in `sp-traffic` container
- Each blob name includes timestamp: `{source_path}/{prefix}_{timestamp}.json`
- Example: `previsao/previsao_2026-05-24T14:30:00.json`

## Strategy: Earliest Timestamp Filtering

### Algorithm
1. List all blobs in the container
2. Extract timestamps from blob names using regex
3. Find the earliest timestamp (`min_timestamp`)
4. Only fetch blobs with `timestamp > min_timestamp`
5. Insert fetched blobs into staging table

### Implementation Details

#### Blob Name Pattern
```python
# Regex to extract timestamp from blob name
TIMESTAMP_PATTERN = r"^([a-z_]+)/([a-z_]+)_(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.json$"

def extract_timestamp(blob_name: str) -> datetime | None:
    match = re.match(TIMESTAMP_PATTERN, blob_name)
    if match:
        return datetime.fromisoformat(match.group(2))
    return None
```

#### Blob Listing (using shared CloudStorage utility)
```python
# List all blobs in container
blobs = list(container_client.list_blobs())

# Filter by source prefix and extract timestamps
source_prefixes = ["previsao", "weather"]
all_timestamps = []

for blob in blobs:
    if any(blob.name.startswith(f"{prefix}/") for prefix in source_prefixes):
        ts = extract_timestamp(blob.name)
        if ts:
            all_timestamps.append(ts)

# Find earliest timestamp
min_timestamp = min(all_timestamps) if all_timestamps else None

# Only fetch blobs newer than min_timestamp
blobs_to_fetch = [b for b in blobs 
                  if any(b.name.startswith(f"{prefix}/") for prefix in source_prefixes)
                  and extract_timestamp(b.name) > min_timestamp]
```

### Edge Cases Handled
- **First run**: `min_timestamp` is None → fetch all blobs
- **Empty container**: No blobs to fetch, script exits gracefully
- **Re-run with no new data**: `blobs_to_fetch` is empty, script completes without inserts
- **Partial failures**: Failed blob downloads don't affect other successful downloads
