"""
Brokerage login volume predictor.

Combines news classification, market volatility, surge state, and sentiment
into a single composite score, then maps it to a labelled prediction level.

This is a pure function module — no I/O, no DB access.  All inputs are
passed in so the logic is easy to unit-test and the weights easy to tune.

Scoring weights (starting values — tune empirically using actual_impact data):

  News signals (30-min window)
    Surge active                        +40
    Each HIGH event  (max 3, i.e. +30)  +10 each
    Each MEDIUM event (max 3, i.e. +12) +4  each

  Market signals
    HIGH-severity volatility signal      +10 each (max 2, i.e. +20)
    MEDIUM-severity volatility signal    +5  each (max 2, i.e. +10)
    Cross-market correlation signal      +10 (counts once regardless of count)

  Sentiment
    overall_sentiment_score <= -0.5      +8   (fear / panic selling)
    overall_sentiment_score >=  0.5      +5   (euphoria / FOMO buying)

Level thresholds
    >= 60  →  SURGE    (level 4)
    >= 35  →  ELEVATED (level 3)
    >= 15  →  MODERATE (level 2)
    <  15  →  NORMAL   (level 1)
"""

from typing import Optional


# ---------------------------------------------------------------------------
# Weights — adjust here to tune the model
# ---------------------------------------------------------------------------
W_SURGE_ACTIVE      = 40
W_HIGH_EVENT        = 10
W_HIGH_EVENT_MAX    = 3   # cap on number of HIGH events scored
W_MEDIUM_EVENT      = 4
W_MEDIUM_EVENT_MAX  = 3
W_MARKET_HIGH       = 10
W_MARKET_HIGH_MAX   = 2
W_MARKET_MEDIUM     = 5
W_MARKET_MEDIUM_MAX = 2
W_CROSS_MARKET      = 10  # added once if any cross-market signal present
W_SENTIMENT_FEAR    = 8   # score <= -0.5
W_SENTIMENT_EUPHORIA= 5   # score >= +0.5

# Level thresholds
LEVEL_SURGE    = 60
LEVEL_ELEVATED = 35
LEVEL_MODERATE = 15

LEVELS = {
    4: {
        "label": "SURGE", "color": "red", "volume": "75%+ above baseline",
        "action": "All hands — expect significant login queue pressure",
        "tooltip": "Activate incident response. Login queues may be forming. Notify infrastructure and support teams immediately. Reassess every 5 minutes.",
    },
    3: {
        "label": "ELEVATED", "color": "orange", "volume": "25–75% above baseline",
        "action": "Monitor closely — consider additional resources",
        "tooltip": "Alert on-call team and review capacity. Volumes are significantly above baseline and may continue to rise. Reassess every 10 minutes.",
    },
    2: {
        "label": "MODERATE", "color": "yellow", "volume": "10–25% above baseline",
        "action": "Watch for escalation",
        "tooltip": "No intervention required yet. Volumes are running slightly above baseline. Monitor for additional HIGH events or market signals that could push this to ELEVATED.",
    },
    1: {
        "label": "NORMAL", "color": "green", "volume": "Baseline",
        "action": "No action needed",
        "tooltip": "Login volumes are within expected baseline range. Continue normal monitoring.",
    },
}


def compute_score(
    surge_active: bool,
    high_count_in_window: int,
    medium_count_in_window: int,
    market_signals: Optional[list] = None,
    sentiment_score: float = 0.0,
) -> dict:
    """
    Compute the volume prediction score and return a result dict.

    Parameters
    ----------
    surge_active : bool
        Whether the spike detector has fired a SURGE.
    high_count_in_window : int
        Number of HIGH-classified events in the current spike window.
    medium_count_in_window : int
        Number of MEDIUM-classified events in the current spike window.
    market_signals : list of dicts, optional
        Volatility signal dicts from market_data.detect_volatility().
        Each dict must have at least ``severity`` (HIGH|MEDIUM) and
        ``type`` (index_move|cross_market_correlation) keys.
    sentiment_score : float
        Overall weighted sentiment score in [-1.0, 1.0] from /events/summary.

    Returns
    -------
    dict with keys:
        level       int   1–4
        label       str   NORMAL / MODERATE / ELEVATED / SURGE
        color       str   green / yellow / orange / red
        score       int   raw composite score (0–100+)
        drivers     list  plain-English strings explaining top contributors
    """
    if market_signals is None:
        market_signals = []

    score = 0
    drivers = []

    # --- Surge active -------------------------------------------------------
    if surge_active:
        score += W_SURGE_ACTIVE
        drivers.append("Surge active")

    # --- HIGH events --------------------------------------------------------
    capped_high = min(high_count_in_window, W_HIGH_EVENT_MAX)
    if capped_high:
        score += capped_high * W_HIGH_EVENT
        drivers.append(f"{capped_high} HIGH event{'s' if capped_high > 1 else ''} in window")

    # --- MEDIUM events ------------------------------------------------------
    capped_med = min(medium_count_in_window, W_MEDIUM_EVENT_MAX)
    if capped_med:
        score += capped_med * W_MEDIUM_EVENT
        drivers.append(f"{capped_med} MEDIUM event{'s' if capped_med > 1 else ''} in window")

    # --- Market volatility signals ------------------------------------------
    high_mkt   = [s for s in market_signals if s.get("severity") == "HIGH"   and s.get("type") == "index_move"]
    medium_mkt = [s for s in market_signals if s.get("severity") == "MEDIUM" and s.get("type") == "index_move"]
    cross      = [s for s in market_signals if s.get("type") == "cross_market_correlation"]

    capped_high_mkt = min(len(high_mkt), W_MARKET_HIGH_MAX)
    if capped_high_mkt:
        score += capped_high_mkt * W_MARKET_HIGH
        names = ", ".join(s.get("name", s.get("symbol", "?")) for s in high_mkt[:capped_high_mkt])
        drivers.append(f"High market volatility: {names}")

    capped_med_mkt = min(len(medium_mkt), W_MARKET_MEDIUM_MAX)
    if capped_med_mkt:
        score += capped_med_mkt * W_MARKET_MEDIUM
        names = ", ".join(s.get("name", s.get("symbol", "?")) for s in medium_mkt[:capped_med_mkt])
        drivers.append(f"Moderate market volatility: {names}")

    if cross:
        score += W_CROSS_MARKET
        drivers.append(cross[0].get("message", "Cross-market correlation signal"))

    # --- Sentiment ----------------------------------------------------------
    if sentiment_score <= -0.5:
        score += W_SENTIMENT_FEAR
        drivers.append("Negative sentiment (fear / selling pressure)")
    elif sentiment_score >= 0.5:
        score += W_SENTIMENT_EUPHORIA
        drivers.append("Positive sentiment (euphoria / buying pressure)")

    # --- Map to level -------------------------------------------------------
    if score >= LEVEL_SURGE:
        level = 4
    elif score >= LEVEL_ELEVATED:
        level = 3
    elif score >= LEVEL_MODERATE:
        level = 2
    else:
        level = 1

    return {
        "level": level,
        "label": LEVELS[level]["label"],
        "color": LEVELS[level]["color"],
        "volume": LEVELS[level]["volume"],
        "action": LEVELS[level]["action"],
        "tooltip": LEVELS[level]["tooltip"],
        "score": score,
        "drivers": drivers,
    }
