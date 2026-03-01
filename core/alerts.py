"""
Alert dispatch — prints to console and optionally posts to a Slack webhook.
Console output is structured so it's easy to grep in a terminal session.
"""

import json
import logging
from datetime import datetime, timezone

import requests

from . import config

log = logging.getLogger(__name__)

# ANSI color codes for terminal readability
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_CYAN   = "\033[96m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

_LEVEL_COLOR = {
    "HIGH":   _RED + _BOLD,
    "MEDIUM": _YELLOW,
    "LOW":    _CYAN,
}
_SURGE_COLOR = "\033[95m" + _BOLD  # Magenta bold


def _color(level: str, text: str) -> str:
    return f"{_LEVEL_COLOR.get(level, '')}{text}{_RESET}"


def alert_article(article: dict, result: dict) -> None:
    """Print a single classified article. Always shown for HIGH; summarized for others."""
    level = result.get("classification", "LOW")
    conf  = result.get("confidence", 0.0)
    reason = result.get("reason", "")
    title  = article.get("title", "")
    source = article.get("source", "")
    pub    = article.get("published_at", "")
    if isinstance(pub, datetime):
        pub = pub.strftime("%Y-%m-%d %H:%M UTC")

    print(
        f"{_color(level, f'[{level}]')} "
        f"{_BOLD}{title}{_RESET}\n"
        f"  Source: {source}  |  Published: {pub}  |  Confidence: {conf:.0%}\n"
        f"  Reason: {reason}"
    )

    # Slack for HIGH only (when configured)
    if level == "HIGH" and config.SLACK_WEBHOOK_URL:
        _post_slack({
            "text": f":rotating_light: *HIGH IMPACT NEWS*\n*{title}*\n_{reason}_\nSource: {source}",
        })


def alert_surge(count: int, recent_titles: list[str], window_minutes: int) -> None:
    """Print and optionally Slack a NEWS SURGE alert."""
    titles_fmt = "\n  • ".join(recent_titles[:5])
    msg = (
        f"{_SURGE_COLOR}{'='*60}\n"
        f"  NEWS SURGE: {count} HIGH events in last {window_minutes} min\n"
        f"  Expect elevated brokerage login volume shortly.\n"
        f"  Recent events:\n  • {titles_fmt}\n"
        f"{'='*60}{_RESET}"
    )
    print(msg)
    log.warning("NEWS SURGE: %d HIGH events in %d min window", count, window_minutes)

    if config.SLACK_WEBHOOK_URL:
        bullet_list = "\n• ".join(recent_titles[:5])
        _post_slack({
            "text": (
                f":loudspeaker: *NEWS SURGE DETECTED*\n"
                f"{count} HIGH-impact events in the last {window_minutes} minutes.\n"
                f"Expect elevated login volume. Prepare backend systems.\n"
                f"Recent events:\n• {bullet_list}"
            )
        })


def _post_slack(payload: dict) -> None:
    if not config.SLACK_WEBHOOK_URL:
        return
    try:
        resp = requests.post(
            config.SLACK_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
        if resp.status_code != 200:
            log.warning("Slack webhook returned %s: %s", resp.status_code, resp.text)
    except Exception as e:
        log.warning("Slack post failed: %s", e)
