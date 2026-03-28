"""Sentinel REST API — exposes classified news events to the frontend."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, APIRouter, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core import config
from api.models import (
    NewsEvent, SummaryResponse, ClassificationCount, SentimentBreakdown,
    SurgeResponse, HealthResponse, NarrativeResponse, ConfigResponse,
    TimeseriesResponse, SentimentTimeseriesResponse,
    FeedInfo, FeedValidationResult, AddFeedRequest, AddFeedResponse,
    MarketSnapshot, MarketVolatilitySignal, MarketDataResponse,
)
from api.dependencies import get_db

app = FastAPI(title="Sentinel API", version="1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",          # Vite dev server
        "http://localhost:5500",          # VSCode Live Server
        "http://127.0.0.1:5500",          # VSCode Live Server (alternative)
        "http://localhost:8000",          # Local API
        "http://docker-apps.lan:8082",    # Docker apps server
    ],
    allow_methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
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
def get_summary(hours: int = Query(24, ge=1, le=720)):
    """Classification counts with per-tier sentiment breakdown and weighted overall sentiment."""
    conn = get_db()
    rows = conn.execute(
        f"""
        SELECT classification, COALESCE(sentiment, 'NEUTRAL') AS sentiment, COUNT(*) AS cnt
        FROM news_events
        WHERE created_at >= datetime('now', '-{hours} hours')
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
        window_hours=hours,
        counts=counts,
        total=sum(c.count for c in counts),
        overall_sentiment=overall,
        overall_sentiment_score=round(score, 3),
    )


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
def get_timeseries(hours: int = Query(24, ge=1, le=720)):
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


@router.get("/events/sentiment-timeseries", response_model=SentimentTimeseriesResponse)
def get_sentiment_timeseries(hours: int = Query(24, ge=1, le=720)):
    """Hourly weighted sentiment scores for the last N hours."""
    from collections import defaultdict
    conn = get_db()

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    buckets = [(now - timedelta(hours=i)).strftime("%Y-%m-%dT%H:00:00Z") for i in range(hours - 1, -1, -1)]

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        """
        SELECT strftime('%Y-%m-%dT%H:00:00', published_at) AS bucket,
               classification,
               COALESCE(sentiment, 'NEUTRAL') AS sentiment,
               COUNT(*) AS cnt
        FROM news_events
        WHERE published_at >= ?
        GROUP BY bucket, classification, sentiment
        ORDER BY bucket ASC
        """,
        (cutoff,),
    ).fetchall()

    bucket_weighted: dict = defaultdict(float)
    bucket_total: dict = defaultdict(float)
    for row in rows:
        bucket_key = row[0] + "Z"
        cls  = row[1]
        sent = (row[2] or "NEUTRAL").upper()
        cnt  = row[3]
        w = _CLS_WEIGHT.get(cls, 1)
        bucket_weighted[bucket_key] += w * _SENT_SCORE.get(sent, 0) * cnt
        bucket_total[bucket_key]    += w * cnt

    scores = [
        round(bucket_weighted[b] / bucket_total[b], 3) if bucket_total[b] > 0 else None
        for b in buckets
    ]
    return SentimentTimeseriesResponse(labels=buckets, scores=scores)


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

    # Fetch latest market snapshots for LLM context
    market_ctx = None
    if config.MARKET_DATA_ENABLED:
        try:
            from core import storage as market_storage
            market_ctx = market_storage.get_latest_market_data()
        except Exception:
            pass

    text = classifier.summarize(events, surge_active=surge_active, market_context=market_ctx)
    now_str = datetime.now(timezone.utc).isoformat()

    cs.set_meta("narrative_text", text)
    cs.set_meta("narrative_generated_at", now_str)
    cs.set_meta("narrative_event_count", current_count)
    cs.set_meta("narrative_surge_state", str(surge_active))

    return NarrativeResponse(text=text, generated_at=now_str, cached=False, surge_active=surge_active)


@router.get("/feeds", response_model=list[FeedInfo])
def list_feeds():
    """Get all configured RSS feeds (active only)."""
    from core import feeds_manager
    feeds = feeds_manager.load_feeds()
    return [
        FeedInfo(
            id=f["id"],
            name=f["name"],
            url=f["url"],
            feed_type=f.get("feed_type", "Unknown"),
            active=f.get("active", True),
            added_at=f.get("added_at", ""),
        )
        for f in feeds
    ]


@router.post("/feeds/validate", response_model=FeedValidationResult)
def validate_feed(request: AddFeedRequest):
    """Test a feed URL and detect its type.

    Auto-detects feed format (RSS 2.0, Atom 1.0, etc.) and validates
    it has required fields (title, summary, link, timestamp).
    """
    from core import feed_handlers

    result = feed_handlers.detect_feed_type(request.url)

    # Convert handler object to None for serialization
    handler = result.pop("handler")
    result["warnings"] = []

    if result["valid"] and not (result.get("sample_entries") and
                                any(e["summary_length"] > 100 for e in result["sample_entries"])):
        result["warnings"].append(
            "Feed entries have short or missing summaries. "
            "Classifier will have limited context."
        )

    return FeedValidationResult(**result)


@router.post("/feeds", response_model=AddFeedResponse)
def add_feed(request: AddFeedRequest):
    """Add a new RSS feed after validating it."""
    from core import feed_handlers, feeds_manager

    # Validate the feed first
    validation = feed_handlers.detect_feed_type(request.url)

    if not validation["valid"]:
        raise HTTPException(
            status_code=400,
            detail=f"Feed validation failed: {'; '.join(validation['errors'])}",
        )

    # Add to database
    feed_name = request.name or validation.get("feed_type", "Unknown Feed")
    feed_type = validation.get("feed_type", "Unknown")

    try:
        new_feed = feeds_manager.add_feed(
            url=request.url,
            name=feed_name,
            feed_type=feed_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return AddFeedResponse(
        feed=FeedInfo(
            id=new_feed["id"],
            name=new_feed["name"],
            url=new_feed["url"],
            feed_type=new_feed.get("feed_type", "Unknown"),
            active=new_feed.get("active", True),
            added_at=new_feed.get("added_at", ""),
        ),
        message=f"Feed added: {feed_name}",
    )


@router.delete("/feeds/{feed_id}")
def delete_feed(feed_id: str):
    """Remove a feed by ID."""
    from core import feeds_manager

    success = feeds_manager.delete_feed(feed_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Feed {feed_id} not found")

    return {"message": f"Feed {feed_id} deleted"}


@router.patch("/feeds/{feed_id}")
def toggle_feed(feed_id: str, active: bool = Query(..., description="Enable or disable feed")):
    """Enable/disable a feed."""
    from core import feeds_manager

    feed = feeds_manager.toggle_feed(feed_id, active)
    if not feed:
        raise HTTPException(status_code=404, detail=f"Feed {feed_id} not found")

    return {
        "feed_id": feed_id,
        "active": active,
        "message": f"Feed {'enabled' if active else 'disabled'}",
    }


@router.get("/market/indices", response_model=MarketDataResponse)
def get_market_indices():
    """Latest snapshots for all tracked indices + active volatility signals."""
    from core import market_data, storage as ms

    configured = config.MARKET_DATA_ENABLED
    snapshots_raw = ms.get_latest_market_data() if configured else []

    snapshots = [
        MarketSnapshot(
            symbol=s["symbol"],
            name=s.get("name", ""),
            region=s.get("region", ""),
            price=s.get("price", 0),
            prev_close=s.get("prev_close", 0),
            change_pct=s.get("change_pct", 0),
            high=s.get("high"),
            low=s.get("low"),
            fetched_at=s.get("fetched_at", ""),
        )
        for s in snapshots_raw
    ]

    signals_raw = market_data.detect_volatility(snapshots_raw) if snapshots_raw else []
    signals = [
        MarketVolatilitySignal(
            type=sig["type"],
            severity=sig["severity"],
            symbol=sig.get("symbol"),
            name=sig.get("name"),
            region=sig["region"],
            change_pct=sig["change_pct"],
            message=sig["message"],
        )
        for sig in signals_raw
    ]

    fetched_at = snapshots_raw[0]["fetched_at"] if snapshots_raw else None

    return MarketDataResponse(
        snapshots=snapshots,
        signals=signals,
        fetched_at=fetched_at,
        market_data_enabled=configured,
    )


@router.get("/market/history")
def get_market_history(
    symbol: str = Query(..., description="Ticker symbol, e.g. ^N225"),
    hours: int = Query(24, ge=1, le=720, description="Look-back hours"),
):
    """Historical snapshots for a specific symbol (for charting)."""
    from core import storage as ms

    rows = ms.get_market_history(symbol, hours)
    return [
        MarketSnapshot(
            symbol=r["symbol"],
            name=r.get("name", ""),
            region=r.get("region", ""),
            price=r.get("price", 0),
            prev_close=r.get("prev_close", 0),
            change_pct=r.get("change_pct", 0),
            high=r.get("high"),
            low=r.get("low"),
            fetched_at=r.get("fetched_at", ""),
        )
        for r in rows
    ]


app.include_router(router)

# Serve the built Vue frontend with SPA fallback
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
_INDEX = _DIST / "index.html"

if _DIST.exists():
    # Catch-all route for SPA: serve index.html for all non-API routes
    # This allows Vue Router to handle routing on the client side
    @app.get("/{path:path}")
    async def serve_spa(path: str):
        """Serve static files or fall back to index.html for SPA routing."""
        # Don't intercept API calls
        if path.startswith("api/"):
            return HTTPException(status_code=404, detail="Not found")

        # Try to serve static file first (CSS, JS, images, etc.)
        file_path = _DIST / path
        if file_path.is_file():
            return FileResponse(file_path)

        # Fall back to index.html for client-side routing
        if _INDEX.exists():
            return FileResponse(_INDEX)

        return HTTPException(status_code=404, detail="Not found")
