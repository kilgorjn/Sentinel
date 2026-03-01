# Sentinel — Financial News Monitor

Monitors financial news feeds, classifies articles by market impact using a local Ollama LLM, and fires alerts when a burst of high-impact events is detected. Designed to give brokerage ops teams advance warning before login volume spikes hit.

## How it works

```
RSS Feeds / NewsAPI
      ↓
  feeds.py        — fetch & deduplicate articles every 5 minutes
      ↓
  classifier.py   — ask local Ollama to classify each article HIGH / MEDIUM / LOW
      ↓
  spike_detector  — sliding 30-min window; SURGE alert when ≥3 HIGH events accumulate
      ↓
  storage.py      — write to SQLite (accuracy tracking) + JSON log (Splunk ingestion)
      ↓
  alerts.py       — color-coded console output; optional Slack webhook
```

The spike detection mirrors a login-volume spike pattern: instead of counting logins per time window, it counts HIGH-impact news events. A burst of major events is a leading indicator that user logins will spike within 10–15 minutes.

## Prerequisites

- Python 3.9+
- [Ollama](https://ollama.ai) running on a host reachable by this machine (default config points to `jeffs-gaming-pc.lan:11434`)
- A model pulled on that Ollama server — `gemma3:12b` is the default; `qwen3:8b` is a faster alternative

Check available models on your server:
```bash
curl http://jeffs-gaming-pc.lan:11434/api/tags | python3 -m json.tool
```

## Installation

```bash
git clone <repo-url>
cd sentinel

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## Configuration

All settings live in [config.py](config.py). The key ones to review before first run:

| Setting | Default | Description |
|---------|---------|-------------|
| `OLLAMA_URL` | `http://jeffs-gaming-pc.lan:11434` | Ollama server address |
| `OLLAMA_MODEL` | `gemma3:12b` | Model to use for classification |
| `RSS_FEEDS` | WSJ, CNBC, Reuters, Yahoo | News sources (free, no API key) |
| `NEWSAPI_KEY` | `None` | Optional — 100 req/day free at newsapi.org |
| `SPIKE_WINDOW_MINUTES` | `30` | Rolling window for burst detection |
| `SPIKE_HIGH_THRESHOLD` | `3` | HIGH events in window before SURGE fires |
| `POLL_INTERVAL_SECONDS` | `300` | How often to fetch news (5 minutes) |
| `MARKET_HOURS_ONLY` | `True` | Skip nights and weekends |
| `SLACK_WEBHOOK_URL` | `None` | Set to enable Slack alerts |

## Usage

### Smoke test
Classifies 5 built-in sample articles and exits — useful for verifying Ollama connectivity and classification quality before running live:

```bash
python monitor.py --test
```

Expected output:
```
[HIGH]   Federal Reserve Cuts Interest Rates by 50 Basis Points...
         Source: Reuters  |  Confidence: 90%
         Reason: Surprise broad-market rate cut — concrete Fed action...

[MEDIUM] Apple Reports Record Quarterly Earnings, Beats Analyst Estimates
         ...

[LOW]    Goldman Sachs Analyst Upgrades Ford to Buy
         ...
```

### Production loop

```bash
python monitor.py
```

Runs continuously, polling every 5 minutes during market hours (09:00–17:00 ET, Mon–Fri). Ctrl+C to stop.

### Run as a background service (macOS launchd)

Create `/Library/LaunchDaemons/com.sentinel.news.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>           <string>com.sentinel.news</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/jeff/VSCodeProjects/Sentinel/.venv/bin/python</string>
    <string>/Users/jeff/VSCodeProjects/Sentinel/monitor.py</string>
  </array>
  <key>RunAtLoad</key>       <true/>
  <key>KeepAlive</key>       <true/>
  <key>StandardOutPath</key> <string>/var/log/sentinel.log</string>
  <key>StandardErrorPath</key><string>/var/log/sentinel.log</string>
</dict>
</plist>
```

## Output files

### `financial_news.log`
One JSON record per line — ship this to Splunk for correlation with your WAS access logs:

```json
{"timestamp": "2026-02-28T14:00:15+00:00", "monitored_at": "2026-02-28T14:00:22+00:00", "source": "Reuters", "title": "Federal Reserve Cuts Rates by 50 Basis Points", "classification": "HIGH", "confidence": 0.92, "reason": "Concrete Fed action affecting all market participants"}
```

**Splunk correlation query** (after shipping the log via universal forwarder, `sourcetype=financial_news`):
```spl
index=news classification=HIGH
| eval event_time=strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z")
| join type=left [ search index=access_logs action=login | timechart span=1m count as logins ]
| table event_time, title, logins
| sort -event_time
```

### `news_events.db`
SQLite database for tracking classification accuracy over time. After you've correlated a news event with an actual login spike, fill in the `actual_impact` column manually:

```bash
sqlite3 news_events.db

-- See today's breakdown
SELECT classification, COUNT(*) FROM news_events
WHERE created_at >= datetime('now', '-24 hours')
GROUP BY classification;

-- Record that a HIGH event actually drove a spike
UPDATE news_events SET actual_impact = 'confirmed_spike'
WHERE title LIKE '%Federal Reserve%' AND DATE(created_at) = '2026-02-28';

-- Measure classifier accuracy after a few months
SELECT classification, actual_impact, COUNT(*)
FROM news_events
WHERE actual_impact IS NOT NULL
GROUP BY classification, actual_impact;
```

## Classification levels

| Level | Examples | Expected login impact |
|-------|----------|-----------------------|
| **HIGH** | Fed rate decisions, CPI/jobs report, market moves >3%, trading halts | Likely spike within 10–15 min |
| **MEDIUM** | Earnings beats/misses, IPOs, options expiration, Fed speculation | Possible moderate increase |
| **LOW** | Analyst upgrades, minor commentary, already-priced-in news | Minimal impact |

## Tuning

**Too many false HIGH alerts?** Raise `HIGH_CONFIDENCE_MIN` in `config.py` (e.g. `0.75`) to require the model to be more certain before a HIGH sticks.

**Surge fires too easily?** Increase `SPIKE_HIGH_THRESHOLD` (e.g. `5`) or extend `SPIKE_WINDOW_MINUTES`.

**Slower machine / want faster classification?** Switch `OLLAMA_MODEL` to `qwen3:8b` in `config.py`.

**Want to add a news source?** Append an RSS URL to `RSS_FEEDS` in `config.py` — no code changes needed.

## File reference

```
sentinel/
├── monitor.py          Main entry point and polling loop
├── feeds.py            RSS + NewsAPI fetch and deduplication
├── classifier.py       Ollama HTTP client and response parser
├── spike_detector.py   Sliding-window burst detection
├── storage.py          SQLite + JSON log writer
├── alerts.py           Console and Slack alert dispatch
├── config.py           All configuration settings
├── requirements.txt    feedparser, requests
├── news_events.db      Created on first run — SQLite store
└── financial_news.log  Created on first run — Splunk-ready log
```
