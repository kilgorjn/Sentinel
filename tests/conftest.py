"""
Shared pytest fixtures.

Uses an in-memory SQLite engine so tests run without a real MySQL server.
The core modules use a module-level engine, so we patch core.db before any
import of storage/monitor happens.
"""

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Point all DB access at in-memory SQLite before importing app modules
_TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session", autouse=True)
def patch_db_engine():
    """Replace the SQLAlchemy engine with an in-memory SQLite instance."""
    from sqlalchemy.orm import sessionmaker
    import core.db as db_module

    # StaticPool ensures all threads (including FastAPI's threadpool) share
    # the same SQLite in-memory connection, so tables created by create_all
    # are visible to route handlers running in worker threads.
    engine = create_engine(
        _TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    with patch.object(db_module, "engine", engine), \
         patch.object(db_module, "SessionLocal", SessionLocal):
        db_module.Base.metadata.create_all(bind=engine)
        yield engine
        db_module.Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_tables(patch_db_engine):
    """Truncate all tables between tests for isolation."""
    yield
    from core.db import Base
    with patch_db_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def now():
    return datetime.now(timezone.utc)
