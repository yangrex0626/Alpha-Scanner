# 潛力幣種篩選器 · Altcoin Alpha Scanner

一個接近專業加密基金「Alpha Scanner」的短線爆發力篩選器。整合技術面、資金流、
未平倉量、資金費率、相對強弱、板塊輪動，給每個幣一個 **Potential Score (0~100)**
並標示實戰候選。

> 偵測「主力進場第一特徵：成交量先放大、價格後噴」，比單看 RSI / MACD / 漲幅榜實用。

---

## 🚀 兩種版本

### A. 純前端版（零安裝，立即可用）—— `scanner.html`
直接用瀏覽器打開 `scanner.html`（雙擊即可）。它在瀏覽器裡直接呼叫 Binance 期貨
公開 API 計算所有分數，**不需要安裝任何東西、不需 API key**。

- 涵蓋：基礎資料、Potential Score、成交量異常、OI、Funding、Taker 買賣比、
  EMA 排列、突破掃描、相對強弱、板塊輪動、交易訊號中心、第18條實戰篩選。
- **免費鏈上**：DefiLlama TVL 資金流（DeFi 協議幣，免金鑰）。
- **免費情緒**：Alternative.me 全市場 Fear & Greed 指數（免金鑰）。
- 覆蓋率因此約 **90%**。
- **想點亮大戶流向 / 交易所流入流出 / 社群提及 / 爆倉?** 不用裝任何東西 —
  用 Supabase Edge Function 當安全代理(金鑰存伺服器、解決 CORS),把網址貼進
  `scanner.html` 最上面的 `PROXY_URL` 即可,覆蓋率接近 100%。
  詳見 [SUPABASE_SETUP.md](SUPABASE_SETUP.md)。

### B. Python 完整版（可接付費資料源）
有後端、可快取、可插入 Nansen / Glassnode / LunarCrush / Coinglass 等 API key
點亮鏈上、情緒、事件、大戶流向、交易所流入流出、爆倉模組。

```bash
pip install -r requirements.txt

# 命令列
python cli.py                 # 掃描 + 排名表
python cli.py --top 100       # 掃描成交量前 100
python cli.py --candidates    # 只看通過第18條硬篩選的候選
python cli.py --min-score 80  # 只看 ≥80
python cli.py --json out.json # 另存完整結果

# 網頁儀表板
python app.py                 # 開 http://127.0.0.1:5000
```

> ⚠️ 本機目前未安裝 Python（只有 Microsoft Store stub）。安裝方式：
> `winget install Python.Python.3.12`，或到 https://python.org 下載。
> 在那之前請先用 **A. 純前端版**。

---

## 📊 評分系統（Potential Score 0~100）

| 類別 | 權重 | 內容 |
|------|------|------|
| 技術面 | 30% | EMA20/50/200 多頭排列、站上 EMA20、突破（前高/箱體/下降趨勢/布林上軌）、RSI、相對強弱 |
| 資金流 | 30% | 成交量異常、OI 變化、Funding、Taker 買賣比、大戶淨流入*、交易所流入流出*、爆倉* |
| 鏈上 | 20% | 活躍/新增地址、交易筆數成長* |
| 情緒 | 10% | 社群提及成長率*、Galaxy Score* |
| 事件 | 10% | 上幣、ETF、合作、空投、主網* |

`*` = 需付費 API（見下）。缺資料的類別會自動剔除並重新分配權重，分數永遠反映
**真實訊號**，覆蓋率另外顯示。

### 成交量異常加分（最重要功能之一）
`Volume Ratio = 今日成交量 ÷ 過去20日均量`： ≥2x +10、≥3x +20、≥5x +30。

### OI × 價格訊號
- OI↑ + 價↑ = ★★★★★ 新資金追價（最強）
- OI↑ + 價↓ = ⚠ 可能大舉做空
- OI↓ + 價↑ = 空單回補

### 第18條：實戰候選硬篩選（✅候選）
同時滿足：成交量 ≥2x 均量、OI 增加 ≥5%、EMA20>EMA50 且站上 EMA20、7日漲幅 > BTC。

### 分數分級
🔥 ≥95 極少數超強標的 ／ ⭐ ≥90 優先研究 ／ 🟢 ≥80 重點觀察 ／ 🟡 ≥65 留意。

---

## 🔌 接上付費資料源（Python 版）

`screener/external.py` 已寫好真正的串接。免金鑰來源（DefiLlama 鏈上 TVL、
Alternative.me Fear & Greed）開箱即用；其餘設定環境變數即點亮：

| 環境變數 | 點亮模組 | 供應商 | 狀態 |
|----------|----------|--------|------|
| —（免金鑰） | 鏈上 TVL 資金流 | DefiLlama | ✅ 已串接 |
| —（免金鑰） | 全市場情緒 | Alternative.me F&G | ✅ 已串接 |
| `LUNARCRUSH_API_KEY` | 社群提及 / Galaxy Score | LunarCrush | ✅ 已串接 |
| `WHALE_ALERT_API_KEY` | 大戶流向 / 交易所流入流出 | Whale Alert | ✅ 已串接 |
| `COINGLASS_API_KEY` | 多空爆倉 | CoinGlass | ✅ 已串接* |
| `COINMARKETCAL_API_KEY` | 上幣 / 主網 / 事件曆 | CoinMarketCal | ✅ 已串接 |
| `GLASSNODE_API_KEY` | 鏈上地址/交易、交易所流 | Glassnode | ⚙ 留 TODO |

`*` CoinGlass 各方案的 endpoint/欄位略有不同，請依你的方案微調 `get_liquidations`。

```powershell
$env:LUNARCRUSH_API_KEY="..."; $env:WHALE_ALERT_API_KEY="..."; python cli.py
```

---

## 📁 結構
```
coin/
├─ scanner.html          # ★ 純前端零安裝版（雙擊打開，可選接 Supabase 代理）
├─ SUPABASE_SETUP.md     # 用 Edge Function 點亮 社群/大戶/爆倉（免本機安裝）
├─ supabase/functions/crypto-proxy/index.ts   # 安全 API 代理
├─ app.py                # Flask 網頁儀表板
├─ cli.py                # 命令列
├─ config.py             # 權重、門檻、板塊對照表
├─ requirements.txt
├─ templates/index.html  # 儀表板前端
└─ screener/
   ├─ binance.py         # Binance 現貨/期貨公開 API
   ├─ coingecko.py       # 市值 / FDV / 上市交易所數 / 合約
   ├─ indicators.py      # EMA / RSI / 量比 / 突破 / 布林 / OI
   ├─ scoring.py         # Potential Score + 訊號分級
   ├─ external.py        # 付費資料插槽（鏈上/情緒/事件/流向/爆倉）
   └─ engine.py          # 主流程：抓取→計算→評分→排名
```

---

## ⚠️ 免責聲明
本工具僅供研究與教育用途，**不構成投資建議**。加密市場風險極高，請自行做足
功課並控管風險。
