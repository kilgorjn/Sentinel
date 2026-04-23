"""Classify financial news articles using a local Ollama LLM."""

import re
import logging
from typing import Optional

import requests

from . import config

log = logging.getLogger(__name__)

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


def _parse_classification(line: str) -> str:
    for level in ("HIGH", "MEDIUM", "LOW"):
        if level in line:
            return level
    return "LOW"


def _parse_confidence(line: str) -> float:
    raw = line.split(":", 1)[-1].strip()
    try:
        val = float(raw.rstrip("%"))
        return val / 100 if val > 1 else val
    except ValueError:
        return 0.5


def _parse_sentiment(line: str) -> str:
    upper = line.upper()
    for s in ("POSITIVE", "NEGATIVE", "NEUTRAL"):
        if s in upper:
            return s
    return "NEUTRAL"


def _parse_response(text: str) -> dict:
    """Extract classification, confidence, reason, and sentiment from Ollama output."""
    result = {"classification": "LOW", "confidence": 0.5, "reason": "", "sentiment": "NEUTRAL"}

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("CLASSIFICATION:"):
            result["classification"] = _parse_classification(line)
        elif line.startswith("CONFIDENCE:"):
            result["confidence"] = _parse_confidence(line)
        elif line.startswith("REASON:"):
            result["reason"] = line.split(":", 1)[-1].strip()
        elif line.startswith("SENTIMENT:"):
            result["sentiment"] = _parse_sentiment(line)

    return result


def classify(article: dict) -> dict:
    """
    Classify a single article dict (must have 'title' and 'summary').
    Returns dict with keys: classification, confidence, reason.
    Falls back to LOW on any error.
    """
    prompt = _PROMPT_TEMPLATE.format(
        title=article.get("title", ""),
        summary=article.get("summary", "")[:500],
    )
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

        return result

    except requests.exceptions.Timeout:
        log.error("Ollama timed out classifying: %s", article.get("title"))
        return {"classification": "LOW", "confidence": 0.0, "reason": "Ollama timeout"}
    except Exception as e:
        log.error("Ollama error for '%s': %s", article.get("title"), e)
        return {"classification": "LOW", "confidence": 0.0, "reason": f"Error: {e}"}


_SUMMARY_PROMPT = """\
You are a financial news analyst at a large brokerage firm.

Recent classified news events (last 24 hours):
{events}

{prediction_context}{surge_context}Write 3-4 sentences covering:
- The main financial themes driving market attention right now
- Why brokerage customers are likely logging in to check their accounts
- Any key risk factors or catalysts to watch

Rules: Output ONLY the summary sentences. No preamble, no intro phrase, no labels. Start directly with the first sentence of analysis.
SUMMARY:"""

_PREDICTION_TONE = {
    "NORMAL":   "metrics indicate baseline login activity — acknowledge themes but note conditions are not yet driving elevated traffic",
    "MODERATE": "metrics indicate moderately elevated login activity — convey developing conditions that merit attention",
    "ELEVATED": "metrics indicate significantly elevated login activity — convey meaningful concern and heightened customer engagement",
    "SURGE":    "metrics indicate a login volume SURGE — convey urgency and directly explain what is driving the spike",
}


def summarize(
    events: list[dict],
    surge_active: bool = False,
    market_context: list[dict] | None = None,
    prediction: Optional[dict] | None = None,
) -> str:
    """Generate a plain-English narrative summary of recent events via Ollama.

    If *market_context* is provided (a list of snapshot dicts with at least
    ``name`` and ``change_pct`` keys), significant moves are appended to the
    prompt so the LLM can weave them into the narrative.

    If *prediction* is provided (a dict with at least ``label``, ``score``,
    and ``drivers`` keys), the current login volume prediction is injected so
    the LLM calibrates its tone to match the quantitative assessment.
    """
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

    # Append market data context if available
    market_section = ""
    if market_context:
        significant = [
            s for s in market_context if abs(s.get("change_pct", 0)) >= 0.5
        ]
        if significant:
            market_lines = [
                f"- {s['name']}: {s['change_pct']:+.1f}%"
                for s in significant
            ]
            market_section = (
                "\n\nGLOBAL MARKET CONTEXT:\n" + "\n".join(market_lines) + "\n"
            )

    # Inject prediction context so the LLM's tone matches the quantitative view
    prediction_context = ""
    if prediction:
        label   = prediction.get("label", "NORMAL")
        score   = prediction.get("score", 0)
        drivers = prediction.get("drivers") or []
        tone    = _PREDICTION_TONE.get(label, _PREDICTION_TONE["NORMAL"])
        drivers_str = "; ".join(drivers) if drivers else "no significant drivers"
        prediction_context = (
            f"CURRENT LOGIN VOLUME PREDICTION: {label} (score: {score}/100)\n"
            f"Key drivers: {drivers_str}\n"
            f"Tone guidance: {tone}\n\n"
        )

    prompt = _SUMMARY_PROMPT.format(
        events="\n".join(lines) + market_section,
        surge_context=surge_context,
        prediction_context=prediction_context,
    )
    try:
        raw = _call_ollama(prompt)
        text = raw.strip()
        if "SUMMARY:" in text:
            text = text.split("SUMMARY:", 1)[-1].strip()
        return text
    except Exception as e:
        log.warning("Narrative summarization failed: %s", e)
        return "Summary unavailable — Ollama did not respond."
