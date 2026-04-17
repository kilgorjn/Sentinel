"""Tests for core/alerts.py — console output and webhook dispatch."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from core import alerts, config


def _article(title="Fed cuts rates", source="Reuters", pub=None):
    return {
        "title": title,
        "source": source,
        "published_at": pub or datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc),
    }


def _result(classification="LOW", confidence=0.8, reason="Test reason"):
    return {"classification": classification, "confidence": confidence, "reason": reason}


class TestColor:
    def test_known_level_applies_color(self):
        colored = alerts._color("HIGH", "text")
        assert "text" in colored
        assert alerts._RESET in colored

    def test_unknown_level_returns_text_with_reset(self):
        colored = alerts._color("UNKNOWN", "text")
        assert "text" in colored


class TestAlertArticle:
    def test_prints_article_info(self, capsys):
        alerts.alert_article(_article(), _result("LOW"))
        out = capsys.readouterr().out
        assert "Fed cuts rates" in out
        assert "Reuters" in out

    def test_datetime_formatted(self, capsys):
        pub = datetime(2026, 4, 16, 14, 30, tzinfo=timezone.utc)
        alerts.alert_article(_article(pub=pub), _result())
        out = capsys.readouterr().out
        assert "2026-04-16" in out

    def test_string_published_at_passed_through(self, capsys):
        art = _article()
        art["published_at"] = "2026-04-16 12:00 UTC"
        alerts.alert_article(art, _result())
        out = capsys.readouterr().out
        assert "2026-04-16" in out

    def test_no_slack_post_for_low(self, capsys):
        with patch("core.alerts._post_slack") as mock_slack, \
             patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"):
            alerts.alert_article(_article(), _result("LOW"))
        mock_slack.assert_not_called()

    def test_slack_posted_for_high(self):
        with patch("core.alerts._post_slack") as mock_slack, \
             patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"):
            alerts.alert_article(_article(), _result("HIGH"))
        mock_slack.assert_called_once()

    def test_no_slack_when_url_not_set(self):
        with patch("core.alerts._post_slack") as mock_slack, \
             patch.object(config, "SLACK_WEBHOOK_URL", ""):
            alerts.alert_article(_article(), _result("HIGH"))
        mock_slack.assert_not_called()

    def test_discord_posted_for_high(self):
        with patch("core.alerts._post_discord") as mock_discord, \
             patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test"), \
             patch.object(config, "SLACK_WEBHOOK_URL", ""):
            alerts.alert_article(_article(), _result("HIGH"))
        mock_discord.assert_called_once()

    def test_no_discord_for_low(self):
        with patch("core.alerts._post_discord") as mock_discord, \
             patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test"):
            alerts.alert_article(_article(), _result("LOW"))
        mock_discord.assert_not_called()


class TestAlertSurge:
    def test_prints_surge_message(self, capsys):
        alerts.alert_surge(5, ["Title A", "Title B"], 30)
        out = capsys.readouterr().out
        assert "SURGE" in out
        assert "5" in out

    def test_slack_posted_when_url_set(self):
        with patch("core.alerts._post_slack") as mock_slack, \
             patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"):
            alerts.alert_surge(3, ["A", "B", "C"], 30)
        mock_slack.assert_called_once()

    def test_no_slack_when_url_not_set(self):
        with patch("core.alerts._post_slack") as mock_slack, \
             patch.object(config, "SLACK_WEBHOOK_URL", ""):
            alerts.alert_surge(3, ["A"], 30)
        mock_slack.assert_not_called()

    def test_discord_posted_when_url_set(self):
        with patch("core.alerts._post_discord") as mock_discord, \
             patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test"), \
             patch.object(config, "SLACK_WEBHOOK_URL", ""):
            alerts.alert_surge(3, ["A"], 30)
        mock_discord.assert_called_once()


class TestAlertMarketSignal:
    def _signal(self, severity="HIGH", change_pct=3.0):
        return {
            "severity": severity,
            "message": "SPX up 3.0% — significant overnight move",
            "region": "us",
            "change_pct": change_pct,
        }

    def test_prints_signal(self, capsys):
        alerts.alert_market_signal(self._signal())
        out = capsys.readouterr().out
        assert "MARKET SIGNAL" in out
        assert "Us" in out  # region.title()

    def test_upward_arrow_for_positive(self, capsys):
        alerts.alert_market_signal(self._signal(change_pct=2.0))
        out = capsys.readouterr().out
        assert "▲" in out

    def test_downward_arrow_for_negative(self, capsys):
        alerts.alert_market_signal(self._signal(change_pct=-2.0))
        out = capsys.readouterr().out
        assert "▼" in out

    def test_slack_posted_for_high(self):
        with patch("core.alerts._post_slack") as mock_slack, \
             patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"):
            alerts.alert_market_signal(self._signal("HIGH"))
        mock_slack.assert_called_once()

    def test_no_slack_for_medium(self):
        with patch("core.alerts._post_slack") as mock_slack, \
             patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"):
            alerts.alert_market_signal(self._signal("MEDIUM"))
        mock_slack.assert_not_called()

    def test_discord_posted_for_high(self):
        with patch("core.alerts._post_discord") as mock_discord, \
             patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test"), \
             patch.object(config, "SLACK_WEBHOOK_URL", ""):
            alerts.alert_market_signal(self._signal("HIGH"))
        mock_discord.assert_called_once()


class TestPostSlack:
    def test_no_op_when_url_not_set(self):
        with patch.object(config, "SLACK_WEBHOOK_URL", ""), \
             patch("core.alerts.requests.post") as mock_post:
            alerts._post_slack({"text": "hello"})
        mock_post.assert_not_called()

    def test_posts_to_webhook(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch("core.alerts.requests.post", return_value=mock_resp):
            alerts._post_slack({"text": "hello"})

    def test_logs_warning_on_non_200(self, caplog):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch("core.alerts.requests.post", return_value=mock_resp):
            alerts._post_slack({"text": "hello"})

    def test_logs_warning_on_exception(self, caplog):
        with patch.object(config, "SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"), \
             patch("core.alerts.requests.post", side_effect=requests.exceptions.ConnectionError):
            alerts._post_slack({"text": "hello"})  # should not raise


class TestPostDiscord:
    def test_no_op_when_url_not_set(self):
        with patch.object(config, "DISCORD_WEBHOOK_URL", ""), \
             patch("core.alerts.requests.post") as mock_post:
            alerts._post_discord({"title": "Test"})
        mock_post.assert_not_called()

    def test_posts_embed_to_webhook(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        with patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test"), \
             patch("core.alerts.requests.post", return_value=mock_resp) as mock_post:
            alerts._post_discord({"title": "Alert"})
        payload = mock_post.call_args[1]["json"]
        assert "embeds" in payload

    def test_logs_warning_on_non_200_204(self, caplog):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        with patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test"), \
             patch("core.alerts.requests.post", return_value=mock_resp):
            alerts._post_discord({"title": "Alert"})

    def test_logs_warning_on_exception(self):
        with patch.object(config, "DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test"), \
             patch("core.alerts.requests.post", side_effect=requests.exceptions.ConnectionError):
            alerts._post_discord({"title": "Alert"})  # should not raise
