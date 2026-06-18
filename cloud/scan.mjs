// 雲端哨兵:在 GitHub Actions 上定時跑,掃描 Binance 期貨,有「新候選」就發 Telegram。
// 不需要瀏覽器、不需要你的電腦開著。純 Node(內建 fetch),零依賴。
//
// 環境變數(由 GitHub Secrets 提供):
//   TELEGRAM_TOKEN  必填  Telegram Bot Token
//   TELEGRAM_CHAT   必填  你的 chat id
//   TOP_N           選填  掃描成交量前幾名(預設 40)
//   MIN_SCORE       選填  分數達多少也視為標的(預設 80)
import fs from "node:fs";

const FAPI = "https://fapi.binance.com";
const TOP_N = +(process.env.TOP_N || 40);
const MIN_SCORE = +(process.env.MIN_SCORE || 80);
const TG_TOKEN = process.env.TELEGRAM_TOKEN;
const TG_CHAT = process.env.TELEGRAM_CHAT;
const STATE = "state.json";
const EXCLUDE = new Set(["USDCUSDT","FDUSDUSDT","TUSDUSDT","BUSDUSDT","DAIUSDT","USDPUSDT","EURUSDT","AEURUSDT"]);
const VOL_TIERS = [[5,30],[3,20],[2,10],[1.5,5]];

async function jget(url){try{const r=await fetch(url);if(!r.ok)return null;return await r.json();}catch{return null;}}

// ---- indicators (與 scanner.html 一致) ----
function ema(v,p){if(v.length<p)return null;const k=2/(p+1);let e=v[0];for(let i=1;i<v.length;i++)e=v[i]*k+e*(1-k);return e;}
function rsi(v,p=14){if(v.length<p+1)return null;let g=0,l=0;for(let i=1;i<=p;i++){const d=v[i]-v[i-1];if(d>0)g+=d;else l-=d;}g/=p;l/=p;for(let i=p+1;i<v.length;i++){const d=v[i]-v[i-1];g=(g*(p-1)+(d>0?d:0))/p;l=(l*(p-1)+(d<0?-d:0))/p;}if(l===0)return 100;return 100-100/(1+g/l);}
const clamp=x=>Math.max(0,Math.min(100,x));
function volRatio(qv,w=20){if(qv.length<w+1)return null;let s=0;for(let i=qv.length-1-w;i<qv.length-1;i++)s+=qv[i];const a=s/w;return a>0?qv[qv.length-1]/a:null;}
function bollUpper(c,p=20,m=2){if(c.length<p)return null;const w=c.slice(-p);const mid=w.reduce((a,b)=>a+b,0)/p;const sd=Math.sqrt(w.reduce((a,b)=>a+(b-mid)**2,0)/p);return mid+m*sd;}
function breakouts(h,l,c,lb=20){if(c.length<lb+2)return [];const price=c[c.length-1];const ph=Math.max(...h.slice(-lb-1,-1));const pl=Math.min(...l.slice(-lb-1,-1));const box=(ph-pl)/pl;const rh5=Math.max(...h.slice(-6,-1));const bu=bollUpper(c);const out=[];if(price>ph)out.push("prior_high");if(price>ph&&box<0.25)out.push("box");if(price>rh5&&c[c.length-1]>c[c.length-2]&&c[c.length-2]>c[c.length-3])out.push("downtrend");if(bu&&price>bu)out.push("boll_upper");return out;}
function oiChange(hist){if(!hist||hist.length<2)return null;const a=+hist[0].sumOpenInterestValue,b=+hist[hist.length-1].sumOpenInterestValue;return a>0?(b-a)/a*100:null;}

// ---- scoring ----
function volBonus(vr){if(vr==null)return 0;for(const[t,p]of VOL_TIERS)if(vr>=t)return p;return 0;}
function scoreTechnical(t,beatsBtc,brk,rsiV){let s=50;if(t.bull)s+=18;else if(t.e20&&t.e50&&t.e20>t.e50)s+=8;if(t.above20)s+=8;s+=6*brk.length;if(rsiV!=null){if(rsiV>=55&&rsiV<=72)s+=8;else if(rsiV>80)s-=10;else if(rsiV<40)s-=6;}if(beatsBtc)s+=6;return clamp(s);}
function scoreCapital(vr,oi,fund,pc,taker){let s=50;if(vr!=null)s+=volBonus(vr);if(oi!=null){if(oi>20)s+=18;else if(oi>10)s+=12;else if(oi>5)s+=6;else if(oi<-10)s-=8;if(oi>10&&pc!=null&&pc>0)s+=6;}if(fund!=null){const f=fund*100;if(f>0.1)s-=6;else if(f>0&&f<=0.05)s+=4;else if(f<-0.05)s+=8;}if(taker!=null){if(taker>1.15)s+=6;else if(taker<0.85)s-=4;}return clamp(s);}

async function pool(items,limit,fn){const out=[];let i=0;async function w(){while(i<items.length){const idx=i++;try{out[idx]=await fn(items[idx]);}catch{out[idx]=null;}}}await Promise.all(Array.from({length:Math.min(limit,items.length)},w));return out;}

async function analyze(sym,tk,btc7){
  const kl=await jget(`${FAPI}/fapi/v1/klines?symbol=${sym}&interval=1d&limit=220`);
  if(!kl||kl.length<60)return null;
  const c=kl.map(r=>+r[4]),h=kl.map(r=>+r[2]),l=kl.map(r=>+r[3]),qv=kl.map(r=>+r[7]);
  const pc=+tk.priceChangePercent;
  const e20=ema(c,20),e50=ema(c,50),e200=ema(c,200),price=c[c.length-1];
  const t={e20,e50,e200,price,bull:!!(e20&&e50&&e200&&e20>e50&&e50>e200),above20:!!(e20&&price>e20)};
  const rsiV=rsi(c),brk=breakouts(h,l,c);
  const chg7=c.length>=8?((price/c[c.length-8])-1)*100:null;
  const beatsBtc=chg7!=null&&chg7>btc7;
  const vr=volRatio(qv);
  const [oiHist,prem,taker]=await Promise.all([
    jget(`${FAPI}/futures/data/openInterestHist?symbol=${sym}&period=1d&limit=8`),
    jget(`${FAPI}/fapi/v1/premiumIndex?symbol=${sym}`),
    jget(`${FAPI}/futures/data/takerlongshortRatio?symbol=${sym}&period=1h&limit=1`)]);
  const oi=oiChange(oiHist),fund=prem?+prem.lastFundingRate:null,takerR=taker&&taker.length?+taker[taker.length-1].buySellRatio:null;
  const techS=scoreTechnical(t,beatsBtc,brk,rsiV);
  const capS=scoreCapital(vr,oi,fund,pc,takerR);
  const score=Math.round((techS+capS)/2*10)/10;
  const cand=vr!=null&&vr>=2&&oi!=null&&oi>=5&&!!e20&&!!e50&&e20>e50&&t.above20&&beatsBtc;
  return {symbol:sym,base:sym.replace(/USDT$/,""),score,candidate:cand,chg7,vr,oi};
}

async function sendTelegram(text){
  if(!TG_TOKEN||!TG_CHAT){console.log("(未設定 Telegram secrets,略過發送)");return;}
  const r=await fetch(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({chat_id:TG_CHAT,text})});
  console.log("Telegram 發送:",r.status);
}

async function main(){
  const [info,tickers]=await Promise.all([jget(`${FAPI}/fapi/v1/exchangeInfo`),jget(`${FAPI}/fapi/v1/ticker/24hr`)]);
  if(!tickers){console.log("無法連線 Binance");return;}
  const perp=new Set((info?.symbols||[]).filter(s=>s.contractType==="PERPETUAL"&&s.quoteAsset==="USDT"&&s.status==="TRADING").map(s=>s.symbol));
  const tk={};tickers.forEach(t=>{if(t.symbol.endsWith("USDT"))tk[t.symbol]=t;});
  let uni=Object.keys(tk).filter(s=>(!perp.size||perp.has(s))&&!EXCLUDE.has(s));
  uni.sort((a,b)=>+tk[b].quoteVolume-+tk[a].quoteVolume);
  uni=uni.slice(0,TOP_N);

  const btcKl=await jget(`${FAPI}/fapi/v1/klines?symbol=BTCUSDT&interval=1d&limit=10`);
  const bc=btcKl?btcKl.map(r=>+r[4]):[];
  const btc7=bc.length>=8?((bc[bc.length-1]/bc[bc.length-8])-1)*100:0;

  const res=(await pool(uni,5,s=>analyze(s,tk[s],btc7))).filter(Boolean);
  const alert=res.filter(c=>c.candidate||c.score>=MIN_SCORE).sort((a,b)=>b.score-a.score);
  const cur=alert.map(c=>c.symbol);
  console.log(`掃描 ${res.length} 幣,符合 ${alert.length} 個:`,cur.join(", ")||"(無)");

  // 讀上次狀態(由 actions/cache 還原);首次執行只建立基準、不發通知
  const firstRun=!fs.existsSync(STATE);
  let prev=[];
  if(!firstRun){try{prev=JSON.parse(fs.readFileSync(STATE,"utf8")).symbols||[];}catch{}}
  const fresh=alert.filter(c=>!prev.includes(c.symbol));

  if(firstRun){
    console.log("首次執行,建立基準,不發通知。");
  }else if(fresh.length){
    const f=(v,d=0)=>v==null?"-":(v>=0?"+":"")+v.toFixed(d);
    const lines=fresh.map(c=>`• ${c.base}  分數 ${c.score}${c.candidate?" ✅候選":""}\n   7d ${f(c.chg7)}%  量 ${c.vr?c.vr.toFixed(1)+"x":"-"}  OI ${f(c.oi)}%`);
    await sendTelegram(`🚨 Alpha Scanner 新標的 (${fresh.length})\n\n`+lines.join("\n\n")+`\n\nBTC 7d ${f(btc7,1)}%`);
  }else{
    console.log("無新標的,不發通知。");
  }

  fs.writeFileSync(STATE,JSON.stringify({symbols:cur,ts:Date.now()}));
}
main().catch(e=>{console.error(e);process.exit(0);});
