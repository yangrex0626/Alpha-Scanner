"""Screener orchestration: fetch -> compute -> score -> rank.

Produces a list of coin dicts ready for CLI tables or the web dashboard,
plus a sector-rotation summary.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from screener import binance, coingecko, indicators as ind, external
from screener import scoring


def _base(symbol: str) -> str:
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def _benchmark_change(tickers: dict, symbol: str) -> float:
    t = tickers.get(symbol)
    try:
        return float(t["priceChangePercent"]) if t else 0.0
    except Exception:
        return 0.0


def _analyze_symbol(symbol: str, ticker: dict, btc_chg: float, eth_chg: float,
                    btc_7d: float, cg: dict, global_fng=None) -> dict | None:
    base = _base(symbol)
    kl = binance.klines(symbol, "1d", 250)
    if len(kl) < 60:
        return None

    c = ind.closes(kl)
    price_chg_24h = float(ticker.get("priceChangePercent", 0) or 0)

    # --- technical
    tech = ind.ema_stack(c)
    rsi_val = ind.rsi(c)
    brk = ind.breakouts(kl)
    boll = ind.bollinger(c)

    # --- relative strength (7d) vs BTC/ETH
    chg_7d = ((c[-1] / c[-8]) - 1) * 100 if len(c) >= 8 else None
    strength = {
        "chg_7d": chg_7d,
        "beats_btc": chg_7d is not None and chg_7d > btc_7d,
        "beats_eth": chg_7d is not None and eth_chg is not None and chg_7d > eth_chg,
        "rs_vs_btc": (chg_7d - btc_7d) if chg_7d is not None else None,
    }

    # --- volume anomaly
    vr = ind.volume_ratio(kl)

    # --- derivatives
    oi_hist = binance.open_interest_hist(symbol, "1d", 8)
    oi_chg = ind.oi_change_pct(oi_hist)
    oi_now = binance.open_interest_now(symbol)
    funding = binance.funding_rate(symbol)
    taker = binance.taker_buysell_ratio(symbol)
    ls_ratio = binance.long_short_ratio(symbol)
    oi_signal = ind.oi_price_signal(oi_chg, price_chg_24h)

    # --- paid plug-ins (graceful None)
    flows = external.get_flows(base)
    onchain = external.get_onchain(base)
    social = external.get_social(base)
    events = external.get_events(base)
    liq = external.get_liquidations(symbol)

    # --- scores
    tech_score = scoring.score_technical(tech, strength, brk, rsi_val)
    cap_score = scoring.score_capital(vr, oi_chg, funding, price_chg_24h,
                                      flows, liq, taker)
    oc_score = scoring.score_onchain(onchain)
    sent_score = scoring.score_sentiment(social, global_fng)
    ev_score = scoring.score_event(events)

    result = scoring.potential_score({
        "technical": tech_score,
        "capital": cap_score,
        "onchain": oc_score,
        "sentiment": sent_score,
        "event": ev_score,
    })
    score = result["score"]

    # --- metadata
    meta = cg.get(base, {})
    quote_vol = float(ticker.get("quoteVolume", 0) or 0)

    return {
        "symbol": symbol,
        "base": base,
        "name": meta.get("name") or base,
        "sector": config.sector_of(base),
        "price": tech.get("price"),
        "chg_24h": round(price_chg_24h, 2),
        "chg_7d": round(chg_7d, 2) if chg_7d is not None else None,
        "rs_vs_btc": round(strength["rs_vs_btc"], 2) if strength["rs_vs_btc"] is not None else None,
        "beats_btc": strength["beats_btc"],
        "quote_vol_24h": quote_vol,
        "volume_ratio": round(vr, 2) if vr is not None else None,
        "market_cap": meta.get("market_cap"),
        "fdv": meta.get("fdv"),
        "mc_rank": meta.get("mc_rank"),
        # technical
        "ema20": tech.get("ema20"), "ema50": tech.get("ema50"), "ema200": tech.get("ema200"),
        "ema_bull": tech.get("bull_stack"), "above_ema20": tech.get("above_ema20"),
        "rsi": round(rsi_val, 1) if rsi_val is not None else None,
        "breakouts": [k for k in ("prior_high", "box", "downtrend", "boll_upper") if brk.get(k)],
        "boll_upper": boll.get("upper"),
        # derivatives
        "oi_usd": None if not oi_hist else _safe(oi_hist[-1].get("sumOpenInterestValue")),
        "oi_change_pct": round(oi_chg, 1) if oi_chg is not None else None,
        "oi_signal": oi_signal,
        "funding_pct": round(funding * 100, 4) if funding is not None else None,
        "taker_ratio": round(taker, 2) if taker is not None else None,
        "ls_ratio": round(ls_ratio, 2) if ls_ratio is not None else None,
        "liquidations": liq,
        # on-chain (DefiLlama) + flows (Whale Alert)
        "tvl": onchain.tvl,
        "tvl_change_7d": onchain.tvl_change_7d,
        "whale_netflow_usd": flows.whale_netflow_usd,
        "exchange_netflow_usd": flows.exchange_netflow_usd,
        # sub-scores
        "score_technical": round(tech_score),
        "score_capital": round(cap_score[0]),
        "score_onchain": round(oc_score[0]),
        "score_sentiment": round(sent_score[0]),
        "score_event": round(ev_score[0]),
        # final
        "potential_score": score,
        "coverage": result["coverage"],
        "signal": scoring.signal_label(score),
        "candidate": _passes_filter(vr, oi_chg, tech, strength),
    }


def _safe(v):
    try:
        return float(v)
    except Exception:
        return None


def _passes_filter(vr, oi_chg, tech, strength) -> bool:
    """Hard gates from spec section 18 (the real-trading filter)."""
    f = config.FILTER
    if vr is None or vr < f["min_volume_ratio"]:
        return False
    if oi_chg is None or oi_chg < f["min_oi_change_pct"]:
        return False
    if f["require_ema_bull"]:
        e20, e50 = tech.get("ema20"), tech.get("ema50")
        if not (e20 and e50 and e20 > e50 and tech.get("above_ema20")):
            return False
    if f["beat_btc_7d"] and not strength.get("beats_btc"):
        return False
    return True


def sector_rotation(coins: list[dict]) -> list[dict]:
    """24h capital-flow proxy by sector (spec section 12)."""
    buckets: dict[str, dict] = {}
    for c in coins:
        b = buckets.setdefault(c["sector"], {"sector": c["sector"], "chgs": [],
                                             "vol": 0.0, "count": 0})
        if c["chg_24h"] is not None:
            b["chgs"].append(c["chg_24h"])
        b["vol"] += c["quote_vol_24h"] or 0
        b["count"] += 1
    out = []
    for b in buckets.values():
        avg = sum(b["chgs"]) / len(b["chgs"]) if b["chgs"] else 0.0
        out.append({"sector": b["sector"], "avg_chg_24h": round(avg, 2),
                    "volume": b["vol"], "count": b["count"]})
    out.sort(key=lambda x: x["avg_chg_24h"], reverse=True)
    for i, s in enumerate(out, 1):
        s["rank"] = i
    return out


def run(top_n: int | None = None, enrich: bool = True,
        progress=lambda *_: None) -> dict:
    """Run the full scan.  Returns {'coins': [...], 'sectors': [...], 'meta': {...}}."""
    top_n = top_n or config.TOP_N_SYMBOLS
    progress("Fetching universe...")
    perps = binance.perp_symbols()
    tickers = binance.futures_24h()
    if not tickers:
        return {"coins": [], "sectors": [], "meta": {"error": "Binance unreachable"}}

    # rank universe by 24h quote volume
    universe = [s for s in tickers
                if s in perps and s.endswith("USDT") and s not in config.EXCLUDE]
    universe.sort(key=lambda s: float(tickers[s].get("quoteVolume", 0) or 0), reverse=True)
    universe = universe[:top_n]

    progress("Priming on-chain (DefiLlama) + sentiment (Fear&Greed)...")
    external.prime()
    fng, fng_label = external.fear_greed()

    btc_chg = _benchmark_change(tickers, config.BENCHMARK)
    eth_chg = _benchmark_change(tickers, config.BENCHMARK2)
    # BTC 7d for relative strength
    btc_kl = binance.klines(config.BENCHMARK, "1d", 10)
    btc_c = ind.closes(btc_kl)
    btc_7d = ((btc_c[-1] / btc_c[-8]) - 1) * 100 if len(btc_c) >= 8 else 0.0

    progress("Fetching CoinGecko metadata...")
    cg = coingecko.markets(pages=2) if enrich else {}

    progress(f"Analyzing {len(universe)} symbols...")
    coins: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_analyze_symbol, s, tickers[s], btc_chg, eth_chg,
                          btc_7d, cg, fng): s for s in universe}
        done = 0
        for fut in as_completed(futs):
            done += 1
            progress(f"Analyzing... {done}/{len(universe)}")
            try:
                r = fut.result()
                if r:
                    coins.append(r)
            except Exception:
                pass

    coins.sort(key=lambda c: c["potential_score"], reverse=True)
    sectors = sector_rotation(coins)
    # tag sector rank onto coins
    rank_map = {s["sector"]: s["rank"] for s in sectors}
    for c in coins:
        c["sector_rank"] = rank_map.get(c["sector"])

    return {
        "coins": coins,
        "sectors": sectors,
        "meta": {
            "scanned": len(coins),
            "btc_chg_24h": round(btc_chg, 2),
            "eth_chg_24h": round(eth_chg, 2),
            "btc_chg_7d": round(btc_7d, 2),
            "fng": fng,
            "fng_label": fng_label,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    }
