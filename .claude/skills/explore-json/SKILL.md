# Explore JSON Files (Bus Stops Data)

## Context
JSON files in `ingestion/olho_vivo/paradas_staging/` contain bus route data with structure:
```json
{
  "line_id": <bus_line_id>,
  "ps": [
    {"cp": "<stop_code>", ...},
    ...
  ]
}
```

## Quick Analysis Script
Run this to analyze any JSON file in the folder:

```powershell
cd "I:\DEV\sp-traffic\ingestion\olho_vivo\paradas_staging"
python -c "
import json, sys
data = json.load(open(sys.argv[1]))
stop_counts = {}
for line in data:
    stop_counts[line['line_id']] = len(line.get('ps', []))
sorted_by_stops = sorted(stop_counts.items(), key=lambda x: x[1], reverse=True)
print(f'Total lines: {len(data)}')
print('\nTop 5 by stops:')
for l, c in sorted_by_stops[:5]:
    print(f'  Line {l}: {c} stops')
all_counts = [c for c in stop_counts.values()]
print(f'\nTotal stops: {sum(all_counts)}')
print(f'Avg stops/line: {sum(all_counts)/len(all_counts):.1f}')
" "$@"
```

## Common Queries

### Count stops per line (top N)
```python
sorted(stop_counts.items(), key=lambda x: x[1], reverse=True)[:N]
```

### Find lines with fewest/most stops
```python
min(stop_counts, key=stop_counts.get)  # Line with 0 stops
max(stop_counts, key=stop_counts.get)  # Line with most stops
```

### Distribution by stop count range
```python
ranges = {}
for c in all_counts:
    if c <= 5: ranges['1-5'] += 1
    elif c <= 10: ranges['6-10'] += 1
    # ... etc
```
