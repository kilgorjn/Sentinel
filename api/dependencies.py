"""Database dependencies for FastAPI route handlers.

All routes automatically get a database session with connection pooling.
SQLAlchemy's connection pool handles concurrent access thread-safely.
"""

from core.db import get_session


def get_db():
    """Get a database session for a route handler.

    Returns a SQLAlchemy session with automatic connection pooling.
    The connection pool manages cleanup automatically.

    Usage:
        @router.get("/endpoint")
        def my_route(session = Depends(get_db)):
            events = session.query(NewsEvent).all()
    """
    return get_session()
