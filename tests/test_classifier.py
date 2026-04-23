"""Tests for core/classifier.py — parse helpers, _parse_response, classify, summarize."""

import pytest
import requests
from unittest.mock import patch

from core.classifier import (
    _parse_classification,
    _parse_confidence,
    _parse_sentiment,
    _parse_response,
    classify,
    summarize,
)
from core import config


class TestParseClassification:
    def test_high(self):
        assert _parse_classification("CLASSIFICATION: HIGH") == "HIGH"

    def test_medium(self):
        assert _parse_classification("CLASSIFICATION: MEDIUM") == "MEDIUM"

    def test_low(self):
        assert _parse_classification("CLASSIFICATION: LOW") == "LOW"

    def test_embedded_in_longer_line(self):
        assert _parse_classification("The result is HIGH based on data") == "HIGH"

    def test_no_match_defaults_to_low(self):
        assert _parse_classification("CLASSIFICATION: UNKNOWN") == "LOW"

    def test_empty_string_defaults_to_low(self):
        assert _parse_classification("") == "LOW"

    def test_prefers_high_over_medium_when_both_present(self):
        # "HIGH" comes first in the loop so it wins
        assert _parse_classification("HIGH MEDIUM LOW") == "HIGH"


class TestParseConfidence:
    def test_decimal_value(self):
        assert _parse_confidence("CONFIDENCE: 0.85") == pytest.approx(0.85)

    def test_percent_symbol(self):
        assert _parse_confidence("CONFIDENCE: 85%") == pytest.approx(0.85)

    def test_whole_number_over_one(self):
        # Values > 1 are treated as percentages
        assert _parse_confidence("CONFIDENCE: 90") == pytest.approx(0.9)

    def test_value_at_boundary_one(self):
        assert _parse_confidence("CONFIDENCE: 1") == pytest.approx(1.0)

    def test_invalid_defaults_to_half(self):
        assert _parse_confidence("CONFIDENCE: ???") == pytest.approx(0.5)

    def test_empty_suffix_defaults_to_half(self):
        assert _parse_confidence("CONFIDENCE:") == pytest.approx(0.5)

    def test_zero(self):
        assert _parse_confidence("CONFIDENCE: 0.0") == pytest.approx(0.0)


class TestParseSentiment:
    def test_positive(self):
        assert _parse_sentiment("SENTIMENT: POSITIVE") == "POSITIVE"

    def test_negative(self):
        assert _parse_sentiment("SENTIMENT: NEGATIVE") == "NEGATIVE"

    def test_neutral(self):
        assert _parse_sentiment("SENTIMENT: NEUTRAL") == "NEUTRAL"

    def test_case_insensitive(self):
        assert _parse_sentiment("sentiment: positive") == "POSITIVE"

    def test_no_match_defaults_to_neutral(self):
        assert _parse_sentiment("SENTIMENT: MIXED") == "NEUTRAL"

    def test_empty_defaults_to_neutral(self):
        assert _parse_sentiment("") == "NEUTRAL"


class TestParseResponse:
    def test_full_valid_response(self):
        text = (
            "CLASSIFICATION: HIGH\n"
            "CONFIDENCE: 0.9\n"
            "REASON: Fed emergency rate cut\n"
            "SENTIMENT: NEGATIVE"
        )
        result = _parse_response(text)
        assert result["classification"] == "HIGH"
        assert result["confidence"] == pytest.approx(0.9)
        assert result["reason"] == "Fed emergency rate cut"
        assert result["sentiment"] == "NEGATIVE"

    def test_defaults_on_empty_response(self):
        result = _parse_response("")
        assert result["classification"] == "LOW"
        assert result["confidence"] == pytest.approx(0.5)
        assert result["reason"] == ""
        assert result["sentiment"] == "NEUTRAL"

    def test_ignores_unrecognised_lines(self):
        text = "Some preamble\nCLASSIFICATION: MEDIUM\nTrailing noise"
        result = _parse_response(text)
        assert result["classification"] == "MEDIUM"

    def test_percentage_confidence_converted(self):
        text = "CLASSIFICATION: LOW\nCONFIDENCE: 75%\nREASON: Minor\nSENTIMENT: NEUTRAL"
        result = _parse_response(text)
        assert result["confidence"] == pytest.approx(0.75)

    def test_whitespace_stripped_from_reason(self):
        text = "REASON:   Markets rallied sharply  "
        result = _parse_response(text)
        assert result["reason"] == "Markets rallied sharply"


class TestClassify:
    _ARTICLE = {"title": "Fed cuts rates 50bps", "summary": "Emergency rate cut announced."}
    _HIGH_RAW = "CLASSIFICATION: HIGH\nCONFIDENCE: 0.9\nREASON: Fed emergency cut\nSENTIMENT: NEGATIVE"

    def test_successful_classification(self):
        with patch("core.classifier._call_ollama", return_value=self._HIGH_RAW):
            result = classify(self._ARTICLE)
        assert result["classification"] == "HIGH"
        assert result["confidence"] == pytest.approx(0.9)
        assert result["sentiment"] == "NEGATIVE"

    def test_high_downgraded_when_confidence_too_low(self):
        raw = f"CLASSIFICATION: HIGH\nCONFIDENCE: {config.HIGH_CONFIDENCE_MIN - 0.1:.2f}\nREASON: Uncertain\nSENTIMENT: NEUTRAL"
        with patch("core.classifier._call_ollama", return_value=raw):
            result = classify(self._ARTICLE)
        assert result["classification"] == "MEDIUM"
        assert "downgraded" in result["reason"]

    def test_medium_downgraded_when_confidence_too_low(self):
        raw = f"CLASSIFICATION: MEDIUM\nCONFIDENCE: {config.MEDIUM_CONFIDENCE_MIN - 0.1:.2f}\nREASON: Weak signal\nSENTIMENT: NEUTRAL"
        with patch("core.classifier._call_ollama", return_value=raw):
            result = classify(self._ARTICLE)
        assert result["classification"] == "LOW"
        assert "downgraded" in result["reason"]

    def test_timeout_returns_low_with_zero_confidence(self):
        with patch("core.classifier._call_ollama", side_effect=requests.exceptions.Timeout):
            result = classify(self._ARTICLE)
        assert result["classification"] == "LOW"
        assert result["confidence"] == pytest.approx(0.0)
        assert "timeout" in result["reason"].lower()

    def test_generic_error_returns_low(self):
        with patch("core.classifier._call_ollama", side_effect=ValueError("bad json")):
            result = classify(self._ARTICLE)
        assert result["classification"] == "LOW"
        assert result["confidence"] == pytest.approx(0.0)
        assert "Error" in result["reason"]

    def test_high_kept_when_confidence_above_minimum(self):
        raw = f"CLASSIFICATION: HIGH\nCONFIDENCE: {config.HIGH_CONFIDENCE_MIN + 0.1:.2f}\nREASON: Clear signal\nSENTIMENT: NEGATIVE"
        with patch("core.classifier._call_ollama", return_value=raw):
            result = classify(self._ARTICLE)
        assert result["classification"] == "HIGH"


class TestSummarize:
    _EVENTS = [
        {"classification": "HIGH", "title": "Fed cuts rates", "reason": "Emergency cut"},
        {"classification": "MEDIUM", "title": "CPI data released", "reason": "Inflation easing"},
    ]

    def test_returns_static_message_for_empty_events(self):
        result = summarize([])
        assert "No significant" in result

    def test_returns_ollama_summary_for_events(self):
        with patch("core.classifier._call_ollama", return_value="Markets are volatile today."):
            result = summarize(self._EVENTS)
        assert result == "Markets are volatile today."

    def test_strips_summary_label_from_response(self):
        with patch("core.classifier._call_ollama", return_value="SUMMARY: Key themes emerged."):
            result = summarize(self._EVENTS)
        assert result == "Key themes emerged."

    def test_surge_context_included_when_active(self):
        captured = {}
        def capture_prompt(prompt):
            captured["prompt"] = prompt
            return "Summary text."
        with patch("core.classifier._call_ollama", side_effect=capture_prompt):
            summarize(self._EVENTS, surge_active=True)
        assert "SURGE" in captured["prompt"]

    def test_market_context_included_when_significant(self):
        market_ctx = [{"name": "S&P 500", "change_pct": -2.5}]
        captured = {}
        def capture_prompt(prompt):
            captured["prompt"] = prompt
            return "Summary."
        with patch("core.classifier._call_ollama", side_effect=capture_prompt):
            summarize(self._EVENTS, market_context=market_ctx)
        assert "S&P 500" in captured["prompt"]

    def test_market_context_ignored_when_insignificant(self):
        market_ctx = [{"name": "S&P 500", "change_pct": 0.1}]
        captured = {}
        def capture_prompt(prompt):
            captured["prompt"] = prompt
            return "Summary."
        with patch("core.classifier._call_ollama", side_effect=capture_prompt):
            summarize(self._EVENTS, market_context=market_ctx)
        assert "S&P 500" not in captured["prompt"]

    def test_ollama_error_returns_fallback(self):
        with patch("core.classifier._call_ollama", side_effect=RuntimeError("offline")):
            result = summarize(self._EVENTS)
        assert "unavailable" in result.lower()

    def test_prediction_context_included_in_prompt(self):
        prediction = {"label": "ELEVATED", "score": 42, "drivers": ["3 HIGH events", "Market volatility"]}
        captured = {}
        def capture_prompt(prompt):
            captured["prompt"] = prompt
            return "Summary."
        with patch("core.classifier._call_ollama", side_effect=capture_prompt):
            summarize(self._EVENTS, prediction=prediction)
        assert "ELEVATED" in captured["prompt"]
        assert "42" in captured["prompt"]
        assert "3 HIGH events" in captured["prompt"]

    def test_no_prediction_context_when_omitted(self):
        captured = {}
        def capture_prompt(prompt):
            captured["prompt"] = prompt
            return "Summary."
        with patch("core.classifier._call_ollama", side_effect=capture_prompt):
            summarize(self._EVENTS)
        assert "LOGIN VOLUME PREDICTION" not in captured["prompt"]
