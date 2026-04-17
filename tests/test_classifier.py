"""Tests for core/classifier.py — parse helpers and _parse_response."""

import pytest
from core.classifier import (
    _parse_classification,
    _parse_confidence,
    _parse_sentiment,
    _parse_response,
)


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
