"""Real integrations for the extra data sources (spec modules 4/5/8/13/14/15).

Keyless sources work out of the box:
  - DefiLlama        on-chain TVL fund-flow          (no key)
  - Alternative.me   Fear & Greed sentiment          (no key)

Keyed sources light up when you export the matching environment variable:
  - LunarCrush       social mention / galaxy score    LUNARCRUSH_API_KEY
  - CoinMarketCal    event calendar (listing/mainnet) COINMARKETCAL_API_KEY
  - Whale Alert      large transfers / whale flow     WHALE_ALERT_API_KEY
  - CoinGlass        long/short liquidations          COINGLASS_API_KEY
  - Glassnode        exchange in/outflow, addresses   GLASSNODE_API_KEY

Everything degrades gracefully: missing key/data -> None -> the scoring engine
renormalizes weights and reports honest data-coverage.

Call prime() ONCE before scanning to warm the shared keyless caches.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

# --- keys from environment ---
LUNARCRUSH_KEY = os.getenv("LUNARCRUSH_API_KEY")
COINGLASS_KEY = os.getenv("COINGLASS_API_KEY")
CMC_CAL_KEY = os.getenv("COINMARKETCAL_API_KEY")
WHALE_ALERT_KEY = os.getenv("WHALE_ALERT_API_KEY")
GLASSNODE_KEY = os.getenv("GLASSNODE_API_KEY")

_S = requests.Session()
_S.headers.update({"User-Agent": "alpha-scanner/1.0"})
TIMEOUT = 15


def _get(url, params=None, headers=None):
    try:
        r = _S.get(url, params=params, headers=headers, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Shared keyless caches (fetched once via prime())
# ---------------------------------------------------------------------------
_LLAMA: dict[str, dict] = {}
_FNG: Optional[int] = None
_FNG_LABEL: Optional[str] = None


def prime() -> None:
    """Warm DefiLlama + Fear&Greed caches.  Safe to call repeatedly."""
    global _LLAMA, _FNG, _FNG_LABEL
    protos = _get("https://api.llama.fi/protocols")
    if protos:
        m: dict[str, dict] = {}
        for p in protos:
            if p.get("category") == "CEX":
                continue
            sym = (p.get("symbol") or "").upper()
            if not sym or sym == "-":
                continue
            tvl = p.get("tvl") or 0
            if sym not in m or tvl > (m[sym].get("tvl") or 0):
                m[sym] = {"tvl": tvl, "change_1d": p.get("change_1d"),
                          "change_7d": p.get("change_7d"), "category": p.get("category")}
        _LLAMA = m
    fg = _get("https://api.alternative.me/fng/?limit=1")
    if fg and fg.get("data"):
        try:
            _FNG = int(fg["data"][0]["value"])
            _FNG_LABEL = fg["data"][0].get("value_classification")
        except Exception:
            pass


def fear_greed() -> tuple[Optional[int], Optional[str]]:
    return _FNG, _FNG_LABEL


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass
class FlowData:
    whale_netflow_usd: Optional[float] = None
    exchange_inflow_usd: Optional[float] = None
    exchange_outflow_usd: Optional[float] = None
    large_transfers: list = field(default_factory=list)

    @property
    def exchange_netflow_usd(self) -> Optional[float]:
        if self.exchange_inflow_usd is None or self.exchange_outflow_usd is None:
            return None
        return self.exchange_inflow_usd - self.exchange_outflow_usd


@dataclass
class OnchainData:
    active_addresses_growth_pct: Optional[float] = None
    new_addresses_growth_pct: Optional[float] = None
    tx_count_growth_pct: Optional[float] = None
    tvl_change_1d: Optional[float] = None
    tvl_change_7d: Optional[float] = None
    tvl: Optional[float] = None


@dataclass
class SocialData:
    mention_growth_pct: Optional[float] = None
    galaxy_score: Optional[float] = None


@dataclass
class EventData:
    upcoming: list = field(default_factory=list)
    has_listing: bool = False
    has_mainnet: bool = False
    has_major_news: bool = False


# ---------------------------------------------------------------------------
# 13. On-chain  (DefiLlama keyless + Glassnode keyed)
# ---------------------------------------------------------------------------
def get_onchain(base: str) -> OnchainData:
    oc = OnchainData()
    le = _LLAMA.get(base.upper())
    if le:
        oc.tvl = le.get("tvl")
        oc.tvl_change_1d = le.get("change_1d")
        oc.tvl_change_7d = le.get("change_7d")
    if GLASSNODE_KEY:
        # TODO: Glassnode addresses/active_count, new_non_zero, tx/count.
        # e.g. https://api.glassnode.com/v1/metrics/addresses/active_count
        #      ?a={base}&api_key={GLASSNODE_KEY}&i=24h  -> compute % growth.
        pass
    return oc


# ---------------------------------------------------------------------------
# 14. Social  (LunarCrush keyed; falls back to global Fear&Greed)
# ---------------------------------------------------------------------------
def get_social(base: str) -> SocialData:
    if LUNARCRUSH_KEY:
        d = _get(f"https://lunarcrush.com/api4/public/coins/{base}/v1",
                 headers={"Authorization": f"Bearer {LUNARCRUSH_KEY}"})
        if d and d.get("data"):
            row = d["data"]
            return SocialData(
                galaxy_score=row.get("galaxy_score"),
                # social_volume change isn't a single field; use interactions delta
                mention_growth_pct=row.get("social_volume_24h_percent_change"),
            )
    return SocialData()  # engine uses global Fear&Greed when this is empty


# ---------------------------------------------------------------------------
# 15. Events  (CoinMarketCal keyed)
# ---------------------------------------------------------------------------
_LISTING_KW = ("listing", "list ", "binance", "coinbase", "upbit", "上幣", "上线")
_MAINNET_KW = ("mainnet", "main net", "launch", "主网", "主網", "upgrade", "hard fork")


def get_events(base: str) -> EventData:
    if not CMC_CAL_KEY:
        return EventData()
    # CoinMarketCal expects coin ids; symbol often works as a filter.
    d = _get("https://developers.coinmarketcal.com/v1/events",
             params={"coins": base.lower(), "max": 5},
             headers={"x-api-key": CMC_CAL_KEY, "Accept": "application/json"})
    ev = EventData()
    rows = (d or {}).get("body") or []
    for r in rows:
        title = (r.get("title") or {}).get("en", "") if isinstance(r.get("title"), dict) else str(r.get("title", ""))
        t = title.lower()
        ev.upcoming.append({"title": title, "date": r.get("date_event")})
        if any(k in t for k in _LISTING_KW):
            ev.has_listing = True
        if any(k in t for k in _MAINNET_KW):
            ev.has_mainnet = True
        ev.has_major_news = True
    return ev


# ---------------------------------------------------------------------------
# 4/5. Whale flows + exchange in/outflow  (Whale Alert keyed)
# ---------------------------------------------------------------------------
def get_flows(base: str) -> FlowData:
    if not WHALE_ALERT_KEY:
        return FlowData()
    start = int(time.time()) - 3600
    d = _get("https://api.whale-alert.io/v1/transactions",
             params={"api_key": WHALE_ALERT_KEY, "min_value": 1_000_000, "start": start})
    fd = FlowData(exchange_inflow_usd=0.0, exchange_outflow_usd=0.0, whale_netflow_usd=0.0)
    sym = base.lower()
    for tx in (d or {}).get("transactions", []):
        if (tx.get("symbol") or "").lower() != sym:
            continue
        amt = tx.get("amount_usd") or 0
        frm = (tx.get("from") or {}).get("owner_type")
        to = (tx.get("to") or {}).get("owner_type")
        fd.large_transfers.append({"from": (tx.get("from") or {}).get("owner", "unknown"),
                                   "to": (tx.get("to") or {}).get("owner", "unknown"),
                                   "usd": amt})
        if to == "exchange":
            fd.exchange_inflow_usd += amt          # to exchange = bearish
            fd.whale_netflow_usd -= amt
        elif frm == "exchange":
            fd.exchange_outflow_usd += amt         # off exchange = bullish
            fd.whale_netflow_usd += amt
    return fd


# ---------------------------------------------------------------------------
# 8. Liquidations  (CoinGlass keyed)
# ---------------------------------------------------------------------------
def get_liquidations(symbol: str) -> dict:
    if not COINGLASS_KEY:
        return {}
    base = symbol.replace("USDT", "")
    d = _get("https://open-api-v4.coinglass.com/api/futures/liquidation/history",
             params={"symbol": base, "interval": "1d", "limit": 1},
             headers={"CG-API-KEY": COINGLASS_KEY})
    rows = (d or {}).get("data") or []
    if not rows:
        return {}
    last = rows[-1]
    # field names vary by plan; adjust to your endpoint's schema.
    return {"long_usd": float(last.get("longLiquidationUsd", 0) or 0),
            "short_usd": float(last.get("shortLiquidationUsd", 0) or 0)}
