"""Shared SQLite connection for FastAPI route handlers."""

import sqlite3
from core import storage


def get_db() -> sqlite3.Connection:
    """Get the properly configured database connection from storage.

    This ensures the API uses the same connection with WAL mode,
    timeout settings, and synchronous pragmas as the monitor.
    """
    conn = storage._get_conn()
    conn.row_factory = sqlite3.Row
    return conn
