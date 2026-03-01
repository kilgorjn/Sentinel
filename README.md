# Sentinel — Financial News Monitor

Monitors financial news feeds, classifies articles by market impact using a local Ollama LLM, and fires alerts when a burst of high-impact events is detected. Designed to give brokerage ops teams advance warning before login volume spikes hit.

A web UI displays the live event feed, classification summary, an AI-generated narrative, and a 24-hour trend chart — all auto-refreshing every 30 seconds.

## How it works

```
RSS Feeds / NewsAPI
      ↓
  core/feeds.py       — fetch & deduplicate articles every 5 minutes
      ↓
  core/classifier.py  — ask local Ollama to classify each article HIGH / MEDIUM / LOW
                        and generate a narrative summary of current events
      ↓
  core/spike_detector — sliding 30-min window; SURGE alert when ≥3 HIGH events accumulate
      ↓
  core/storage.py     — write to SQLite (accuracy tracking) + JSON log (Splunk ingestion)
      ↓
  core/alerts.py      — color-coded console output; optional Slack webhook
      ↓
  api/main.py         — FastAPI REST API consumed by the Vue frontend
```

The spike detection mirrors a login-volume spike pattern: instead of counting logins per time window, it counts HIGH-impact news events. A burst of major events is a leading indicator that user logins will spike within 10–15 minutes.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [Ollama](https://ollama.ai) running on a host reachable by the Docker containers
- A model pulled on that Ollama server — `gemma3:12b` is the default; `qwen3:8b` is a faster alternative

Check available models on your server:
```bash
curl http://your-ollama-host:11434/api/tags | python3 -m json.tool
```

## Quick start (Docker)

```bash
git clone https://github.com/kilgorjn/Sentinel.git
cd Sentinel

cp .env.example .env
# Edit .env — set OLLAMA_URL and optionally NEWSAPI_KEY

docker compose up --build -d
```

The web UI will be available at `http://localhost:8000`.

## Configuration

Copy `.env.example` to `.env` and set values. All settings can also be overridden via environment variables.

| Setting | Default | Description |
|---------|---------|-------------|
| `OLLAMA_URL` | `http://jeffs-gaming-pc.lan:11434` | Ollama server address |
| `OLLAMA_MODEL` | `gemma3:12b` | Model to use for classification and narrative |
| `NEWSAPI_KEY` | *(unset)* | Optional — 100 req/day free at newsapi.org |
| `DISPLAY_TIMEZONE` | `America/New_York` | Timezone for all frontend timestamps |
| `SPIKE_WINDOW_MINUTES` | `30` | Rolling window for burst detection |
| `SPIKE_HIGH_THRESHOLD` | `3` | HIGH events in window before SURGE fires |
| `POLL_INTERVAL_SECONDS` | `300` | How often to fetch news (5 minutes) |
| `MARKET_HOURS_ONLY` | `False` | Set `True` to restrict polling to 09:00–17:00 ET Mon–Fri |
| `SLACK_WEBHOOK_URL` | *(unset)* | Set to enable Slack surge alerts |

Additional settings (RSS feeds, confidence thresholds) live in `core/config.py`.

## Web UI

The frontend provides:

- **Summary bar** — HIGH / MEDIUM / LOW counts for the last 24 hours; click tiles to toggle visibility
- **Trend chart** — 24-hour line chart showing event volume per classification, based on article publication time
- **Narrative summary** — AI-generated 3–4 sentence analysis of current events, updated every 15 minutes; surge-aware (explains what is driving the spike when a SURGE is active)
- **Event feed** — Full list of classified articles with source, timestamp, confidence, and reason

## Portainer / Docker stack deployment

Use `docker-compose.portainer.yml` to create a Portainer stack. Fill in `stack.env` with your values and upload it as the stack environment file.

The Docker image is published automatically to `ghcr.io/kilgorjn/sentinel:latest` on every push to `main` via GitHub Actions.

## Local development (without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Smoke test — classifies 5 sample articles and exits
python -m core.monitor --test

# Production loop
python -m core.monitor
```

Frontend dev server (hot reload):
```bash
cd frontend
npm install
npm run dev       # http://localhost:5173 (proxies API calls to http://localhost:8000)
```

API server:
```bash
uvicorn api.main:app --reload --port 8000
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
SQLite database for tracking classification accuracy over time.

```bash
# Access the DB inside the running Docker container
docker exec -it sentinel-api-1 sqlite3 /data/news_events.db

-- Today's breakdown
SELECT classification, COUNT(*) FROM news_events
WHERE published_at >= datetime('now', '-24 hours')
GROUP BY classification;

-- Record that a HIGH event actually drove a login spike
UPDATE news_events SET actual_impact = 'confirmed_spike'
WHERE title LIKE '%Federal Reserve%';

-- Measure classifier accuracy
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

**Too many false HIGH alerts?** Raise `HIGH_CONFIDENCE_MIN` in `core/config.py` (e.g. `0.75`).

**Surge fires too easily?** Increase `SPIKE_HIGH_THRESHOLD` (e.g. `5`) or extend `SPIKE_WINDOW_MINUTES`.

**Slower machine / want faster classification?** Set `OLLAMA_MODEL=qwen3:8b` in `.env`.

**Want to add a news source?** Append an RSS URL to `RSS_FEEDS` in `core/config.py` — no code changes needed.

## Project structure

```
Sentinel/
├── core/
│   ├── monitor.py          Main entry point and polling loop
│   ├── feeds.py            RSS + NewsAPI fetch and deduplication
│   ├── classifier.py       Ollama HTTP client, classifier, and narrative summarizer
│   ├── spike_detector.py   Sliding-window burst detection
│   ├── storage.py          SQLite + JSON log writer; meta key-value store
│   ├── alerts.py           Console and Slack alert dispatch
│   └── config.py           All configuration settings
├── api/
│   ├── main.py             FastAPI application and route handlers
│   ├── models.py           Pydantic response schemas
│   └── dependencies.py     Shared DB connection
├── frontend/
│   ├── src/
│   │   ├── App.vue         Root component; data fetching and state
│   │   └── components/     SummaryBar, EventFeed, EventChart, NarrativeSummary, SurgeAlert
│   ├── public/favicon.svg
│   └── package.json
├── .github/workflows/
│   └── docker-publish.yml  Build and push to ghcr.io on push to main
├── Dockerfile              Multi-stage build (Node → Vue dist, Python app)
├── docker-compose.yml      Local development / self-hosted
├── docker-compose.portainer.yml  Portainer stack (uses published image)
├── stack.env               Environment variable template for Portainer
├── .env.example            Local .env template
└── requirements.txt        Python dependencies
```
