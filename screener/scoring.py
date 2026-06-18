"""Potential Score (0-100) computation and signal labelling.

Each category produces a 0-100 sub-score plus an "available" flag.  Final score
is the weighted average over AVAILABLE categories (weights renormalize), so the
number always reflects real signals, and we report data_coverage separately.
"""
from __future__ import annotations

from config import WEIGHTS, VOLUME_RATIO_TIERS, TIERS


def _clamp(x: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Category sub-scores
# ---------------------------------------------------------------------------
def score_technical(tech: dict, strength: dict, brk: dict, rsi_val) -> float:
    """技術面: EMA stack, price location, breakouts, RSI health, rel-strength."""
    s = 50.0
    if tech.get("bull_stack"):
        s += 18
    elif tech.get("ema20") and tech.get("ema50") and tech["ema20"] > tech["ema50"]:
        s += 8
    if tech.get("above_ema20"):
        s += 8
    # breakouts
    s += 6 * sum(1 for k in ("prior_high", "box", "downtrend", "boll_upper") if brk.get(k))
    # RSI: reward momentum but penalize blow-off > 80
    if rsi_val is not None:
        if 55 <= rsi_val <= 72:
            s += 8
        elif rsi_val > 80:
            s -= 10
        elif rsi_val < 40:
            s -= 6
    # relative strength contributes here too
    if strength.get("beats_btc"):
        s += 6
    if strength.get("beats_eth"):
        s += 4
    return _clamp(s)


def volume_bonus(vr) -> float:
    if vr is None:
        return 0.0
    for thr, pts in VOLUME_RATIO_TIERS:
        if vr >= thr:
            return float(pts)
    return 0.0


def score_capital(vr, oi_chg, funding, price_chg, flows, liq, taker_ratio) -> tuple[float, bool]:
    """資金流: volume anomaly + OI + funding + flows + liquidations + taker flow."""
    available = False
    s = 50.0
    # volume anomaly (always available from Binance)
    if vr is not None:
        available = True
        s += volume_bonus(vr)
    # open interest
    if oi_chg is not None:
        available = True
        if oi_chg > 20:
            s += 18
        elif oi_chg > 10:
            s += 12
        elif oi_chg > 5:
            s += 6
        elif oi_chg < -10:
            s -= 8
        # OI up + price up = strongest
        if oi_chg > 10 and price_chg is not None and price_chg > 0:
            s += 6
    # funding rate: extreme positive = crowded long (risk), slight pos healthy
    if funding is not None:
        available = True
        fpct = funding * 100
        if fpct > 0.1:
            s -= 6          # very crowded long, squeeze risk
        elif 0 < fpct <= 0.05:
            s += 4
        elif fpct < -0.05:
            s += 8          # crowded short, squeeze-up fuel
    # taker buy/sell aggression
    if taker_ratio is not None:
        available = True
        if taker_ratio > 1.15:
            s += 6
        elif taker_ratio < 0.85:
            s -= 4
    # smart-money + exchange flows (paid)
    if flows.whale_netflow_usd is not None:
        available = True
        s += 10 if flows.whale_netflow_usd > 0 else -8
    if flows.exchange_netflow_usd is not None:
        available = True
        # negative netflow (outflow) = bullish
        s += 8 if flows.exchange_netflow_usd < 0 else -6
    # liquidations (paid): short liqs dominating = upside acceleration
    if liq:
        available = True
        long_l = liq.get("long_usd", 0) or 0
        short_l = liq.get("short_usd", 0) or 0
        if short_l > long_l * 1.5:
            s += 8
        elif long_l > short_l * 1.5:
            s -= 6
    return _clamp(s), available


def score_onchain(oc) -> tuple[float, bool]:
    """鏈上數據: address/tx growth (Glassnode) + TVL fund-flow (DefiLlama)."""
    s = 50.0
    available = False
    # address / tx growth (keyed)
    for g in (oc.active_addresses_growth_pct, oc.new_addresses_growth_pct,
              oc.tx_count_growth_pct):
        if g is None:
            continue
        available = True
        if g > 30:
            s += 14
        elif g > 10:
            s += 7
        elif g < -10:
            s -= 6
    # TVL fund-flow (keyless DefiLlama)
    if oc.tvl_change_7d is not None:
        available = True
        c7 = oc.tvl_change_7d
        if c7 > 30:
            s += 14
        elif c7 > 10:
            s += 7
        elif c7 < -10:
            s -= 6
    if oc.tvl_change_1d is not None:
        available = True
        c1 = oc.tvl_change_1d
        if c1 > 10:
            s += 8
        elif c1 < -10:
            s -= 5
    return _clamp(s), available


def score_sentiment(soc, global_fng=None) -> tuple[float, bool]:
    """情緒: per-coin social mention growth (LunarCrush) or fall back to the
    market-wide Fear & Greed index (Alternative.me, keyless)."""
    if soc.mention_growth_pct is None and soc.galaxy_score is None:
        if global_fng is None:
            return 50.0, False
        return _clamp(50 + (global_fng - 50) * 0.4), True
    s = 50.0
    if soc.mention_growth_pct is not None:
        g = soc.mention_growth_pct
        if g > 300:
            s += 30
        elif g > 100:
            s += 18
        elif g > 30:
            s += 8
    if soc.galaxy_score is not None:
        s += (soc.galaxy_score - 50) * 0.3
    return _clamp(s), True


def score_event(ev) -> tuple[float, bool]:
    """事件: listings / mainnet / news catalysts (paid)."""
    if not (ev.upcoming or ev.has_listing or ev.has_mainnet or ev.has_major_news):
        return 50.0, False
    s = 55.0
    if ev.has_listing:
        s += 25
    if ev.has_mainnet:
        s += 15
    if ev.has_major_news:
        s += 10
    return _clamp(s), True


# ---------------------------------------------------------------------------
# Combine
# ---------------------------------------------------------------------------
def potential_score(sub: dict) -> dict:
    """sub = {category: (score, available)} for capital/onchain/sentiment/event,
    plus 'technical': score (always available).  Returns final score + coverage.
    """
    parts = {
        "technical": (sub["technical"], True),
        "capital":   sub["capital"],
        "onchain":   sub["onchain"],
        "sentiment": sub["sentiment"],
        "event":     sub["event"],
    }
    total_w = sum(WEIGHTS[k] for k, (_, av) in parts.items() if av)
    if total_w == 0:
        return {"score": 0.0, "coverage": 0.0}
    score = sum(WEIGHTS[k] * sc for k, (sc, av) in parts.items() if av) / total_w
    coverage = total_w  # fraction of nominal weight backed by live data
    return {"score": round(score, 1), "coverage": round(coverage * 100)}


def signal_label(score: float) -> str:
    for thr, label in TIERS:
        if score >= thr:
            return label
    return TIERS[-1][1]
