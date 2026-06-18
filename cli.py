"""Command-line runner for the Altcoin Alpha Scanner.

Usage:
    python cli.py                 # scan default universe, show ranked table
    python cli.py --top 100       # scan top 100 by volume
    python cli.py --candidates    # only coins passing the section-18 hard filter
    python cli.py --min-score 80  # only score >= 80
    python cli.py --no-enrich     # skip CoinGecko (faster, no market cap)
    python cli.py --json out.json # also dump full results to JSON
"""
from __future__ import annotations

import argparse
import json
import sys

from screener import engine


def _fmt_usd(v):
    if v is None:
        return "-"
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(v) >= div:
            return f"{v/div:.1f}{unit}"
    return f"{v:.0f}"


def _pct(v):
    return "-" if v is None else f"{v:+.1f}%"


def main():
    ap = argparse.ArgumentParser(description="潛力幣種篩選器 / Altcoin Alpha Scanner")
    ap.add_argument("--top", type=int, default=None, help="universe size by 24h volume")
    ap.add_argument("--candidates", action="store_true", help="only section-18 candidates")
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--no-enrich", action="store_true", help="skip CoinGecko metadata")
    ap.add_argument("--limit", type=int, default=30, help="rows to print")
    ap.add_argument("--json", type=str, default=None, help="dump full results to file")
    args = ap.parse_args()

    def progress(msg):
        print(f"\r\033[K{msg}", end="", file=sys.stderr, flush=True)

    data = engine.run(top_n=args.top, enrich=not args.no_enrich, progress=progress)
    print("\r\033[K", end="", file=sys.stderr)

    meta = data["meta"]
    if meta.get("error"):
        print("ERROR:", meta["error"])
        return

    coins = data["coins"]
    if args.candidates:
        coins = [c for c in coins if c["candidate"]]
    coins = [c for c in coins if c["potential_score"] >= args.min_score]

    # --- header
    print(f"\n  潛力幣種篩選器  |  {meta['timestamp']}  |  "
          f"BTC 24h {_pct(meta['btc_chg_24h'])} / 7d {_pct(meta['btc_chg_7d'])}  |  "
          f"掃描 {meta['scanned']} 幣")
    print("=" * 118)

    # --- sector rotation
    print("  板塊輪動 (24H 平均漲幅):  ", end="")
    print("   ".join(f"{s['rank']}.{s['sector']} {_pct(s['avg_chg_24h'])}"
                     for s in data["sectors"][:6]))
    print("=" * 118)

    # --- table
    hdr = (f"  {'#':>2} {'SYMBOL':<12}{'板塊':<8}{'分數':>5} {'訊號':<16}"
           f"{'24h':>8}{'7d':>8}{'VolX':>6}{'OI%':>7}{'Fund%':>7}{'RSI':>5}  突破/旗標")
    print(hdr)
    print("-" * 118)
    brk_names = {"prior_high": "破前高", "box": "破箱體",
                 "downtrend": "破下降", "boll_upper": "破布林"}
    for i, c in enumerate(coins[:args.limit], 1):
        flags = []
        if c["candidate"]:
            flags.append("✅候選")
        if c["ema_bull"]:
            flags.append("EMA多頭")
        flags += [brk_names[b] for b in c["breakouts"]]

        vol_s = f"{c['volume_ratio']}x" if c["volume_ratio"] else "-"
        fund_s = f"{c['funding_pct']:+.3f}" if c["funding_pct"] is not None else "-"
        rsi_s = str(c["rsi"]) if c["rsi"] is not None else "-"
        print(f"  {i:>2} {c['symbol']:<12}{c['sector']:<8}"
              f"{c['potential_score']:>5.0f} {c['signal']:<16}"
              f"{_pct(c['chg_24h']):>8}{_pct(c['chg_7d']):>8}"
              f"{vol_s:>6}{_pct(c['oi_change_pct']):>7}{fund_s:>7}{rsi_s:>5}  "
              f"{' '.join(flags)}")

    print("-" * 118)
    print(f"  顯示 {min(len(coins), args.limit)}/{len(coins)} 幣  |  "
          f"資料覆蓋率 (live data): {coins[0]['coverage'] if coins else 0}% "
          f"(鏈上/情緒/事件需 API key — 見 README)")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  已輸出 JSON -> {args.json}")


if __name__ == "__main__":
    main()
