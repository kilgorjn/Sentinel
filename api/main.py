"""Sentinel REST API — exposes classified news events to the frontend."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, APIRouter, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core import config
from api.models import (
    NewsEvent, SummaryResponse, ClassificationCount,
    SurgeResponse, HealthResponse,
)
from api.dependencies import get_db

app = FastAPI(title="Sentinel API", version="1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # Vite dev server
    allow_methods=["GET"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api")


@router.get("/events", response_model=list[NewsEvent])
def get_events(
    classification: Optional[str] = Query(None, description="Filter: HIGH, MEDIUM, or LOW"),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    """Return recent classified events from SQLite, newest-first."""
    conn = get_db()
    if classification:
        classification = classification.upper()
        if classification not in ("HIGH", "MEDIUM", "LOW"):
            raise HTTPException(status_code=400, detail="classification must be HIGH, MEDIUM, or LOW")
        rows = conn.execute(
            "SELECT * FROM news_events WHERE classification = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (classification, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM news_events ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/events/summary", response_model=SummaryResponse)
def get_summary():
    """Classification counts for the last 24 hours."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT classification, COUNT(*) as count
        FROM news_events
        WHERE created_at >= datetime('now', '-24 hours')
        GROUP BY classification
        ORDER BY count DESC
        """
    ).fetchall()
    counts = [ClassificationCount(classification=r["classification"], count=r["count"]) for r in rows]
    return SummaryResponse(
        window_hours=24,
        counts=counts,
        total=sum(c.count for c in counts),
    )


@router.get("/surge", response_model=SurgeResponse)
def get_surge():
    """Current surge status based on HIGH events in the spike detection window."""
    conn = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=config.SPIKE_WINDOW_MINUTES)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM news_events WHERE classification = 'HIGH' AND created_at >= ?",
        (cutoff,),
    ).fetchone()
    high_count = row["cnt"] if row else 0
    return SurgeResponse(
        surge_active=high_count >= config.SPIKE_HIGH_THRESHOLD,
        high_count_in_window=high_count,
        window_minutes=config.SPIKE_WINDOW_MINUTES,
        threshold=config.SPIKE_HIGH_THRESHOLD,
    )


@router.get("/health", response_model=HealthResponse)
def get_health():
    """Ping Ollama to verify the inference backend is reachable."""
    try:
        resp = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
        reachable = resp.status_code == 200
    except Exception:
        reachable = False
    return HealthResponse(
        status="ok" if reachable else "degraded",
        ollama_reachable=reachable,
        ollama_url=config.OLLAMA_URL,
        model=config.OLLAMA_MODEL,
    )


app.include_router(router)

# Serve the built Vue frontend — must be mounted LAST so API routes take priority
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
