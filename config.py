"""Global configuration for the Altcoin Alpha Scanner / 潛力幣種篩選器."""

# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
# How many of the most-liquid USDT perpetuals to scan (by 24h quote volume).
TOP_N_SYMBOLS = 60

# Symbols to always exclude (stablecoins, leveraged tokens, etc.)
EXCLUDE = {
    "USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "BUSDUSDT", "DAIUSDT",
    "USDPUSDT", "EURUSDT", "AEURUSDT",
}

# Benchmarks for relative-strength comparison.
BENCHMARK = "BTCUSDT"
BENCHMARK2 = "ETHUSDT"

# ---------------------------------------------------------------------------
# Scoring weights (Potential Score 0-100).  These follow the spec.
# Any category with no data is dropped and the remaining weights renormalize,
# so the score always reflects *real* signals.  data_coverage reports how much
# of the weight was backed by live data.
# ---------------------------------------------------------------------------
WEIGHTS = {
    "technical": 0.30,   # 技術面
    "capital":   0.30,   # 資金流 (volume / OI / funding / liquidations / flows)
    "onchain":   0.20,   # 鏈上數據
    "sentiment": 0.10,   # 情緒 (social)
    "event":     0.10,   # 事件 (catalysts / listings)
}

# ---------------------------------------------------------------------------
# Volume-anomaly bonus thresholds (spec section 3).
#   current 24h volume / 20-day average volume
# ---------------------------------------------------------------------------
VOLUME_RATIO_TIERS = [
    (5.0, 30),
    (3.0, 20),
    (2.0, 10),
    (1.5, 5),
]

# ---------------------------------------------------------------------------
# "My recommended" real-trading filter (spec section 18).
# A coin is a CANDIDATE only if it passes the hard gates below.
# ---------------------------------------------------------------------------
FILTER = {
    "min_volume_ratio": 2.0,     # 成交量 > 2x 均量 (spec says 3x; 2x = looser pre-screen)
    "min_oi_change_pct": 5.0,    # OI 增加 > 5%
    "require_ema_bull": True,    # EMA20 > EMA50 and price > EMA20
    "beat_btc_7d": True,         # 7 日漲幅 > BTC
}

# Score tiers for the watchlist labels (spec section 18).
TIERS = [
    (95, "🔥 極少數超強標的"),
    (90, "⭐ 優先研究"),
    (80, "🟢 重點觀察"),
    (65, "🟡 留意"),
    (0,  "⚪ 一般"),
]

# ---------------------------------------------------------------------------
# Sector map (板塊).  CoinGecko categories are noisy, so we keep a curated map
# for the majors and fall back to "Other".  Extend freely.
# ---------------------------------------------------------------------------
SECTOR_MAP = {
    # 公鏈 / L1
    "BTC": "公鏈", "ETH": "公鏈", "SOL": "公鏈", "SUI": "公鏈", "SEI": "公鏈",
    "APT": "公鏈", "AVAX": "公鏈", "NEAR": "公鏈", "ADA": "公鏈", "DOT": "公鏈",
    "TON": "公鏈", "ATOM": "公鏈", "TRX": "公鏈", "BNB": "公鏈", "ICP": "公鏈",
    "KAS": "公鏈", "HBAR": "公鏈", "ALGO": "公鏈", "INJ": "公鏈", "TIA": "公鏈",
    # Layer2
    "ARB": "Layer2", "OP": "Layer2", "MATIC": "Layer2", "POL": "Layer2",
    "STRK": "Layer2", "MANTA": "Layer2", "ZK": "Layer2", "METIS": "Layer2",
    "IMX": "Layer2",
    # DeFi
    "AAVE": "DeFi", "UNI": "DeFi", "MKR": "DeFi", "LDO": "DeFi", "CRV": "DeFi",
    "COMP": "DeFi", "SNX": "DeFi", "DYDX": "DeFi", "PENDLE": "DeFi",
    "CAKE": "DeFi", "SUSHI": "DeFi", "ENA": "DeFi", "JUP": "DeFi",
    # AI
    "FET": "AI", "RENDER": "AI", "RNDR": "AI", "TAO": "AI", "AGIX": "AI",
    "OCEAN": "AI", "AKT": "AI", "WLD": "AI", "ARKM": "AI", "AI": "AI",
    "GRT": "AI", "NMR": "AI",
    # Meme
    "DOGE": "Meme", "SHIB": "Meme", "PEPE": "Meme", "WIF": "Meme",
    "BONK": "Meme", "FLOKI": "Meme", "BOME": "Meme", "MEME": "Meme",
    "BRETT": "Meme", "POPCAT": "Meme",
    # GameFi
    "AXS": "GameFi", "SAND": "GameFi", "MANA": "GameFi", "GALA": "GameFi",
    "APE": "GameFi", "PIXEL": "GameFi", "BEAM": "GameFi", "ILV": "GameFi",
    "GMT": "GameFi",
    # RWA
    "ONDO": "RWA", "OM": "RWA", "POLYX": "RWA", "PENDLE_RWA": "RWA",
    "TRU": "RWA", "CFG": "RWA",
    # Infra / DePIN / Oracle
    "LINK": "Oracle", "PYTH": "Oracle", "API3": "Oracle",
    "FIL": "DePIN", "AR": "DePIN", "HNT": "DePIN", "IOTX": "DePIN",
    "THETA": "DePIN",
    # Payments / Exchange
    "XRP": "支付", "XLM": "支付", "LTC": "支付", "BCH": "支付",
    "OKB": "交易所", "BGB": "交易所", "CRO": "交易所",
}


def sector_of(base_symbol: str) -> str:
    """Return the sector for a base symbol (e.g. 'SOL'), defaulting to 'Other'."""
    return SECTOR_MAP.get(base_symbol.upper(), "Other")
