# 雲端哨兵(GitHub Actions)— 關機也能收 Telegram 通知

讓 GitHub 每 30 分鐘自動掃描 Binance,有**新候選**就推播到你的 Telegram。
**不用開瀏覽器、不用電腦開著、完全免費。**

```
GitHub Actions (每30分) ──► cloud/scan.mjs 掃描 Binance ──► 有新標的 ──► Telegram 你的手機
```

---

## 一次性設定(約 10 分鐘)

### 1. 準備 Telegram(拿 Token 與 Chat ID)
1. Telegram 搜尋 **@BotFather** → `/newbot` → 取得 **Bot Token**(像 `123456:ABC...`)。
2. 對你剛建的 bot 隨便傳一句話。
3. 瀏覽器打開(把 `<TOKEN>` 換成你的):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   找到 `"chat":{"id":123456789...}` 那個數字 = 你的 **Chat ID**。

### 2. 把這個專案放上 GitHub
- 到 https://github.com → New repository(**Private 私人即可**)。
- 把整個 `coin` 資料夾上傳/推送上去(至少要有 `cloud/scan.mjs` 和 `.github/workflows/alpha-scanner.yml`)。
  - 不熟 git 的話:repo 頁面 **Add file → Upload files**,把 `cloud` 和 `.github` 兩個資料夾拖上去。

### 3. 設定 Secrets(放金鑰)
Repo → **Settings → Secrets and variables → Actions → New repository secret**,新增兩個:

| Name | Value |
|------|-------|
| `TELEGRAM_TOKEN` | 你的 Bot Token |
| `TELEGRAM_CHAT` | 你的 Chat ID |

### 4. 啟用 Actions
- Repo → **Actions** 分頁 → 若提示啟用就按 **Enable**。
- 左側點 **Alpha Scanner Sentinel** → 右邊 **Run workflow**(手動跑一次測試)。
- 第一次執行只會「建立基準、不發通知」(避免一次塞爆),**之後出現新標的才會推播**。

完成!之後它會自己每 30 分鐘跑一次。

---

## 調整

- **掃描頻率**:改 `.github/workflows/alpha-scanner.yml` 裡的 cron。
  例:每 15 分鐘 `*/15 * * * *`、每小時 `0 * * * *`。
  (GitHub 免費排程常延遲幾分鐘,且過於頻繁可能被降頻,建議 ≥15 分鐘。)
- **門檻**:改 workflow 裡 `TOP_N`(掃描數量)、`MIN_SCORE`(分數門檻)。
- **通知條件**:`cloud/scan.mjs` 裡 `alert = candidate || score>=MIN_SCORE`,可自行調整。

## 注意
- 這支雲端版只用 **Binance 免費資料**(技術 + 量能 + OI + Funding),算出分數與 ✅候選 —— 跟網頁版的核心邏輯一致。
- 不含 AI 機率 / CoinGecko / F&G(那些留在網頁版用)。
- 「新標的」判斷靠 `state.json`(由 Actions 快取保存),所以同一個幣不會每 30 分鐘重複吵你,直到它掉出清單再重新進榜才會再通知。
- 免費額度:GitHub Actions 私人 repo 每月 2000 分鐘,這支每次跑約 1 分鐘,每 30 分鐘一次 → 每月約 1440 分鐘,**在免費額度內**(若不夠就把頻率調低)。

⚠️ 僅供研究,非投資建議。
