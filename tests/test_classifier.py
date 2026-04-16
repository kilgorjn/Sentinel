"""Tests for core/classifier.py — _parse_response(), classify(), summarize()."""

import pytest
import requests
from unittest.mock import patch, MagicMock

from core import classifier, config
from core.classifier import _parse_response


def _mock_ollama(text: str):
    resp = MagicMock()
    resp.json.return_value = {"response": text}
    resp.raise_for_status = MagicMock()
    return resp


class TestParseResponse:
    def test_defaults_on_empty_input(self):
        result = _parse_response("")
        assert result["classification"] == "LOW"
        assert result["confidence"] == 0.5
        assert result["sentiment"] == "NEUTRAL"
        assert result["reason"] == ""

    def test_parses_high(self):
        text = "CLASSIFICATION: HIGH\nCONFIDENCE: 0.9\nREASON: Fed rate cut\nSENTIMENT: NEGATIVE"
        r = _parse_response(text)
        assert r["classification"] == "HIGH"
        assert r["confidence"] == 0.9
        assert r["reason"] == "Fed rate cut"
        assert r["sentiment"] == "NEGATIVE"

    def test_parses_medium(self):
        text = "CLASSIFICATION: MEDIUM\nCONFIDENCE: 0.65\nREASON: Earnings beat\nSENTIMENT: POSITIVE"
        r = _parse_response(text)
        assert r["classification"] == "MEDIUM"
        assert r["sentiment"] == "POSITIVE"

    def test_parses_low(self):
        text = "CLASSIFICATION: LOW\nCONFIDENCE: 0.3\nREASON: Minor note\nSENTIMENT: NEUTRAL"
        r = _parse_response(text)
        assert r["classification"] == "LOW"

    def test_confidence_as_percentage(self):
        text = "CLASSIFICATION: HIGH\nCONFIDENCE: 90%\nREASON: Test\nSENTIMENT: NEUTRAL"
        r = _parse_response(text)
        assert r["confidence"] == pytest.approx(0.9)

    def test_invalid_confidence_keeps_default(self):
        text = "CLASSIFICATION: HIGH\nCONFIDENCE: n/a\nREASON: Test\nSENTIMENT: NEUTRAL"
        r = _parse_response(text)
        assert r["confidence"] == 0.5

    def test_positive_sentiment(self):
        r = _parse_response("CLASSIFICATION: LOW\nCONFIDENCE: 0.5\nREASON: x\nSENTIMENT: POSITIVE")
        assert r["sentiment"] == "POSITIVE"

    def test_negative_sentiment(self):
        r = _parse_response("CLASSIFICATION: LOW\nCONFIDENCE: 0.5\nREASON: x\nSENTIMENT: NEGATIVE")
        assert r["sentiment"] == "NEGATIVE"

    def test_extra_whitespace_around_values(self):
        text = "CLASSIFICATION:  HIGH \nCONFIDENCE: 0.8\nREASON:  Some reason \nSENTIMENT: NEUTRAL"
        r = _parse_response(text)
        assert r["classification"] == "HIGH"
        assert r["reason"] == "Some reason"


class TestClassify:
    def test_returns_parsed_result(self):
        resp_text = "CLASSIFICATION: HIGH\nCONFIDENCE: 0.9\nREASON: Fed cut\nSENTIMENT: NEGATIVE"
        with patch("core.classifier.requests.post", return_value=_mock_ollama(resp_text)):
            result = classifier.classify({"title": "Fed Cuts Rates", "summary": "50bps"})
        assert result["classification"] == "HIGH"
        assert result["confidence"] == 0.9

    def test_timeout_returns_low(self):
        with patch("core.classifier.requests.post", side_effect=requests.exceptions.Timeout()):
            result = classifier.classify({"title": "Test", "summary": ""})
        assert result["classification"] == "LOW"
        assert result["confidence"] == 0.0
        assert "timeout" in result["reason"].lower()

    def test_generic_error_returns_low(self):
        with patch("core.classifier.requests.post", side_effect=Exception("Connection refused")):
            result = classifier.classify({"title": "Test", "summary": ""})
        assert result["classification"] == "LOW"
        assert result["confidence"] == 0.0

    def test_high_downgraded_when_confidence_too_low(self):
        low_conf = config.HIGH_CONFIDENCE_MIN - 0.1
        resp_text = f"CLASSIFICATION: HIGH\nCONFIDENCE: {low_conf}\nREASON: Weak signal\nSENTIMENT: NEUTRAL"
        with patch("core.classifier.requests.post", return_value=_mock_ollama(resp_text)):
            result = classifier.classify({"title": "Test", "summary": ""})
        assert result["classification"] == "MEDIUM"
        assert "downgraded" in result["reason"]

    def test_medium_downgraded_when_confidence_too_low(self):
        low_conf = config.MEDIUM_CONFIDENCE_MIN - 0.1
        resp_text = f"CLASSIFICATION: MEDIUM\nCONFIDENCE: {low_conf}\nREASON: Weak signal\nSENTIMENT: NEUTRAL"
        with patch("core.classifier.requests.post", return_value=_mock_ollama(resp_text)):
            result = classifier.classify({"title": "Test", "summary": ""})
        assert result["classification"] == "LOW"
        assert "downgraded" in result["reason"]

    def test_high_kept_when_confidence_above_threshold(self):
        high_conf = config.HIGH_CONFIDENCE_MIN + 0.1
        resp_text = f"CLASSIFICATION: HIGH\nCONFIDENCE: {high_conf}\nREASON: Strong signal\nSENTIMENT: NEGATIVE"
        with patch("core.classifier.requests.post", return_value=_mock_ollama(resp_text)):
            result = classifier.classify({"title": "Test", "summary": ""})
        assert result["classification"] == "HIGH"

    def test_medium_kept_when_confidence_above_threshold(self):
        high_conf = config.MEDIUM_CONFIDENCE_MIN + 0.1
        resp_text = f"CLASSIFICATION: MEDIUM\nCONFIDENCE: {high_conf}\nREASON: OK signal\nSENTIMENT: NEUTRAL"
        with patch("core.classifier.requests.post", return_value=_mock_ollama(resp_text)):
            result = classifier.classify({"title": "Test", "summary": ""})
        assert result["classification"] == "MEDIUM"


class TestSummarize:
    def test_no_events_returns_default_message(self):
        result = classifier.summarize([])
        assert "No significant" in result

    def test_returns_ollama_text(self):
        events = [{"classification": "HIGH", "title": "Fed Cuts", "reason": "50bps cut"}]
        with patch("core.classifier.requests.post", return_value=_mock_ollama("Markets rallied on the Fed decision.")):
            result = classifier.summarize(events)
        assert "Markets rallied" in result

    def test_strips_summary_label_prefix(self):
        events = [{"classification": "LOW", "title": "Minor note", "reason": "analyst note"}]
        with patch("core.classifier.requests.post", return_value=_mock_ollama("SUMMARY: Clean text here.")):
            result = classifier.summarize(events)
        assert not result.startswith("SUMMARY:")
        assert "Clean text here." in result

    def test_ollama_failure_returns_fallback(self):
        events = [{"classification": "HIGH", "title": "Fed Cuts", "reason": "50bps cut"}]
        with patch("core.classifier.requests.post", side_effect=Exception("Ollama down")):
            result = classifier.summarize(events)
        assert "unavailable" in result.lower()

    def test_surge_context_included(self):
        events = [{"classification": "HIGH", "title": "Crash", "reason": "market drop"}]
        captured_prompt = []

        def capture(url, json=None, timeout=None):
            captured_prompt.append(json.get("prompt", ""))
            return _mock_ollama("Summary text.")

        with patch("core.classifier.requests.post", side_effect=capture):
            classifier.summarize(events, surge_active=True)

        assert "SURGE" in captured_prompt[0]

    def test_market_context_included_for_significant_moves(self):
        events = [{"classification": "LOW", "title": "Minor", "reason": "note"}]
        market = [{"name": "S&P 500", "change_pct": -2.5}, {"name": "Nasdaq", "change_pct": 0.1}]
        captured_prompt = []

        def capture(url, json=None, timeout=None):
            captured_prompt.append(json.get("prompt", ""))
            return _mock_ollama("Summary.")

        with patch("core.classifier.requests.post", side_effect=capture):
            classifier.summarize(events, market_context=market)

        assert "S&P 500" in captured_prompt[0]
        assert "Nasdaq" not in captured_prompt[0]
