"""Pydantic response schemas for the Sentinel API."""

from typing import Optional
from pydantic import BaseModel


class NewsEvent(BaseModel):
    id: int
    title: str
    source: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[str] = None
    classification: str
    confidence: Optional[float] = None
    reason: Optional[str] = None
    sentiment: Optional[str] = None
    actual_impact: Optional[str] = None
    created_at: str


class NewsEventDetail(NewsEvent):
    """Full event detail including RSS summary — returned by GET /api/events/{id}."""
    summary: Optional[str] = None


class SentimentBreakdown(BaseModel):
    positive: int = 0
    negative: int = 0
    neutral: int = 0


class ClassificationCount(BaseModel):
    classification: str
    count: int
    sentiment: SentimentBreakdown = SentimentBreakdown()


class SummaryResponse(BaseModel):
    window_hours: int
    counts: list[ClassificationCount]
    total: int
    overall_sentiment: str           # POSITIVE | NEGATIVE | NEUTRAL
    overall_sentiment_score: float   # weighted score in [-1.0, 1.0]


class SurgeResponse(BaseModel):
    surge_active: bool
    high_count_in_window: int
    window_minutes: int
    threshold: int


class HealthResponse(BaseModel):
    status: str          # "ok" | "degraded"
    ollama_reachable: bool
    ollama_url: str
    model: str


class NarrativeResponse(BaseModel):
    text: str
    generated_at: str
    cached: bool
    surge_active: bool


class ConfigResponse(BaseModel):
    display_timezone: str
    read_only: bool


class TimeseriesResponse(BaseModel):
    labels: list[str]           # ISO hour bucket strings
    high: list[int]
    medium: list[int]
    low: list[int]


class SentimentTimeseriesResponse(BaseModel):
    labels: list[str]                   # ISO hour bucket strings
    scores: list[Optional[float]]       # weighted sentiment score [-1, 1] or None for empty hours


class FeedInfo(BaseModel):
    """Feed metadata and status."""
    id: str
    name: str
    url: str
    feed_type: str              # e.g. "RSS 2.0", "Atom 1.0"
    active: bool
    added_at: str               # ISO timestamp


class FeedValidationResult(BaseModel):
    """Result of validating a feed URL."""
    valid: bool
    feed_type: str              # "RSS 2.0", "Atom 1.0", etc.
    version: str                # "rss20", "atom10", etc.
    entry_count: int
    sample_entries: list[dict]  # List of dicts with title, summary_length, has_timestamp, has_url
    errors: list[str]
    warnings: list[str] = []


class MarketSnapshot(BaseModel):
    symbol: str
    name: str
    region: str
    price: float
    prev_close: float
    change_pct: float
    high: Optional[float] = None
    low: Optional[float] = None
    fetched_at: str


class MarketVolatilitySignal(BaseModel):
    type: str           # "index_move" or "cross_market_correlation"
    severity: str       # "HIGH" or "MEDIUM"
    symbol: Optional[str] = None
    name: Optional[str] = None
    region: str
    change_pct: float
    message: str


class MarketDataResponse(BaseModel):
    snapshots: list[MarketSnapshot]
    signals: list[MarketVolatilitySignal]
    fetched_at: Optional[str] = None
    market_data_enabled: bool


class PredictionResponse(BaseModel):
    level: int                # 1=NORMAL, 2=MODERATE, 3=ELEVATED, 4=SURGE
    label: str                # NORMAL | MODERATE | ELEVATED | SURGE
    color: str                # green | yellow | orange | red
    volume: str               # expected login volume description
    action: str               # recommended action
    tooltip: str              # detailed action guidance (shown on hover)
    score: int                # raw composite score
    drivers: list[str]        # plain-English explanation of top contributors
    computed_at: str          # ISO timestamp


class AddFeedRequest(BaseModel):
    """Request to add a new feed."""
    url: str
    name: Optional[str] = None  # Auto-generated from feed if not provided


class AddFeedResponse(BaseModel):
    """Response after adding a feed."""
    feed: FeedInfo
    message: str
