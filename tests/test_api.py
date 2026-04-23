"""Tests for the FastAPI REST layer — focuses on GET /api/events/{id}."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from api.main import app
from api.dependencies import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(engine):
    """Return a SQLAlchemy session bound to the test engine."""
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return Session()


def _override_get_db(engine):
    """Return a FastAPI dependency override that yields a test-engine session."""
    def _get_db():
        session = _make_session(engine)
        try:
            yield session
        finally:
            session.close()
    return _get_db


def _insert_event(engine, *, title="Test Headline", summary="Raw RSS summary.",
                  classification="HIGH", reason="LLM reason text.",
                  sentiment="NEGATIVE", confidence=0.9,
                  url="https://example.com/article"):
    """Insert a NewsEvent row directly and return its id."""
    from core.db import NewsEvent as NewsEventModel
    session = _make_session(engine)
    row = NewsEventModel(
        title=title,
        summary=summary,
        source="Reuters",
        url=url,
        classification=classification,
        reason=reason,
        sentiment=sentiment,
        confidence=confidence,
        published_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.commit()
    event_id = row.id
    session.close()
    return event_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(patch_db_engine):
    """TestClient with the DB dependency pointing at the in-memory SQLite engine."""
    app.dependency_overrides[get_db] = _override_get_db(patch_db_engine)
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/events/{id}
# ---------------------------------------------------------------------------

class TestGetEventDetail:
    def test_returns_200_with_full_detail(self, client, patch_db_engine):
        event_id = _insert_event(patch_db_engine)
        resp = client.get(f"/api/events/{event_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == event_id
        assert data["title"] == "Test Headline"
        assert data["summary"] == "Raw RSS summary."
        assert data["classification"] == "HIGH"
        assert data["reason"] == "LLM reason text."
        assert data["sentiment"] == "NEGATIVE"

    def test_summary_field_present_even_when_none(self, client, patch_db_engine):
        from core.db import NewsEvent as NewsEventModel
        session = _make_session(patch_db_engine)
        row = NewsEventModel(
            title="No Summary Event",
            summary=None,
            source="AP",
            url="https://example.com/nosummary",
            classification="LOW",
            confidence=0.5,
            published_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.commit()
        event_id = row.id
        session.close()

        resp = client.get(f"/api/events/{event_id}")
        assert resp.status_code == 200
        assert resp.json()["summary"] is None

    def test_returns_404_for_missing_id(self, client):
        resp = client.get("/api/events/999999")
        assert resp.status_code == 404

    def test_confidence_rounded_correctly(self, client, patch_db_engine):
        event_id = _insert_event(patch_db_engine, confidence=0.753)
        resp = client.get(f"/api/events/{event_id}")
        assert resp.status_code == 200
        assert resp.json()["confidence"] == pytest.approx(0.753)

    def test_url_preserved(self, client, patch_db_engine):
        event_id = _insert_event(patch_db_engine, url="https://wsj.com/story/123")
        resp = client.get(f"/api/events/{event_id}")
        assert resp.json()["url"] == "https://wsj.com/story/123"
