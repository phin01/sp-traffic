# Upload CSV to PostgreSQL (Staging Tables)

## Quick Script Pattern

```python
import os, csv
from dotenv import find_dotenv, load_dotenv
import pandas as pd
from sqlalchemy import create_engine

# Load env vars from .env file at project root
dotenv_path = find_dotenv('.env')
if not dotenv_path:
    raise FileNotFoundError(".env file not found")
load_dotenv(dotenv_path)

DB_USER = os.environ['DB_USER']
DB_PASSWORD = os.environ['DB_PASSWORD']
DB_HOST = os.environ['DB_HOST']
DB_PORT = os.environ['DB_PORT']
DB_NAME = os.environ['DB_NAME']

# Create engine
engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

# Read CSV file (adjust path and fieldnames as needed)
csv_path = 'path/to/file.csv'  # relative to project root
if not os.path.exists(csv_path):
    raise FileNotFoundError(f"CSV file not found: {csv_path}")

df = pd.read_csv(csv_path)

# Create table with specified schema
table_name = 'schema.table_name'  # e.g., 'staging.stg_short_lines'

# Drop existing table if it exists
try:
    engine.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
except Exception:
    pass

# Create table from DataFrame using native Pandas to SQL function
df.to_sql(
    table_name,
    con=engine,
    if_exists='replace',
    index=False,
    schema='staging'
)

print(f"Inserted {len(df)} rows into {table_name}")
```

## Customization Guide

### Change table name
Replace `table_name = 'schema.table_name'` with your desired schema.table_name.

### Adjust CSV path
Update the `csv_path` variable to point to your file (relative to project root).

### Modify DataFrame columns
The column names in your CSV will automatically become the table columns. You can:
- Rename columns before saving: `df.rename(columns={'old': 'new'}, inplace=True)`
- Select specific columns: `df = df[['col1', 'col2']]`
