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


class TimeseriesResponse(BaseModel):
    labels: list[str]           # ISO hour bucket strings
    high: list[int]
    medium: list[int]
    low: list[int]
