"""Tests for core/market_data.py — detect_volatility, fetch_snapshots, get_latest_snapshots."""

from unittest.mock import MagicMock, patch

import pytest

from core import config
from core.market_data import detect_volatility, fetch_snapshots, get_latest_snapshots


def _snap(name="SPX", region="us", change_pct=0.0, symbol="^GSPC"):
    return {
        "symbol": symbol,
        "name": name,
        "region": region,
        "change_pct": change_pct,
        "price": 5000.0,
        "prev_close": 4900.0,
    }


class TestDetectVolatility:
    def test_empty_snapshots_returns_no_signals(self):
        assert detect_volatility([]) == []

    def test_high_positive_move(self):
        snaps = [_snap("SPX", "us", config.MARKET_VOLATILITY_HIGH + 0.5)]
        signals = detect_volatility(snaps)
        assert len(signals) == 1
        assert signals[0]["severity"] == "HIGH"
        assert signals[0]["type"] == "index_move"
        assert "up" in signals[0]["message"]

    def test_high_negative_move(self):
        snaps = [_snap("DAX", "europe", -(config.MARKET_VOLATILITY_HIGH + 0.5))]
        signals = detect_volatility(snaps)
        assert len(signals) == 1
        assert signals[0]["severity"] == "HIGH"
        assert "down" in signals[0]["message"]

    def test_medium_positive_move(self):
        mid = (config.MARKET_VOLATILITY_MEDIUM + config.MARKET_VOLATILITY_HIGH) / 2
        snaps = [_snap("FTSE", "europe", mid)]
        signals = detect_volatility(snaps)
        assert len(signals) == 1
        assert signals[0]["severity"] == "MEDIUM"

    def test_medium_negative_move(self):
        mid = -((config.MARKET_VOLATILITY_MEDIUM + config.MARKET_VOLATILITY_HIGH) / 2)
        snaps = [_snap("Nikkei", "asia", mid)]
        signals = detect_volatility(snaps)
        assert len(signals) == 1
        assert signals[0]["severity"] == "MEDIUM"
        assert "down" in signals[0]["message"]

    def test_below_threshold_produces_no_signal(self):
        snaps = [_snap("FTSE", "europe", 0.1)]
        assert detect_volatility(snaps) == []

    def test_signal_contains_expected_fields(self):
        snaps = [_snap("SPX", "us", 3.0)]
        sig = detect_volatility(snaps)[0]
        assert sig["symbol"] == "^GSPC"
        assert sig["name"] == "SPX"
        assert sig["region"] == "us"
        assert sig["change_pct"] == pytest.approx(3.0)

    def test_cross_market_bullish_correlation(self):
        """3+ indices up >1% across 2+ regions → global rally signal."""
        snaps = [
            _snap("SPX", "us", 2.0),
            _snap("DAX", "europe", 1.5),
            _snap("Nikkei", "asia", 1.8),
        ]
        signals = detect_volatility(snaps)
        types = [s["type"] for s in signals]
        assert "cross_market_correlation" in types
        cm = next(s for s in signals if s["type"] == "cross_market_correlation")
        assert cm["severity"] == "HIGH"
        assert "rally" in cm["message"].lower()
        assert cm["region"] == "global"

    def test_cross_market_bearish_correlation(self):
        """3+ indices down >1% across 2+ regions → global sell-off signal."""
        snaps = [
            _snap("SPX", "us", -2.0),
            _snap("DAX", "europe", -1.5),
            _snap("Nikkei", "asia", -1.8),
        ]
        signals = detect_volatility(snaps)
        types = [s["type"] for s in signals]
        assert "cross_market_correlation" in types
        cm = next(s for s in signals if s["type"] == "cross_market_correlation")
        assert "sell-off" in cm["message"].lower()

    def test_no_cross_market_when_same_region(self):
        """3 indices all in the same region should NOT trigger correlation."""
        snaps = [
            _snap("A", "us", 2.0),
            _snap("B", "us", 1.5),
            _snap("C", "us", 1.8),
        ]
        signals = detect_volatility(snaps)
        types = [s["type"] for s in signals]
        assert "cross_market_correlation" not in types

    def test_no_cross_market_when_fewer_than_three(self):
        snaps = [
            _snap("SPX", "us", 2.0),
            _snap("DAX", "europe", 1.5),
        ]
        signals = detect_volatility(snaps)
        types = [s["type"] for s in signals]
        assert "cross_market_correlation" not in types

    def test_cross_market_change_pct_is_max_for_bullish(self):
        snaps = [
            _snap("A", "us", 3.0),
            _snap("B", "europe", 1.5),
            _snap("C", "asia", 2.0),
        ]
        signals = detect_volatility(snaps)
        cm = next(s for s in signals if s["type"] == "cross_market_correlation")
        assert cm["change_pct"] == pytest.approx(3.0)

    def test_cross_market_change_pct_is_min_for_bearish(self):
        snaps = [
            _snap("A", "us", -3.0),
            _snap("B", "europe", -1.5),
            _snap("C", "asia", -2.0),
        ]
        signals = detect_volatility(snaps)
        cm = next(s for s in signals if s["type"] == "cross_market_correlation")
        assert cm["change_pct"] == pytest.approx(-3.0)


class TestFetchSnapshots:
    def test_returns_empty_when_disabled(self):
        with patch.object(config, "MARKET_DATA_ENABLED", False):
            result = fetch_snapshots()
        assert result == []

    def test_skips_ticker_with_no_price(self):
        mock_info = MagicMock()
        mock_info.last_price = None
        mock_info.previous_close = None
        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info

        with patch("core.market_data.config.MARKET_DATA_ENABLED", True), \
             patch("core.market_data.config.MARKET_TICKERS", {"us": {"SPX": "^GSPC"}}), \
             patch("core.market_data.yf.Ticker", return_value=mock_ticker), \
             patch("core.market_data.time.sleep"):
            result = fetch_snapshots()
        assert result == []

    def test_logs_warning_on_ticker_exception(self):
        with patch("core.market_data.config.MARKET_DATA_ENABLED", True), \
             patch("core.market_data.config.MARKET_TICKERS", {"us": {"SPX": "^GSPC"}}), \
             patch("core.market_data.yf.Ticker", side_effect=RuntimeError("network")), \
             patch("core.market_data.time.sleep"):
            result = fetch_snapshots()
        assert result == []

    def test_returns_snapshot_for_valid_ticker(self):
        mock_info = MagicMock()
        mock_info.last_price = 5100.0
        mock_info.previous_close = 5000.0
        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info

        with patch("core.market_data.config.MARKET_DATA_ENABLED", True), \
             patch("core.market_data.config.MARKET_TICKERS", {"us": {"SPX": "^GSPC"}}), \
             patch("core.market_data.yf.Ticker", return_value=mock_ticker), \
             patch("core.market_data.time.sleep"):
            result = fetch_snapshots()

        assert len(result) == 1
        assert result[0]["symbol"] == "^GSPC"
        assert result[0]["change_pct"] == pytest.approx(2.0)


class TestGetLatestSnapshots:
    def test_delegates_to_storage(self):
        with patch("core.storage.get_latest_market_data", return_value=[{"symbol": "SPY"}]):
            result = get_latest_snapshots()
        assert result == [{"symbol": "SPY"}]
