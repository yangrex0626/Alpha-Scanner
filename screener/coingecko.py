"""CoinGecko free-tier metadata: market cap, FDV, exchange count, contract.

The free API is rate-limited (~10-30 req/min), so we fetch the markets list
in ONE bulk call and map by symbol.  Per-coin detail calls are optional and
used lazily (with a small delay) only when enrich=True.
"""
from __future__ import annotations

import time
from typing import Optional

import requests

BASE = "https://api.coingecko.com/api/v3"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "alpha-scanner/1.0"})
TIMEOUT = 15


def _get(path: str, params: dict | None = None):
    try:
        r = _SESSION.get(BASE + path, params=params, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def markets(pages: int = 2, per_page: int = 250) -> dict[str, dict]:
    """Bulk market data keyed by UPPERCASE base symbol.

    Returns {symbol: {market_cap, fdv, name, id, price, ...}}.
    When two coins share a ticker the larger market cap wins.
    """
    out: dict[str, dict] = {}
    for page in range(1, pages + 1):
        data = _get("/coins/markets", {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": page,
            "sparkline": "false",
        })
        if not data:
            break
        for c in data:
            sym = (c.get("symbol") or "").upper()
            mc = c.get("market_cap") or 0
            if sym not in out or mc > (out[sym].get("market_cap") or 0):
                out[sym] = {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "market_cap": c.get("market_cap"),
                    "fdv": c.get("fully_diluted_valuation"),
                    "circulating_supply": c.get("circulating_supply"),
                    "total_supply": c.get("total_supply"),
                    "price": c.get("current_price"),
                    "mc_rank": c.get("market_cap_rank"),
                }
        time.sleep(1.5)  # be polite to the free tier
    return out


def coin_detail(coin_id: str) -> Optional[dict]:
    """Per-coin detail: number of listing exchanges + a contract address."""
    data = _get(f"/coins/{coin_id}", {
        "localization": "false", "tickers": "true", "market_data": "false",
        "community_data": "false", "developer_data": "false",
    })
    if not data:
        return None
    tickers = data.get("tickers") or []
    exchanges = {t.get("market", {}).get("name") for t in tickers if t.get("market")}
    platforms = data.get("platforms") or {}
    contract = next((v for v in platforms.values() if v), None)
    return {
        "exchange_count": len([e for e in exchanges if e]),
        "contract": contract,
        "categories": data.get("categories") or [],
    }
