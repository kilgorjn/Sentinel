"""Classify financial news articles using a local Ollama LLM."""

import re
import logging

import requests

import config

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

CLASSIFICATION levels:
HIGH — Concrete broad-market event: Fed rate decisions, major economic data (CPI, jobs), >3% market moves, trading halts
MEDIUM — Company-specific event or rumor: earnings beats/misses, Fed speculation, IPO, options expiration
LOW — Analyst opinions, minor upgrades, general commentary, already-priced-in news
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


def _parse_response(text: str) -> dict:
    """Extract classification, confidence, reason from Ollama output."""
    result = {"classification": "LOW", "confidence": 0.5, "reason": ""}

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
