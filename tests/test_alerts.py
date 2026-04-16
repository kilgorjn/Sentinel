"""Tests for core/alerts.py — console output and webhook dispatch."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from core import alerts, config


def _article(title="Fed Cuts Rates", source="Reuters", published_at=None):
    return {
        "title": title,
        "source": source,
        "published_at": published_at or datetime.now(timezone.utc),
    }


def _result(classification="LOW", confidence=0.8, reason="Test reason"):
    return {
        "classification": classification,
        "confidence": confidence,
        "reason": reason,
    }


def _ok_response(status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = "ok"
    return resp


class TestAlertArticle:
    def test_prints_title_and_source(self, capsys):
        alerts.alert_article(_article("Market Rally"), _result())
        out = capsys.readouterr().out
        assert "Market Rally" in out
        assert "Reuters" in out

    def test_prints_classification_level(self, capsys):
        alerts.alert_article(_article(), _result("HIGH"))
        out = capsys.readouterr().out
        assert "HIGH" in out

    def test_formats_datetime_published_at(self, capsys):
        pub = datetime(2026, 4, 15, 10, 30, 0, tzinfo=timezone.utc)
        alerts.alert_article(_article(published_at=pub), _result())
        out = capsys.readouterr().out
        assert "2026-04-15" in out

    def test_no_slack_when_not_configured(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", None), \
             patch("core.alerts.requests.post") as mock_post:
            alerts.alert_article(_article(), _result("HIGH"))
        mock_post.assert_not_called()

    def test_no_discord_when_not_configured(self):
        with patch.object(config, "DISCORD_WEBHOOK_URL", None), \
             patch("core.alerts.requests.post") as mock_post:
            alerts.alert_article(_article(), _result("HIGH"))
        mock_post.assert_not_called()

    def test_slack_posted_for_high(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch.object(config, "DISCORD_WEBHOOK_URL", None), \
             patch("core.alerts.requests.post", return_value=_ok_response()) as mock_post:
            alerts.alert_article(_article(), _result("HIGH"))
        mock_post.assert_called_once()

    def test_no_slack_for_medium(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch("core.alerts.requests.post") as mock_post:
            alerts.alert_article(_article(), _result("MEDIUM"))
        mock_post.assert_not_called()

    def test_no_slack_for_low(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch("core.alerts.requests.post") as mock_post:
            alerts.alert_article(_article(), _result("LOW"))
        mock_post.assert_not_called()

    def test_discord_posted_for_high(self):
        with patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/test"), \
             patch.object(config, "SLACK_WEBHOOK_URL", None), \
             patch("core.alerts.requests.post", return_value=_ok_response(204)) as mock_post:
            alerts.alert_article(_article(), _result("HIGH"))
        mock_post.assert_called_once()


class TestAlertSurge:
    def test_prints_surge_message(self, capsys):
        alerts.alert_surge(3, ["Headline A", "Headline B"], 30)
        out = capsys.readouterr().out
        assert "SURGE" in out
        assert "Headline A" in out
        assert "30" in out

    def test_slack_sent_when_configured(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch.object(config, "DISCORD_WEBHOOK_URL", None), \
             patch("core.alerts.requests.post", return_value=_ok_response()) as mock_post:
            alerts.alert_surge(3, ["Headline A"], 30)
        mock_post.assert_called_once()

    def test_discord_sent_when_configured(self):
        with patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/test"), \
             patch.object(config, "SLACK_WEBHOOK_URL", None), \
             patch("core.alerts.requests.post", return_value=_ok_response(204)) as mock_post:
            alerts.alert_surge(3, ["Headline A"], 30)
        mock_post.assert_called_once()

    def test_no_webhooks_when_not_configured(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", None), \
             patch.object(config, "DISCORD_WEBHOOK_URL", None), \
             patch("core.alerts.requests.post") as mock_post:
            alerts.alert_surge(3, ["Headline A"], 30)
        mock_post.assert_not_called()

    def test_truncates_to_five_titles(self, capsys):
        titles = [f"Headline {i}" for i in range(10)]
        alerts.alert_surge(10, titles, 30)
        out = capsys.readouterr().out
        assert "Headline 4" in out
        assert "Headline 5" not in out


class TestAlertMarketSignal:
    def test_prints_signal_message(self, capsys):
        signal = {"severity": "HIGH", "message": "SPX dropped 3%", "region": "us", "change_pct": -3.0}
        alerts.alert_market_signal(signal)
        out = capsys.readouterr().out
        assert "MARKET SIGNAL" in out
        assert "SPX dropped 3%" in out

    def test_down_arrow_for_negative_change(self, capsys):
        signal = {"severity": "LOW", "message": "down", "region": "us", "change_pct": -1.0}
        alerts.alert_market_signal(signal)
        assert "▼" in capsys.readouterr().out

    def test_up_arrow_for_positive_change(self, capsys):
        signal = {"severity": "LOW", "message": "up", "region": "us", "change_pct": 1.0}
        alerts.alert_market_signal(signal)
        assert "▲" in capsys.readouterr().out

    def test_slack_sent_for_high_market_signal(self):
        signal = {"severity": "HIGH", "message": "Crash", "region": "us", "change_pct": -3.0}
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch.object(config, "DISCORD_WEBHOOK_URL", None), \
             patch("core.alerts.requests.post", return_value=_ok_response()) as mock_post:
            alerts.alert_market_signal(signal)
        mock_post.assert_called_once()

    def test_no_slack_for_medium_market_signal(self):
        signal = {"severity": "MEDIUM", "message": "Move", "region": "us", "change_pct": -1.0}
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch("core.alerts.requests.post") as mock_post:
            alerts.alert_market_signal(signal)
        mock_post.assert_not_called()


class TestPostSlack:
    def test_skips_when_no_url(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", None), \
             patch("core.alerts.requests.post") as mock_post:
            alerts._post_slack({"text": "test"})
        mock_post.assert_not_called()

    def test_skips_empty_string_url(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", ""), \
             patch("core.alerts.requests.post") as mock_post:
            alerts._post_slack({"text": "test"})
        mock_post.assert_not_called()

    def test_posts_payload(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch("core.alerts.requests.post", return_value=_ok_response()) as mock_post:
            alerts._post_slack({"text": "hello"})
        mock_post.assert_called_once()
        assert mock_post.call_args[1]["json"] == {"text": "hello"}

    def test_logs_warning_on_non_200(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch("core.alerts.requests.post", return_value=_ok_response(500)), \
             patch("core.alerts.log") as mock_log:
            alerts._post_slack({"text": "test"})
        mock_log.warning.assert_called()

    def test_logs_warning_on_exception(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch("core.alerts.requests.post", side_effect=Exception("network error")), \
             patch("core.alerts.log") as mock_log:
            alerts._post_slack({"text": "test"})
        mock_log.warning.assert_called()


class TestPostDiscord:
    def test_skips_when_no_url(self):
        with patch.object(config, "DISCORD_WEBHOOK_URL", None), \
             patch("core.alerts.requests.post") as mock_post:
            alerts._post_discord({"title": "test"})
        mock_post.assert_not_called()

    def test_posts_embed_payload(self):
        with patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/test"), \
             patch("core.alerts.requests.post", return_value=_ok_response(204)) as mock_post:
            alerts._post_discord({"title": "test embed"})
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert "embeds" in payload
        assert payload["embeds"][0]["title"] == "test embed"

    def test_logs_warning_on_non_200_204(self):
        with patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/test"), \
             patch("core.alerts.requests.post", return_value=_ok_response(500)), \
             patch("core.alerts.log") as mock_log:
            alerts._post_discord({"title": "test"})
        mock_log.warning.assert_called()

    def test_logs_warning_on_exception(self):
        with patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/test"), \
             patch("core.alerts.requests.post", side_effect=Exception("timeout")), \
             patch("core.alerts.log") as mock_log:
            alerts._post_discord({"title": "test"})
        mock_log.warning.assert_called()
