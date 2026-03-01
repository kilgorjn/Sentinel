"""Classify financial news articles using Ollama for urgency and FinBERT for sentiment."""

import logging
from typing import Any, Optional

import requests
from transformers import BertTokenizer, BertForSequenceClassification, pipeline

from . import config

log = logging.getLogger(__name__)

# Initialize FinBERT sentiment pipeline on first use
_sentiment_pipeline: Optional[Any] = None


def _get_sentiment_pipeline() -> Any:
    """Lazy-load FinBERT sentiment pipeline (yiyanghkust/finbert-tone).

    Loaded with explicit BERT classes because finbert-tone omits model_type
    in its config.json, which causes the auto-detection in pipeline() to fail.
    """
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        log.info("Loading FinBERT sentiment model...")
        _model_id = "yiyanghkust/finbert-tone"
        tokenizer = BertTokenizer.from_pretrained(_model_id)
        model = BertForSequenceClassification.from_pretrained(_model_id)
        _sentiment_pipeline = pipeline(  # type: ignore
            "sentiment-analysis",
            model=model,
            tokenizer=tokenizer,
            device=-1,  # -1 for CPU, 0+ for GPU
        )
        log.info("FinBERT sentiment model loaded.")
    return _sentiment_pipeline

_PROMPT_TEMPLATE = """\
You are a financial news classifier for a large brokerage firm.

Classify the article below by how likely it will cause a spike in brokerage login volume from active retail traders.

ARTICLE TITLE: {title}
ARTICLE SUMMARY: {summary}

Evaluate:
1. Is this BREAKING/CONCRETE news (decision announced) or speculation/analysis?
2. Scope: Does it affect the whole market or just one stock?
3. Magnitude: How large is the action (50bps rate cut vs. minor analyst note)?
4. Sentiment extremity: Neutral vs. alarming/euphoric?

Respond with ONLY this format — no other text:
CLASSIFICATION: [HIGH|MEDIUM|LOW]
CONFIDENCE: [0.0-1.0]
REASON: [one sentence]
SENTIMENT: [POSITIVE|NEGATIVE|NEUTRAL]

CLASSIFICATION levels:
HIGH — Concrete broad-market event: Fed rate decisions, major economic data (CPI, jobs), >3% market moves, trading halts
MEDIUM — Company-specific event or rumor: earnings beats/misses, Fed speculation, IPO, options expiration
LOW — Analyst opinions, minor upgrades, general commentary, already-priced-in news

SENTIMENT levels:
POSITIVE — Good news: rate cuts, strong jobs/earnings, market rallies, deal closings
NEGATIVE — Bad news: rate hikes, recession signals, market drops, scandals, halts
NEUTRAL — Informational, mixed, or ambiguous impact on investor mood
"""


def _call_ollama(prompt: str) -> str:
    """POST to Ollama and return the raw text response."""
    resp = requests.post(
        f"{config.OLLAMA_URL}/api/generate",
        json={
            "model": config.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": config.OLLAMA_TEMPERATURE},
        },
        timeout=config.OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def _analyze_sentiment(title: str, summary: str) -> tuple:
    """Analyze sentiment using FinBERT. Returns (label, score) tuple.
    Label is 'POSITIVE', 'NEGATIVE', or 'NEUTRAL'. Score is the model confidence [0-1].
    """
    try:
        pipe = _get_sentiment_pipeline()
        text = f"{title}. {summary}"[:512]
        result = pipe(text)[0]
        label = result["label"].upper()
        score = result["score"]
        log.debug("FinBERT sentiment for '%s': %s (%.2f)", title[:50], label, score)
        if label not in ("POSITIVE", "NEGATIVE"):
            label = "NEUTRAL"
        return label, score
    except Exception as e:
        log.warning("FinBERT sentiment analysis failed: %s", e)
        return "NEUTRAL", None


def _parse_response(text: str) -> dict:
    """Extract classification, confidence, reason, and ollama_sentiment from Ollama output."""
    result = {"classification": "LOW", "confidence": 0.5, "reason": "", "ollama_sentiment": "NEUTRAL"}

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("CLASSIFICATION:"):
            for level in ("HIGH", "MEDIUM", "LOW"):
                if level in line:
                    result["classification"] = level
                    break
        elif line.startswith("CONFIDENCE:"):
            raw = line.split(":", 1)[-1].strip()
            try:
                val = float(raw.rstrip("%"))
                result["confidence"] = val / 100 if val > 1 else val
            except ValueError:
                pass
        elif line.startswith("REASON:"):
            result["reason"] = line.split(":", 1)[-1].strip()
        elif line.startswith("SENTIMENT:"):
            for s in ("POSITIVE", "NEGATIVE", "NEUTRAL"):
                if s in line.upper():
                    result["ollama_sentiment"] = s
                    break

    return result


def classify(article: dict) -> dict:
    """
    Classify a single article dict (must have 'title' and 'summary').
    Returns dict with keys: classification, confidence, reason, sentiment.
    Uses Ollama for urgency classification and FinBERT for sentiment analysis.
    Falls back to LOW on any error.
    """
    title = article.get("title", "")
    summary = article.get("summary", "")[:500]
    prompt = _PROMPT_TEMPLATE.format(title=title, summary=summary)

    try:
        raw = _call_ollama(prompt)
        log.debug("Ollama raw response: %s", raw)
        result = _parse_response(raw)

        # Enforce minimum confidence thresholds — downgrade if uncertain
        if result["classification"] == "HIGH" and result["confidence"] < config.HIGH_CONFIDENCE_MIN:
            result["classification"] = "MEDIUM"
            result["reason"] += " (downgraded: low confidence)"
        elif result["classification"] == "MEDIUM" and result["confidence"] < config.MEDIUM_CONFIDENCE_MIN:
            result["classification"] = "LOW"
            result["reason"] += " (downgraded: low confidence)"

        # Run FinBERT sentiment independently
        finbert_label, finbert_score = _analyze_sentiment(title, summary)

        # Per-model sentiments — extensible for future models
        result["sentiments"] = {
            "finbert": {"sentiment": finbert_label, "score": finbert_score},
            "ollama":  {"sentiment": result.pop("ollama_sentiment"), "score": None},
        }
        # Primary sentiment (FinBERT) kept at top level for backward compat
        result["sentiment"] = finbert_label

        return result

    except requests.exceptions.Timeout:
        log.error("Ollama timed out classifying: %s", title)
        return {
            "classification": "LOW",
            "confidence": 0.0,
            "reason": "Ollama timeout",
            "sentiment": "NEUTRAL",
            "sentiments": {},
        }
    except Exception as e:
        log.error("Ollama error for '%s': %s", title, e)
        return {
            "classification": "LOW",
            "confidence": 0.0,
            "reason": f"Error: {e}",
            "sentiment": "NEUTRAL",
            "sentiments": {},
        }


_SUMMARY_PROMPT = """\
You are a financial news analyst at a large brokerage firm.

Recent classified news events (last 24 hours):
{events}

{surge_context}Write 3-4 sentences covering:
- The main financial themes driving market attention right now
- Why brokerage customers are likely logging in to check their accounts
- Any key risk factors or catalysts to watch

Rules: Output ONLY the summary sentences. No preamble, no intro phrase, no labels. Start directly with the first sentence of analysis.
SUMMARY:"""


def summarize(events: list[dict], surge_active: bool = False) -> str:
    """Generate a plain-English narrative summary of recent events via Ollama."""
    if not events:
        return "No significant financial events in the last 24 hours."
    lines = []
    for i, ev in enumerate(events[:25], 1):
        lines.append(f"{i}. [{ev['classification']}] {ev['title']} — {ev.get('reason', '')}")
    surge_context = (
        "IMPORTANT: A NEWS SURGE is currently active. Focus your summary on explaining "
        "the specific causes of the surge and what is driving elevated brokerage activity.\n\n"
        if surge_active else ""
    )
    prompt = _SUMMARY_PROMPT.format(events="\n".join(lines), surge_context=surge_context)
    try:
        raw = _call_ollama(prompt)
        text = raw.strip()
        if "SUMMARY:" in text:
            text = text.split("SUMMARY:", 1)[-1].strip()
        return text
    except Exception as e:
        log.warning("Narrative summarization failed: %s", e)
        return "Summary unavailable — Ollama did not respond."
