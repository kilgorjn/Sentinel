"""SQLAlchemy database models and connection management."""

import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Index, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

# Get database URL from environment or construct from config
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"mysql+pymysql://sentinel:sentinel@localhost:3306/sentinel"
)

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    echo=False,
)

# Session factory
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

Base = declarative_base()


class RawArticle(Base):
    """Raw fetched article, persisted before classification."""
    __tablename__ = "raw_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title_hash = Column(String(64), unique=True, nullable=False)  # SHA256 of normalized title — dedup key
    title = Column(String(500), nullable=False)
    source = Column(String(100))
    url = Column(String(1000))
    summary = Column(Text)
    published_at = Column(DateTime)
    fetched_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_raw_fetched_at", "fetched_at"),
        Index("idx_raw_published_at", "published_at"),
    )

    def to_dict(self):
        """Return a dict for internal pipeline use.

        published_at and fetched_at are returned as datetime objects (not ISO
        strings) so downstream code (classifier, spike detector, save_event)
        can use them directly without reparsing.
        """
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "summary": self.summary,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
        }


class NewsEvent(Base):
    """Classified financial news event."""
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    source = Column(String(100))
    url = Column(String(1000))
    published_at = Column(DateTime, nullable=False)
    classification = Column(String(20), nullable=False)  # HIGH, MEDIUM, LOW
    confidence = Column(Float, default=0.0)
    reason = Column(String(500))
    sentiment = Column(String(20))  # POSITIVE, NEGATIVE, NEUTRAL
    actual_impact = Column(String(500))  # Manual annotation
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_classification", "classification"),
        Index("idx_created_at", "created_at"),
        Index("idx_published_at", "published_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.replace(tzinfo=timezone.utc).isoformat() if self.published_at else None,
            "classification": self.classification,
            "confidence": self.confidence,
            "reason": self.reason,
            "sentiment": self.sentiment,
            "actual_impact": self.actual_impact,
            "created_at": self.created_at.replace(tzinfo=timezone.utc).isoformat() if self.created_at else None,
        }


class Feed(Base):
    """Configured RSS feed."""
    __tablename__ = "feeds"

    id = Column(String(36), primary_key=True)
    url = Column(String(1000), nullable=False)
    url_hash = Column(String(64), unique=True, nullable=False)  # SHA256 hash for unique constraint
    name = Column(String(200), nullable=False)
    feed_type = Column(String(50))  # RSS 2.0, Atom 1.0, etc.
    active = Column(Boolean, default=True)
    added_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "name": self.name,
            "feed_type": self.feed_type,
            "active": self.active,
            "added_at": self.added_at.replace(tzinfo=timezone.utc).isoformat() if self.added_at else None,
        }  # Note: url_hash is intentionally excluded (internal field)


class Meta(Base):
    """Key-value store for metadata (cache, state, etc.)."""
    __tablename__ = "meta"

    key = Column(String(100), primary_key=True)
    value = Column(String(2000), nullable=False)

    def to_dict(self):
        return {"key": self.key, "value": self.value}


class MarketSnapshot(Base):
    """Market index snapshot."""
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    name = Column(String(200))
    region = Column(String(50))
    price = Column(Float)
    prev_close = Column(Float)
    change_pct = Column(Float)
    high = Column(Float)
    low = Column(Float)
    fetched_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_market_symbol", "symbol"),
        Index("idx_market_fetched", "fetched_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "name": self.name,
            "region": self.region,
            "price": self.price,
            "prev_close": self.prev_close,
            "change_pct": self.change_pct,
            "high": self.high,
            "low": self.low,
            "fetched_at": self.fetched_at.replace(tzinfo=timezone.utc).isoformat() if self.fetched_at else None,
        }


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_session():
    """Get a new database session."""
    return SessionLocal()
