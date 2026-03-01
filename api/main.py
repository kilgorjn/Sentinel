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
    NewsEvent, SummaryResponse, ClassificationCount, SentimentBreakdown,
    SurgeResponse, HealthResponse, NarrativeResponse, ConfigResponse, TimeseriesResponse,
    SentimentScore,
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


_CLS_WEIGHT   = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
_SENT_SCORE   = {"POSITIVE": 1, "NEGATIVE": -1, "NEUTRAL": 0}
_SENT_THRESH  = 0.10   # score must exceed ±10% to be called directional


@router.get("/events/summary", response_model=SummaryResponse)
def get_summary():
    """Classification counts with per-tier sentiment breakdown and weighted overall sentiment."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT classification, COALESCE(sentiment, 'NEUTRAL') AS sentiment, COUNT(*) AS cnt
        FROM news_events
        WHERE created_at >= datetime('now', '-24 hours')
        GROUP BY classification, sentiment
        """
    ).fetchall()

    # Roll up into per-classification buckets
    from collections import defaultdict
    buckets: dict = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0, "total": 0})
    weighted_score = 0.0
    weighted_total = 0.0

    for row in rows:
        cls  = row["classification"]
        sent = (row["sentiment"] or "NEUTRAL").upper()
        cnt  = row["cnt"]
        key  = sent.lower() if sent in ("POSITIVE", "NEGATIVE") else "neutral"
        buckets[cls][key]    += cnt
        buckets[cls]["total"] += cnt
        w = _CLS_WEIGHT.get(cls, 1)
        weighted_score += w * _SENT_SCORE.get(sent, 0) * cnt
        weighted_total += w * cnt

    counts = [
        ClassificationCount(
            classification=cls,
            count=data["total"],
            sentiment=SentimentBreakdown(
                positive=data["positive"],
                negative=data["negative"],
                neutral=data["neutral"],
            ),
        )
        for cls, data in buckets.items()
    ]

    score = (weighted_score / weighted_total) if weighted_total else 0.0
    if score > _SENT_THRESH:
        overall = "POSITIVE"
    elif score < -_SENT_THRESH:
        overall = "NEGATIVE"
    else:
        overall = "NEUTRAL"

    return SummaryResponse(
        window_hours=24,
        counts=counts,
        total=sum(c.count for c in counts),
        overall_sentiment=overall,
        overall_sentiment_score=round(score, 3),
    )


@router.get("/events/{event_id}/sentiments", response_model=list[SentimentScore])
def get_event_sentiments(event_id: int):
    """Return per-model sentiment scores for a single event."""
    conn = get_db()
    rows = conn.execute(
        "SELECT model, sentiment, score FROM sentiment_scores WHERE event_id = ? ORDER BY model",
        (event_id,),
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="No sentiment scores found for this event")
    return [dict(r) for r in rows]


@router.get("/surge", response_model=SurgeResponse)
def get_surge():
    """Current surge status based on HIGH events in the spike detection window."""
    conn = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=config.SPIKE_WINDOW_MINUTES)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM news_events WHERE classification = 'HIGH' AND published_at >= ?",
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


@router.get("/events/timeseries", response_model=TimeseriesResponse)
def get_timeseries(hours: int = Query(24, ge=1, le=168)):
    """Hourly event counts per classification for the last N hours."""
    conn = get_db()

    # Build a complete list of hour buckets (UTC, with Z suffix so the browser parses them correctly)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    buckets = [(now - timedelta(hours=i)).strftime("%Y-%m-%dT%H:00:00Z") for i in range(hours - 1, -1, -1)]

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """
        SELECT strftime('%Y-%m-%dT%H:00:00', published_at) AS bucket,
               classification,
               COUNT(*) AS cnt
        FROM news_events
        WHERE published_at >= ?
        GROUP BY bucket, classification
        ORDER BY bucket ASC
        """,
        (cutoff,),
    ).fetchall()

    # Index results by (bucket, classification); SQL returns without Z so we add it for matching
    data: dict[tuple[str, str], int] = {}
    for row in rows:
        data[(row[0] + "Z", row[1])] = row[2]

    high   = [data.get((b, "HIGH"),   0) for b in buckets]
    medium = [data.get((b, "MEDIUM"), 0) for b in buckets]
    low    = [data.get((b, "LOW"),    0) for b in buckets]

    return TimeseriesResponse(labels=buckets, high=high, medium=medium, low=low)


@router.get("/config", response_model=ConfigResponse)
def get_config():
    """Frontend display settings derived from server config."""
    return ConfigResponse(display_timezone=config.DISPLAY_TIMEZONE)


NARRATIVE_TTL_SECONDS = 900  # Regenerate at most every 15 minutes


@router.get("/events/narrative", response_model=NarrativeResponse)
def get_narrative():
    """AI-generated narrative summary of recent events, with surge-aware context."""
    from core import classifier, storage as cs
    conn = get_db()

    # Current 24h event count and surge state (mirrors /surge logic)
    count_row = conn.execute(
        "SELECT COUNT(*) FROM news_events WHERE created_at >= datetime('now', '-24 hours')"
    ).fetchone()
    current_count = str(count_row[0]) if count_row else "0"

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=config.SPIKE_WINDOW_MINUTES)).isoformat()
    surge_row = conn.execute(
        "SELECT COUNT(*) FROM news_events WHERE classification = 'HIGH' AND published_at >= ?",
        (cutoff,),
    ).fetchone()
    surge_active = (surge_row[0] if surge_row else 0) >= config.SPIKE_HIGH_THRESHOLD

    # Check cache — skip Ollama if nothing has changed and cache is fresh
    cached_text  = cs.get_meta("narrative_text")
    cached_at    = cs.get_meta("narrative_generated_at")
    cached_count = cs.get_meta("narrative_event_count")
    cached_surge = cs.get_meta("narrative_surge_state")

    age_ok = False
    if cached_at:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached_at)).total_seconds()
        age_ok = age < NARRATIVE_TTL_SECONDS

    if (cached_text and age_ok
            and cached_count == current_count
            and cached_surge == str(surge_active)):
        return NarrativeResponse(
            text=cached_text, generated_at=cached_at, cached=True, surge_active=surge_active
        )

    # Fetch events for summarization — HIGH first, then MEDIUM, cap at 25
    rows = conn.execute(
        """SELECT title, classification, reason FROM news_events
           WHERE created_at >= datetime('now', '-24 hours')
           ORDER BY CASE classification WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                    created_at DESC
           LIMIT 25"""
    ).fetchall()
    events = [{"title": r[0], "classification": r[1], "reason": r[2]} for r in rows]

    text = classifier.summarize(events, surge_active=surge_active)
    now_str = datetime.now(timezone.utc).isoformat()

    cs.set_meta("narrative_text", text)
    cs.set_meta("narrative_generated_at", now_str)
    cs.set_meta("narrative_event_count", current_count)
    cs.set_meta("narrative_surge_state", str(surge_active))

    return NarrativeResponse(text=text, generated_at=now_str, cached=False, surge_active=surge_active)


app.include_router(router)

# Serve the built Vue frontend — must be mounted LAST so API routes take priority
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
