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

    # Discord for HIGH only (when configured)
    if level == "HIGH" and config.DISCORD_WEBHOOK_URL:
        _post_discord({
            "title": "🚨 High Impact News",
            "description": f"**{title}**\n_{reason}_",
            "color": _DISCORD_COLORS["HIGH"],
            "footer": {"text": source},
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

    if config.DISCORD_WEBHOOK_URL:
        bullet_list = "\n• ".join(recent_titles[:5])
        _post_discord({
            "title": "📢 News Surge Detected",
            "description": (
                f"{count} HIGH-impact events in the last {window_minutes} minutes.\n"
                f"Expect elevated login volume.\n\n"
                f"**Recent events:**\n• {bullet_list}"
            ),
            "color": _DISCORD_COLORS["SURGE"],
        })


def alert_market_signal(signal: dict) -> None:
    """Print a market volatility signal."""
    level = signal.get("severity", "MEDIUM")
    msg = signal.get("message", "")
    region = signal.get("region", "").title()
    change = signal.get("change_pct", 0)
    direction = "▲" if change > 0 else "▼"

    print(
        f"{_color(level, f'[{level}]')} "
        f"{_BOLD}MARKET SIGNAL{_RESET} ({region}) "
        f"{direction} {msg}"
    )

    # Slack for HIGH market signals
    if level == "HIGH" and config.SLACK_WEBHOOK_URL:
        _post_slack({
            "text": f":chart_with_downwards_trend: *MARKET VOLATILITY*\n{msg}\nRegion: {region}",
        })

    # Discord for HIGH market signals
    if level == "HIGH" and config.DISCORD_WEBHOOK_URL:
        _post_discord({
            "title": "📉 Market Volatility Signal",
            "description": f"{direction} {msg}",
            "color": _DISCORD_COLORS["MARKET"],
            "footer": {"text": region},
        })


def _post_slack(payload: dict) -> None:
    if not config.SLACK_WEBHOOK_URL:
        return
    try:
        resp = requests.post(config.SLACK_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code != 200:
            log.warning("Slack webhook returned %s: %s", resp.status_code, resp.text)
    except Exception as e:
        log.warning("Slack post failed: %s", e)


# Discord embed colors
_DISCORD_COLORS = {
    "HIGH":   0xe05252,   # red
    "MEDIUM": 0xe0a832,   # amber
    "LOW":    0x4a9eda,   # blue
    "SURGE":  0x9b59b6,   # purple
    "MARKET": 0xe67e22,   # orange
}


def _post_discord(embed: dict) -> None:
    if not config.DISCORD_WEBHOOK_URL:
        return
    try:
        resp = requests.post(
            config.DISCORD_WEBHOOK_URL,
            json={"embeds": [embed]},
            timeout=10,
        )
        if resp.status_code not in (200, 204):
            log.warning("Discord webhook returned %s: %s", resp.status_code, resp.text)
    except Exception as e:
        log.warning("Discord post failed: %s", e)
