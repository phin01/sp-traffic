# Script Execution Orchestration Specification

**Date**: 2026-05-22  
**Branch**: ingestion-olhovivo  

---

## Summary

This specification defines how to add execution tracking for Python ingestion scripts using PostgreSQL logging, scheduled via cron on an Ubuntu home lab. The solution provides visibility into script runs (success/failure/timestamp) without requiring alerts or cloud infrastructure.

---

## Goals

1. Track every script execution with timestamp and success status
2. Capture error messages when scripts fail
3. Schedule scripts to run every 15 minutes via cron
4. Keep everything local (no cloud costs)
5. Maintain clean separation between ingestion logic and orchestration

---

## Non-Goals

- No alerting (Slack, email, etc.)
- No complex dashboards or UI
- No real-time monitoring
- No retry logic built into the scheduler

---

## Technical Requirements

| Requirement | Specification |
|-------------|---------------|
| Schedule interval | Every 15 minutes (`*/15 * * * *`) |
| Execution model | Idempotent, parallelizable scripts |
| Logging destination | PostgreSQL `script_runs` table |
| Error handling | Catch-all exceptions logged to DB |
| Shared infrastructure | `utils/logging.py` package |
| Environment | Ubuntu home lab with existing PostgreSQL |

---

## Database Schema

### Table: `script_runs`

```sql
CREATE TABLE script_runs (
    id SERIAL PRIMARY KEY,
    script_name VARCHAR(100) NOT NULL,
    run_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    succeeded BOOLEAN NOT NULL,
    error_message TEXT
);

-- Indexes for query performance
CREATE INDEX idx_script_runs_script_name ON script_runs(script_name);
CREATE INDEX idx_script_runs_run_at ON script_runs(run_at);
```

**Field definitions**:

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-incrementing row ID |
| `script_name` | VARCHAR(100) | NOT NULL | Human-readable script identifier (e.g., "olho_vivo_posicao") |
| `run_at` | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT NOW() | When the run started |
| `succeeded` | BOOLEAN | NOT NULL | Whether the script completed successfully |
| `error_message` | TEXT | NULLABLE | Error details if failed (TEXT to accommodate long stack traces) |

---

## Shared Logger Implementation

### File: `utils/logging.py`

```python
"""Centralized logging utility for ingestion scripts.

Each script imports and configures its own logger instance. No global state.
"""

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
from datetime import datetime


def get_logger(script_name: str):
    """Create a logger instance that writes runs to PostgreSQL.
    
    Args:
        script_name: Human-readable name of the script
        
    Returns:
        Logger instance with log_run() method
    """
    load_dotenv()
    
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", 5432))
    db_name = os.getenv("DB_NAME")
    
    engine = create_engine(
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}",
        pool_pre_ping=True,
        echo=False,
    )
    
    class Logger:
        def __init__(self, script_name: str):
            self.script_name = script_name
            self.engine = engine
        
        def log_run(self, succeeded: bool, error_message: str = None) -> None:
            """Log a script run to the database.
            
            Args:
                succeeded: Whether the script completed successfully
                error_message: Optional error message if failed (not used in current schema)
            """
            with self.engine.connect() as conn:
                conn.execute(
                    text("""
                        INSERT INTO script_runs (script_name, run_at, succeeded, error_message)
                        VALUES (:script_name, :run_at, :succeeded, :error_message)
                    """),
                    {
                        "script_name": self.script_name,
                        "run_at": datetime.now(),
                        "succeeded": succeeded,
                        "error_message": error_message or NULL,
                    }
                )
                conn.commit()
    
    return Logger(script_name)


__all__ = ["get_logger"]
```

**Key design decisions**:

1. **No shared state**: Each `Logger` instance creates its own connection pool
2. **Explicit import**: Scripts pass `script_name` explicitly (no env vars or globals)
3. **Simple API**: Single `log_run()` method with boolean success flag
4. **Dotenv integration**: Uses existing `.env` structure

---

## Script Integration Pattern

### Before (current):

```python
# ingestion/olho_vivo/posicao_to_bucket/main.py
import requests
from azure.storage.blob import BlobServiceClient

def main():
    # ... ingestion logic ...
    pass
```

### After:

```python
# ingestion/olho_vivo/posicao_to_bucket/main.py
from utils.logging import get_logger
from azure.storage.blob import BlobServiceClient

logger = get_logger("olho_vivo_posicao")  # Explicit, no global state

def main():
    try:
        # ... ingestion logic ...
        logger.log_run(succeeded=True)
    except Exception as e:
        logger.log_run(succeeded=False, error_message=str(e))
```

---

## Cron Configuration

### Crontab Entry (`~/.crontab`)

```bash
# Run all ingestion scripts every 15 minutes
*/15 * * * * /usr/bin/python3 -m pip install --quiet -r requirements.txt && \
    cd /path/to/sp-traffic && \
    python ingestion/olho_vivo/posicao_to_bucket/main.py && \
    python ingestion/olho_vivo/posicao_staging/main.py && \
    python ingestion/olho_vivo/linhas_staging/main.py && \
    python ingestion/olho_vivo/previsao_staging/main.py
```

### Alternative: Individual cron entries

For better visibility and easier debugging, run each script separately:

```bash
# 15 minutes past the hour - posicao_to_bucket
*/15 * * * * /usr/bin/python3 -m pip install --quiet -r requirements.txt && \
    cd /path/to/sp-traffic && \
    python ingestion/olho_vivo/posicao_to_bucket/main.py

# 30 minutes past the hour - posicao_staging
*/30 * * * * /usr/bin/python3 -m pip install --quiet -r requirements.txt && \
    cd /path/to/sp-traffic && \
    python ingestion/olho_vivo/posicao_staging/main.py

# 45 minutes past the hour - linhas_staging
*/45 * * * * /usr/bin/python3 -m pip install --quiet -r requirements.txt && \
    cd /path/to/sp-traffic && \
    python ingestion/olho_vivo/linhas_staging/main.py

# Every 15 minutes - previsao_staging (same interval as first)
*/15 * * * * /usr/bin/python3 -m pip install --quiet -r requirements.txt && \
    cd /path/to/sp-traffic && \
    python ingestion/olho_vivo/previsao_staging/main.py
```

---

## Querying Execution History

### Recent runs by script:

```sql
SELECT 
    script_name,
    run_at,
    succeeded
FROM script_runs
WHERE script_name = 'olho_vivo_posicao'
ORDER BY run_at DESC
LIMIT 10;
```

### Failed runs only:

```sql
SELECT 
    script_name,
    run_at,
    error_message
FROM script_runs
WHERE succeeded = false
ORDER BY run_at DESC;
```

### Run statistics (last 24 hours):

```sql
SELECT 
    script_name,
    COUNT(*) as total_runs,
    SUM(CASE WHEN succeeded THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN NOT succeeded THEN 1 ELSE 0 END) as failed
FROM script_runs
WHERE run_at >= NOW() - INTERVAL '24 hours'
GROUP BY script_name;
```

---

## Testing Checklist

- [ ] Create `utils/` directory and `__init__.py`
- [ ] Create `utils/logging.py` with `get_logger()` function
- [ ] Add `script_runs` table to PostgreSQL
- [ ] Update `.env` with DB credentials (already done)
- [ ] Test logger in one script (e.g., `posicao_to_bucket/main.py`)
- [ ] Verify log entry appears in database immediately
- [ ] Set up cron job on Ubuntu home lab
- [ ] Run scripts manually and verify logging works end-to-end

---

## Future Enhancements (Out of Scope)

- Alerting via Slack/email when failures occur
- Richer metadata (duration, input/output files)
- Dashboard UI for execution history
- Retry logic with exponential backoff
- Script dependency management
