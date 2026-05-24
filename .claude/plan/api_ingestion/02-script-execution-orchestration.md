# Script Execution Orchestration Plan

**Date**: 2026-05-22  
**Branch**: ingestion-olhovivo  

---

## Overview

Enable execution tracking for Python ingestion scripts via PostgreSQL logging, scheduled with cron on Ubuntu home lab. No alerts required — visibility only.

---

## Requirements

| Requirement | Status |
|-------------|--------|
| Execute scripts every 15 minutes (cron) | ✅ |
| Idempotent, parallelizable scripts | ✅ |
| Visibility into execution status/history | ✅ |
| PostgreSQL available on same machine | ✅ |
| No cloud costs | ✅ |
| No alerting (Slack/email) | ✅ |

---

## Architecture

```
sp-traffic/
├── .env                    # DB credentials
├── utils/                  # NEW: shared utilities package
│   └── __init__.py         # Exposes get_logger()
├── ingestion/              # Existing scripts
│   ├── olho_vivo/
│   │   ├── posicao_to_bucket/main.py
│   │   ├── posicao_staging/main.py
│   │   ├── linhas_staging/main.py
│   │   └── previsao_staging/main.py
├── .claude/
│   └── plan/               # NEW: this file
```

---

## Implementation Details

### 1. Database Schema

Create `script_runs` table in PostgreSQL:

```sql
CREATE TABLE script_runs (
    id SERIAL PRIMARY KEY,
    script_name VARCHAR(100) NOT NULL,
    run_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    succeeded BOOLEAN NOT NULL,
    error_message TEXT
);

-- Index for easy querying by script and time range
CREATE INDEX idx_script_runs_script_name ON script_runs(script_name);
CREATE INDEX idx_script_runs_run_at ON script_runs(run_at);
```

**Fields**:
- `id`: Auto-incrementing row ID
- `script_name`: Human-readable name (e.g., "olho_vivo_posicao")
- `run_at`: Timestamp when the run started

### 2. Shared Logger (`utils/logging.py`)

```python
"""Centralized logging utility for ingestion scripts."""

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
                error_message: Optional error message if failed
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
                        "error_message": error_message or "",
                    }
                )
                conn.commit()
    
    return Logger(script_name)


# Expose for imports
__all__ = ["get_logger"]
```

### 3. Script Usage Pattern

Each ingestion script:

```python
from utils.logging import get_logger

logger = get_logger("olho_vivo_posicao")

try:
    # ... ingestion logic ...
    logger.log_run(succeeded=True)
except Exception as e:
    logger.log_run(succeeded=False, error_message=str(e))
```

### 4. Cron Schedule

On Ubuntu home lab, add to crontab (`~/.crontab`):

```bash
# Run all ingestion scripts every 15 minutes
*/15 * * * * /usr/bin/python3 -m pip install --quiet -r requirements.txt && \
    cd /path/to/sp-traffic && \
    python ingestion/olho_vivo/posicao_to_bucket/main.py && \
    python ingestion/olho_vivo/posicao_staging/main.py && \
    python ingestion/olho_vivo/linhas_staging/main.py && \
    python ingestion/olho_vivo/previsao_staging/main.py
```

Or run scripts individually via separate cron entries.

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

## Next Steps

- [ ] Create `utils/` package with `logging.py`
- [ ] Add `script_runs` table to PostgreSQL
- [ ] Update `.env` with DB credentials (already done)
- [ ] Test logger in one script
- [ ] Set up cron job on Ubuntu home lab
- [ ] Verify logging works end-to-end

---

## Unresolved Questions

None.
