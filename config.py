"""Central configuration for the financial news monitoring system."""

# Ollama server
OLLAMA_URL = "http://jeffs-gaming-pc.lan:11434"
OLLAMA_MODEL = "gemma3:12b"       # Best accuracy; swap to "qwen3:8b" for speed
OLLAMA_TEMPERATURE = 0.3          # Low = consistent classification
OLLAMA_TIMEOUT = 60               # Seconds to wait for inference

# RSS feeds (free, no API key required)
RSS_FEEDS = [
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",       # WSJ Markets
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",  # Yahoo Finance S&P
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",   # CNBC Top News
    "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",  # Reuters Finance
]

# NewsAPI (optional — set to None to disable)
NEWSAPI_KEY = None        # e.g. "abc123..."
NEWSAPI_QUERY = "Federal Reserve OR earnings OR jobs report OR market crash OR CPI"

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

# Storage
DB_PATH = "news_events.db"
LOG_PATH = "financial_news.log"

# Alerts — Slack (set webhook URL to enable, leave None to disable)
SLACK_WEBHOOK_URL = None      # e.g. "https://hooks.slack.com/services/..."
