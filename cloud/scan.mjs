// 雲端哨兵:GitHub Actions 定時跑,掃描 OKX 永續合約,有「新標的」就發 Telegram。
// 為什麼用 OKX 不用 Binance:GitHub 伺服器在美國,Binance 封鎖美國 IP(會「無法連線」);
// OKX 公開行情 API 不封美國 IP,且一樣有永續的價/量/OI/Funding。
// 不需要瀏覽器、不需要你的電腦開著。純 Node(內建 fetch),零依賴。
//
// 環境變數(GitHub Secrets):
//   TELEGRAM_TOKEN 必填 / TELEGRAM_CHAT 必填 / TOP_N(預設100) / MIN_SCORE(預設80)
import fs from "node:fs";

const OKX = "https://www.okx.com";
const TOP_N = +(process.env.TOP_N || 100);
const MIN_SCORE = +(process.env.MIN_SCORE || 80);
const TG_TOKEN = process.env.TELEGRAM_TOKEN;
const TG_CHAT = process.env.TELEGRAM_CHAT;
const STATE = "state.json";
const STABLE = new Set(["USDC","USDT","DAI","TUSD","FDUSD","USDP","EUR","BUSD","USDE"]);
const VOL_TIERS = [[5,30],[3,20],[2,10],[1.5,5]];

async function jget(url){try{const r=await fetch(url);if(!r.ok)return null;const j=await r.json();if(j.code&&j.code!=="0")return null;return j;}catch{return null;}}

// ---- indicators ----
function ema(v,p){if(v.length<p)return null;const k=2/(p+1);let e=v[0];for(let i=1;i<v.length;i++)e=v[i]*k+e*(1-k);return e;}
function rsi(v,p=14){if(v.length<p+1)return null;let g=0,l=0;for(let i=1;i<=p;i++){const d=v[i]-v[i-1];if(d>0)g+=d;else l-=d;}g/=p;l/=p;for(let i=p+1;i<v.length;i++){const d=v[i]-v[i-1];g=(g*(p-1)+(d>0?d:0))/p;l=(l*(p-1)+(d<0?-d:0))/p;}if(l===0)return 100;return 100-100/(1+g/l);}
const clamp=x=>Math.max(0,Math.min(100,x));
function volRatio(qv,w=20){if(qv.length<w+1)return null;let s=0;for(let i=qv.length-1-w;i<qv.length-1;i++)s+=qv[i];const a=s/w;return a>0?qv[qv.length-1]/a:null;}
function bollUpper(c,p=20,m=2){if(c.length<p)return null;const w=c.slice(-p);const mid=w.reduce((a,b)=>a+b,0)/p;const sd=Math.sqrt(w.reduce((a,b)=>a+(b-mid)**2,0)/p);return mid+m*sd;}
function breakouts(h,l,c,lb=20){if(c.length<lb+2)return [];const price=c[c.length-1];const ph=Math.max(...h.slice(-lb-1,-1));const pl=Math.min(...l.slice(-lb-1,-1));const box=(ph-pl)/pl;const rh5=Math.max(...h.slice(-6,-1));const bu=bollUpper(c);const out=[];if(price>ph)out.push("ph");if(price>ph&&box<0.25)out.push("box");if(price>rh5&&c[c.length-1]>c[c.length-2]&&c[c.length-2]>c[c.length-3])out.push("dt");if(bu&&price>bu)out.push("bb");return out;}

// ---- scoring (技術 + 量能/OI) ----
function volBonus(vr){if(vr==null)return 0;for(const[t,p]of VOL_TIERS)if(vr>=t)return p;return 0;}
function scoreTechnical(t,beatsBtc,brk,rsiV){let s=50;if(t.bull)s+=18;else if(t.e20&&t.e50&&t.e20>t.e50)s+=8;if(t.above20)s+=8;s+=6*brk.length;if(rsiV!=null){if(rsiV>=55&&rsiV<=72)s+=8;else if(rsiV>80)s-=10;else if(rsiV<40)s-=6;}if(beatsBtc)s+=6;return clamp(s);}
function scoreCapital(vr,oi){let s=50;if(vr!=null)s+=volBonus(vr);if(oi!=null){if(oi>20)s+=18;else if(oi>10)s+=12;else if(oi>5)s+=6;else if(oi<-10)s-=8;}return clamp(s);}

async function pool(items,limit,fn){const out=[];let i=0;async function w(){while(i<items.length){const idx=i++;try{out[idx]=await fn(items[idx]);}catch{out[idx]=null;}}}await Promise.all(Array.from({length:Math.min(limit,items.length)},w));return out;}

// OKX 日線回傳「新到舊」,每根 [ts,o,h,l,c,vol,volCcy,volCcyQuote,confirm];volCcyQuote=該根 USDT 成交額
function parseCandles(rows){const r=rows.slice().reverse();return {c:r.map(x=>+x[4]),h:r.map(x=>+x[2]),l:r.map(x=>+x[3]),qv:r.map(x=>+x[7])};}

async function analyze(t,btc7,oiNow,oiPrev){
  const instId=t.instId,base=instId.replace("-USDT-SWAP","");
  const k=await jget(`${OKX}/api/v5/market/candles?instId=${instId}&bar=1D&limit=220`);
  if(!k||!k.data||k.data.length<60)return null;
  const {c,h,l,qv}=parseCandles(k.data);
  const price=c[c.length-1];
  const e20=ema(c,20),e50=ema(c,50),e200=ema(c,200);
  const tt={e20,e50,e200,above20:!!(e20&&price>e20),bull:!!(e20&&e50&&e200&&e20>e50&&e50>e200)};
  const rsiV=rsi(c),brk=breakouts(h,l,c);
  const chg7=c.length>=8?((price/c[c.length-8])-1)*100:null;
  const beatsBtc=chg7!=null&&chg7>btc7;
  const vr=volRatio(qv);
  // OI 變化:本次現值 vs 上次快照(跨run比較)
  const now=oiNow[instId],prev=oiPrev?oiPrev[instId]:null;
  let oi=null;if(now!=null&&prev!=null&&prev>0)oi=(now-prev)/prev*100;
  const emaBull=!!e20&&!!e50&&e20>e50;
  const techS=scoreTechnical(tt,beatsBtc,brk,rsiV);
  const capS=scoreCapital(vr,oi);
  const score=Math.round((techS+capS)/2*10)/10;
  // 候選:量≥2x + EMA多頭 + 站上EMA20 + 強於BTC +(有OI資料時要求OI≥3%)
  const cand=vr!=null&&vr>=2&&emaBull&&tt.above20&&beatsBtc&&(oi==null||oi>=3);
  return {instId,base,score,candidate:cand,chg7,vr,oi};
}

async function sendTelegram(text){
  if(!TG_TOKEN||!TG_CHAT){console.log("(未設定 Telegram secrets,略過發送)");return;}
  const r=await fetch(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({chat_id:TG_CHAT,text})});
  console.log("Telegram 發送:",r.status);
}

async function main(){
  if(process.env.TEST==="true"){await sendTelegram("✅ Alpha Scanner 雲端哨兵測試成功!(資料源:OKX)");console.log("已發送測試訊息");return;}

  const tk=await jget(`${OKX}/api/v5/market/tickers?instType=SWAP`);
  if(!tk||!tk.data){console.log("無法連線 OKX");return;}
  let list=tk.data.filter(t=>t.instId.endsWith("-USDT-SWAP")&&!STABLE.has(t.instId.replace("-USDT-SWAP","")));
  const priceMap={};list.forEach(t=>priceMap[t.instId]=+t.last);
  list.sort((a,b)=>(+b.volCcy24h*+b.last)-(+a.volCcy24h*+a.last));
  list=list.slice(0,TOP_N);

  // 一次抓全市場 OI 現值(USD ≈ oiCcy × 價格)
  const oiResp=await jget(`${OKX}/api/v5/public/open-interest?instType=SWAP`);
  const oiNow={};if(oiResp&&oiResp.data)for(const o of oiResp.data){const p=priceMap[o.instId];if(p)oiNow[o.instId]=(+o.oiCcy)*p;}

  // BTC 7 日基準
  const btcK=await jget(`${OKX}/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1D&limit=10`);
  let btc7=0;if(btcK&&btcK.data){const {c}=parseCandles(btcK.data);if(c.length>=8)btc7=((c[c.length-1]/c[c.length-8])-1)*100;}

  // 讀上次狀態(actions/cache 還原)
  const firstRun=!fs.existsSync(STATE);
  let prev={alerted:[],oi:{}};
  if(!firstRun){try{prev=JSON.parse(fs.readFileSync(STATE,"utf8"));}catch{}}

  const res=(await pool(list,5,t=>analyze(t,btc7,oiNow,prev.oi))).filter(Boolean);
  const alert=res.filter(c=>c.candidate||c.score>=MIN_SCORE).sort((a,b)=>b.score-a.score);
  const cur=alert.map(c=>c.instId);
  console.log(`掃描 ${res.length} 幣,符合 ${alert.length} 個:`,alert.map(c=>c.base).join(", ")||"(無)");

  const fresh=alert.filter(c=>!(prev.alerted||[]).includes(c.instId));
  if(firstRun){
    console.log("首次執行(OKX),建立基準,不發通知。");
  }else if(fresh.length){
    const f=(v,d=0)=>v==null?"-":(v>=0?"+":"")+v.toFixed(d);
    const lines=fresh.map(c=>`• ${c.base}  分數 ${c.score}${c.candidate?" ✅候選":""}\n   7d ${f(c.chg7)}%  量 ${c.vr?c.vr.toFixed(1)+"x":"-"}  OI ${f(c.oi)}%`);
    await sendTelegram(`🚨 Alpha Scanner 新標的 (${fresh.length})\n\n`+lines.join("\n\n")+`\n\nBTC 7d ${f(btc7,1)}%　(資料源 OKX)`);
  }else{
    console.log("無新標的,不發通知。");
  }

  fs.writeFileSync(STATE,JSON.stringify({alerted:cur,oi:oiNow,ts:Date.now()}));
}
main().catch(e=>{console.error(e);process.exit(0);});
