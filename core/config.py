"""Central configuration for the financial news monitoring system."""

import os
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent  # project root (Sentinel/)

# Ollama server
OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://jeffs-gaming-pc.lan:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:12b")  # Best accuracy; swap to "qwen3:8b" for speed
OLLAMA_TEMPERATURE = 0.3          # Low = consistent classification
OLLAMA_TIMEOUT = 60               # Seconds to wait for inference

# RSS feeds (free, no API key required)
RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",  # Yahoo Finance S&P
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",   # CNBC Top News
    "https://feeds.npr.org/1006/rss.xml",                      # NPR Business
    "https://seekingalpha.com/market_currents.xml",            # Seeking Alpha
]

# NewsAPI (optional — set to None to disable)
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", None)
NEWSAPI_QUERY = "Federal Reserve OR earnings OR jobs report OR market crash OR CPI"
NEWSAPI_DAILY_LIMIT = 95          # Hard ceiling (free tier = 100; 5 held in reserve)
NEWSAPI_MIN_INTERVAL_SECONDS = 900 # At least 15 min between calls (~96/day max)

# Classification thresholds
# Score needed for each tier (used internally; Ollama outputs HIGH/MEDIUM/LOW directly)
HIGH_CONFIDENCE_MIN = 0.6     # Minimum Ollama confidence to trust a HIGH classification
MEDIUM_CONFIDENCE_MIN = 0.5   # Minimum confidence for MEDIUM

# Spike detection — sliding window
SPIKE_WINDOW_MINUTES = 30     # Look-back window
SPIKE_HIGH_THRESHOLD = 3      # Number of HIGH events in window → SURGE alert

# Monitor loop
POLL_INTERVAL_SECONDS = 300   # Check every 5 minutes
MARKET_HOURS_ONLY = False     # Set to True to restrict polling to 9:00–17:00 ET Mon–Fri
MAX_ARTICLE_AGE_HOURS = 24    # Discard articles older than this

# Display timezone — used by the frontend for all timestamps
DISPLAY_TIMEZONE = os.getenv("DISPLAY_TIMEZONE", "America/New_York")

# Storage — overridable via env vars (used by Docker to point at a named volume)
DB_PATH  = os.getenv("SENTINEL_DB_PATH",  str(_ROOT / "news_events.db"))
LOG_PATH = os.getenv("SENTINEL_LOG_PATH", str(_ROOT / "financial_news.log"))

# Alerts — Slack (set webhook URL to enable, leave None to disable)
SLACK_WEBHOOK_URL = None      # e.g. "https://hooks.slack.com/services/..."
