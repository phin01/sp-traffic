"""Centralized logging utility for ingestion scripts.

Each script imports and configures its own logger instance. No global state.
"""

from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv
import os
from datetime import datetime


def get_logger(script_name: str):
    """Create a logger instance that writes runs to PostgreSQL.

    Args:
        script_name: Human-readable name of the script

    Returns:
        Logger instance with log_run() method
    """
    load_dotenv(dotenv_path=find_dotenv())  # Load DB credentials from .env file

    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", 5432))
    db_name = os.getenv("DB_NAME")

    print(f"Creating logger for script: {db_name} at {db_host}:{db_port} as {db_user}")

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
                        INSERT INTO logging.script_runs (script_name, run_at, succeeded, error_message)
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


__all__ = ["get_logger"]
