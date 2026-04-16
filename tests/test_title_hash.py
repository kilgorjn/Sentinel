"""Tests for storage._title_hash() normalization."""

import pytest
from core.storage import _title_hash


class TestTitleHash:
    def test_same_title_same_hash(self):
        assert _title_hash("Fed Cuts Rates") == _title_hash("Fed Cuts Rates")

    def test_case_insensitive(self):
        assert _title_hash("FED CUTS RATES") == _title_hash("fed cuts rates")

    def test_punctuation_stripped(self):
        # Punctuation differences should not produce different hashes
        assert _title_hash("Fed Cuts Rates!") == _title_hash("Fed Cuts Rates")

    def test_whitespace_collapsed(self):
        assert _title_hash("Fed  Cuts   Rates") == _title_hash("Fed Cuts Rates")

    def test_non_ascii_falls_back(self):
        # Non-ASCII only title should not produce the same hash as another non-ASCII title
        hash1 = _title_hash("日経平均株価が上昇")
        hash2 = _title_hash("上海総合指数が下落")
        assert hash1 != hash2

    def test_all_punctuation_falls_back(self):
        # All-punctuation title normalizes to empty — should fall back, not collide
        hash1 = _title_hash("!!!")
        hash2 = _title_hash("???")
        assert hash1 != hash2

    def test_empty_string_stable(self):
        # Empty string is an edge case — should return a consistent hash
        assert _title_hash("") == _title_hash("")

    def test_returns_64_char_hex(self):
        result = _title_hash("Some Title")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)
