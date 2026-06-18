"""Binance public market data (no API key required).

Spot REST base:    https://api.binance.com
Futures REST base: https://fapi.binance.com   (USDT-M perpetuals)

All functions degrade gracefully: on any network/endpoint error they return
None or an empty structure so the screener keeps running.
"""
from __future__ import annotations

import time
from typing import Optional

import requests

SPOT = "https://api.binance.com"
FAPI = "https://fapi.binance.com"

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "alpha-scanner/1.0"})
TIMEOUT = 12


def _get(base: str, path: str, params: dict | None = None):
    try:
        r = _SESSION.get(base + path, params=params, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
def perp_symbols() -> set[str]:
    """Set of actively-trading USDT-margined perpetual symbols."""
    data = _get(FAPI, "/fapi/v1/exchangeInfo")
    out: set[str] = set()
    if not data:
        return out
    for s in data.get("symbols", []):
        if (
            s.get("contractType") == "PERPETUAL"
            and s.get("quoteAsset") == "USDT"
            and s.get("status") == "TRADING"
        ):
            out.add(s["symbol"])
    return out


def futures_24h() -> dict[str, dict]:
    """24h ticker for every USDT perp, keyed by symbol."""
    data = _get(FAPI, "/fapi/v1/ticker/24hr")
    if not data:
        return {}
    return {d["symbol"]: d for d in data if d["symbol"].endswith("USDT")}


# ---------------------------------------------------------------------------
# Per-symbol data
# ---------------------------------------------------------------------------
def klines(symbol: str, interval: str = "1d", limit: int = 250) -> list[list]:
    """Raw klines from the futures market. Each row:
    [openTime, open, high, low, close, volume, closeTime, quoteVol, ...]
    """
    data = _get(FAPI, "/fapi/v1/klines",
                {"symbol": symbol, "interval": interval, "limit": limit})
    return data or []


def open_interest_now(symbol: str) -> Optional[float]:
    data = _get(FAPI, "/fapi/v1/openInterest", {"symbol": symbol})
    if not data:
        return None
    try:
        return float(data["openInterest"])
    except Exception:
        return None


def open_interest_hist(symbol: str, period: str = "1d", limit: int = 8) -> list[dict]:
    """Historical OI (value in contracts and USD). period: 5m,15m,1h,4h,1d..."""
    data = _get(FAPI, "/futures/data/openInterestHist",
                {"symbol": symbol, "period": period, "limit": limit})
    return data or []


def funding_rate(symbol: str) -> Optional[float]:
    """Latest funding rate (as a decimal, e.g. 0.0001 = 0.01%)."""
    data = _get(FAPI, "/fapi/v1/premiumIndex", {"symbol": symbol})
    if not data:
        return None
    try:
        return float(data["lastFundingRate"])
    except Exception:
        return None


def long_short_ratio(symbol: str, period: str = "1h", limit: int = 2) -> Optional[float]:
    """Top-trader account long/short ratio (>1 = crowd net long)."""
    data = _get(FAPI, "/futures/data/topLongShortAccountRatio",
                {"symbol": symbol, "period": period, "limit": limit})
    if not data:
        return None
    try:
        return float(data[-1]["longShortRatio"])
    except Exception:
        return None


def taker_buysell_ratio(symbol: str, period: str = "1h", limit: int = 1) -> Optional[float]:
    """Taker buy/sell volume ratio (>1 = aggressive buying)."""
    data = _get(FAPI, "/futures/data/takerlongshortRatio",
                {"symbol": symbol, "period": period, "limit": limit})
    if not data:
        return None
    try:
        return float(data[-1]["buySellRatio"])
    except Exception:
        return None
