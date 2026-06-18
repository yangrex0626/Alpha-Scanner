"""Technical, volume and derivatives indicator computations.

Pure functions operating on Binance klines / OI history.  No network here.
"""
from __future__ import annotations

from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Kline helpers
# ---------------------------------------------------------------------------
def closes(kl: list[list]) -> np.ndarray:
    return np.array([float(r[4]) for r in kl], dtype=float)


def highs(kl: list[list]) -> np.ndarray:
    return np.array([float(r[2]) for r in kl], dtype=float)


def lows(kl: list[list]) -> np.ndarray:
    return np.array([float(r[3]) for r in kl], dtype=float)


def quote_volumes(kl: list[list]) -> np.ndarray:
    return np.array([float(r[7]) for r in kl], dtype=float)


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------
def ema(values: np.ndarray, period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return float(e)


def rsi(values: np.ndarray, period: int = 14) -> Optional[float]:
    if len(values) < period + 1:
        return None
    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def ema_stack(c: np.ndarray) -> dict:
    """EMA20/50/200 alignment (多頭排列)."""
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    price = float(c[-1]) if len(c) else None
    bull = bool(e20 and e50 and e200 and e20 > e50 > e200)
    above20 = bool(e20 and price and price > e20)
    return {"ema20": e20, "ema50": e50, "ema200": e200,
            "bull_stack": bull, "above_ema20": above20, "price": price}


def bollinger(c: np.ndarray, period: int = 20, mult: float = 2.0) -> dict:
    if len(c) < period:
        return {"upper": None, "mid": None, "lower": None, "above_upper": False}
    window = c[-period:]
    mid = window.mean()
    sd = window.std()
    upper = mid + mult * sd
    lower = mid - mult * sd
    return {"upper": float(upper), "mid": float(mid), "lower": float(lower),
            "above_upper": bool(c[-1] > upper)}


def breakouts(kl: list[list], lookback: int = 20) -> dict:
    """Detect breakout setups (spec section 10)."""
    h, l, c = highs(kl), lows(kl), closes(kl)
    if len(c) < lookback + 2:
        return {"prior_high": False, "box": False, "downtrend": False,
                "boll_upper": False}
    price = c[-1]
    prior_high = float(h[-(lookback + 1):-1].max())
    prior_low = float(l[-(lookback + 1):-1].min())
    box_range = (prior_high - prior_low) / prior_low if prior_low else 1
    # break of recent swing-high cluster = breaking a falling trendline proxy
    recent_high_5 = float(h[-6:-1].max())
    boll = bollinger(c)
    return {
        "prior_high": bool(price > prior_high),                 # 突破前高
        "box": bool(price > prior_high and box_range < 0.25),   # 突破箱體 (tight range)
        "downtrend": bool(price > recent_high_5 and c[-1] > c[-2] > c[-3]),  # 突破下降趨勢
        "boll_upper": bool(boll["above_upper"]),                # 突破布林上軌
    }


# ---------------------------------------------------------------------------
# Volume anomaly (spec section 3)
# ---------------------------------------------------------------------------
def volume_ratio(kl: list[list], window: int = 20) -> Optional[float]:
    """Current (last completed) day volume / trailing 20-day average."""
    qv = quote_volumes(kl)
    if len(qv) < window + 1:
        return None
    avg = qv[-(window + 1):-1].mean()
    if avg <= 0:
        return None
    return float(qv[-1] / avg)


# ---------------------------------------------------------------------------
# Derivatives: Open Interest (spec section 6)
# ---------------------------------------------------------------------------
def oi_change_pct(oi_hist: list[dict]) -> Optional[float]:
    """% change in OI (USD value) over the supplied history window."""
    if len(oi_hist) < 2:
        return None
    try:
        first = float(oi_hist[0]["sumOpenInterestValue"])
        last = float(oi_hist[-1]["sumOpenInterestValue"])
        if first <= 0:
            return None
        return (last - first) / first * 100
    except Exception:
        return None


def oi_price_signal(oi_chg: Optional[float], price_chg: Optional[float]) -> str:
    """Interpret OI vs price (spec section 6). The 5-star setup is OI↑ & price↑."""
    if oi_chg is None or price_chg is None:
        return "N/A"
    if oi_chg > 5 and price_chg > 0:
        return "★★★★★ 新資金追價 (OI↑ 價↑)"
    if oi_chg > 5 and price_chg < 0:
        return "⚠ 可能大舉做空 (OI↑ 價↓)"
    if oi_chg < -5 and price_chg > 0:
        return "空單回補上漲 (OI↓ 價↑)"
    if oi_chg < -5 and price_chg < 0:
        return "多單離場 (OI↓ 價↓)"
    return "中性"
