"""Database dependencies for FastAPI route handlers.

Each request gets a fresh SQLAlchemy session from the connection pool.
The session is always closed (and rolled back on error) when the request ends.
"""

import sqlite3
from typing import Generator
from sqlalchemy.orm import Session
from core.db import get_session


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for a route handler.

    Ensures the session is closed after every request, returning the
    connection back to the pool. Rolls back on unhandled exceptions.

    Usage:
        @router.get("/endpoint")
        def my_route(session: Session = Depends(get_db)):
            events = session.query(NewsEvent).all()
    """
    session = get_session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
