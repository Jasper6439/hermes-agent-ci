#!/usr/bin/env python3
"""
Market Scanner v3 - Unified News + Smart Money + Price
Aligned with OKX News API schema.
Sources: RSS (EN), OKX News (CN), Zhihu, Smart Money
Output: data/market_scans/scan_YYYY-MM-DD_HHMM.json
"""
import json, os, sys, requests, subprocess, time, re
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pathlib import Path

# Data paths: hermes/data + trading-system/data (where RSS/zhihu actually live)
BASE_DIR = Path(__file__).parent.parent / "data"
TS_DATA = Path.home() / "workspace" / "projects" / "trading-system" / "data"
NEWS_DIR = TS_DATA / "news"  # RSS news lives here
ZHIHU_DIR = TS_DATA / "zhihu_sentiment" / "daily"  # Zhihu lives here
SCAN_DIR = Path.home() / "workspace" / "projects" / "trading-system" / "data" / "market_scans"
SCAN_DIR.mkdir(parents=True, exist_ok=True)

BULLISH_EN = ["bullish","surge","rally","pump","breakout","adoption","partnership",
    "approval","etf","institutional","buy","accumulate","ath","record","growth",
    "positive","gain","profit","upgrade","launch","milestone","support","recovery"]
BEARISH_EN = ["bearish","crash","dump","sell","ban","hack","exploit","decline",
    "drop","regulation","sec","lawsuit","fraud","outflow","fear","panic","loss",
    "negative","warning","risk","downgrade","delay","reject","vulnerability","scam"]
BULLISH_ZH = ["牛市","看涨","上涨","突破","利好","买入","抄底","反弹","暴涨","起飞"]
BEARISH_ZH = ["熊市","看跌","下跌","暴跌","利空","卖出","恐慌","崩盘","割肉","风险"]
COIN_MAP = {"bitcoin":"BTC","btc":"BTC","ethereum":"ETH","eth":"ETH","solana":"SOL",
    "sol":"SOL","bnb":"BNB","xrp":"XRP","cardano":"ADA","ada":"ADA","dogecoin":"DOGE",
    "doge":"DOGE","polkadot":"DOT","dot":"DOT","avalanche":"AVAX","avax":"AVAX",
    "chainlink":"LINK","link":"LINK","polygon":"MATIC","matic":"MATIC","uniswap":"UNI",
    "uni":"UNI","aave":"AAVE","cosmos":"ATOM","atom":"ATOM","near":"NEAR",
    "aptos":"APT","apt":"APT","sui":"SUI","arbitrum":"ARB","arb":"ARB",
    "optimism":"OP","op":"OP","pepe":"PEPE","ton":"TON","litecoin":"LTC",
    "ltc":"LTC","tia":"TIA","celestia":"TIA","inj":"INJ","injective":"INJ"}

def score_text(text, bullish, bearish):
    t = text.lower()
    b = sum(1 for w in bullish if w.lower() in t)
    s = sum(1 for w in bearish if w.lower() in t)
    total = b + s
    return (b - s) / total if total > 0 else 0.0

def extract_coins(text):
    t = text.lower()
    return list(set(sym for kw, sym in COIN_MAP.items() if kw in t))

def score_to_sentiment(score):
    if score > 0.15: return "bullish"
    elif score < -0.15: return "bearish"
    return "neutral"

def get_okx_live_env():
    env = os.environ.copy()
    okx_config = Path.home() / ".okx" / "config.toml"
    if okx_config.exists():
        content = okx_config.read_text()
        m = re.search(r'\[profiles\.live\].*?api_key\s*=\s*"([^"]+)".*?api_secret\s*=\s*"([^"]+)".*?passphrase\s*=\s*"([^"]+)"', content, re.DOTALL)
        if m:
            env["OKX_API_KEY"] = m.group(1)
            env["OKX_SECRET_KEY"] = m.group(2)
            env["OKX_PASSPHRASE"] = m.group(3)
    return env

def mcp_call(tool, args, module):
    proc = subprocess.Popen(
        ["npx", "@okx_ai/okx-trade-mcp", "--modules", module],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=get_okx_live_env()
    )
    init = json.dumps({"jsonrpc":"2.0","id":0,"method":"initialize",
        "params":{"protocolVersion":"2024-11-05","capabilities":{},
        "clientInfo":{"name":"scanner","version":"3.0"}}})
    proc.stdin.write(init + "\n")
    proc.stdin.flush()
    time.sleep(2)
    proc.stdout.readline()
    call = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
        "params":{"name":tool,"arguments":args}})
    proc.stdin.write(call + "\n")
    proc.stdin.flush()
    time.sleep(8)
    out = proc.stdout.readline()
    proc.terminate()
    try:
        data = json.loads(out)
        content = data.get("result",{}).get("content",[{}])[0].get("text","")
        return json.loads(content)
    except:
        return {}

def load_rss_news():
    items = []
    if not NEWS_DIR.exists(): return items
    for f in sorted(NEWS_DIR.glob("*.json"))[-3:]:
        try:
            with open(f) as fh: data = json.load(fh)
            for item in data.get("news", []):
                title = item.get("title","")
                text = f"{title} {item.get('desc','')}"
                score = score_text(text, BULLISH_EN, BEARISH_EN)
                coins = extract_coins(text)
                items.append({"title":title[:200],"summary":item.get("desc","")[:300],
                    "ccyList":coins,"ccySentiments":[{"ccy":c,"sentiment":score_to_sentiment(score)} for c in coins],
                    "importance":"high" if abs(score)>0.5 else "medium" if abs(score)>0.2 else "low",
                    "sentiment_score":round(score,3),"source":"rss","platform":item.get("source","unknown"),
                    "sourceUrl":item.get("url",""),"cTime":item.get("published",""),"type":"rss"})
        except Exception as e: print(f"  Warning RSS {f}: {e}", file=sys.stderr)
    return items

def load_okx_news():
    items = []
    try:
        parsed = mcp_call("news_get_latest", {"limit":20}, "news")
        if parsed.get("ok") and parsed.get("data",{}).get("data"):
            for batch in parsed["data"]["data"]:
                for d in batch.get("details",[]):
                    ccy_list = d.get("ccyList",[])
                    # Also extract coins from title if ccyList is empty
                    if not ccy_list:
                        ccy_list = extract_coins(d.get("title","") + " " + d.get("summary",""))
                    ccy_s = [{"ccy":cs["ccy"],"sentiment":cs.get("sentiment","neutral")} for cs in d.get("ccySentiments",[])]
                    sc = sum(0.5 if cs["sentiment"]=="bullish" else -0.5 if cs["sentiment"]=="bearish" else 0 for cs in ccy_s)/max(len(ccy_s),1)
                    items.append({"title":d.get("title","")[:200],"summary":d.get("summary","")[:300],
                        "ccyList":ccy_list,"ccySentiments":ccy_s,"importance":d.get("importance","medium"),
                        "sentiment_score":round(sc,3),"source":"okx","platform":",".join(d.get("platformList",["okx"])),
                        "sourceUrl":d.get("sourceUrl",""),
                        "cTime":datetime.fromtimestamp(int(d.get("cTime",0))/1000,tz=timezone.utc).isoformat() if d.get("cTime") else "",
                        "type":"okx"})
    except Exception as e: print(f"  Warning OKX news: {e}", file=sys.stderr)
    return items

def load_zhihu():
    items = []
    if not ZHIHU_DIR.exists(): return items
    for f in sorted(ZHIHU_DIR.glob("*.json"))[-2:]:
        try:
            with open(f) as fh: data = json.load(fh)
            for item in data.get("results",[]):
                text = f"{item.get('title','')} {item.get('content_text','')}"
                score = score_text(text, BULLISH_ZH, BEARISH_ZH)
                items.append({"title":item.get("title","")[:100],"summary":item.get("content_text","")[:200],
                    "ccyList":extract_coins(text),"ccySentiments":[],"importance":"medium",
                    "sentiment_score":round(score,3),"source":"zhihu","platform":"zhihu",
                    "sourceUrl":"","cTime":item.get("crawl_time",""),"type":"zhihu"})
        except Exception as e: print(f"  Warning zhihu {f}: {e}", file=sys.stderr)
    return items

def load_okx_smartmoney():
    signals = []
    try:
        parsed = mcp_call("smartmoney_get_signal_overview_by_filter",
            {"period":"3","sortBy":"pnl","lmtNum":20}, "smartmoney")
        if parsed.get("ok") and parsed.get("data",{}).get("data"):
            for item in parsed["data"]["data"]:
                ccy = item.get("ccy","")
                if not ccy: continue
                lr = item.get("longShortRatio",{})
                long_ratio = float(lr.get("longRatio",0.5))
                short_ratio = float(lr.get("shortRatio",0.5))
                wr = item.get("winRate",{})
                long_wr = float(wr.get("avgLongWinRate",0)) if wr.get("avgLongWinRate") else 0
                short_wr = float(wr.get("avgShortWinRate",0)) if wr.get("avgShortWinRate") else 0
                notional = item.get("notional",{})
                long_notional = float(notional.get("longNotionalUsdt",0))
                short_notional = float(notional.get("shortNotionalUsdt",0))
                entry = float(notional.get("smartMoneyLongAvgEntry",0)) if notional.get("smartMoneyLongAvgEntry") else 0

                signals.append({"inst":f"{ccy}-USDT-SWAP","ccy":ccy,
                    "longRatio":long_ratio,"shortRatio":short_ratio,
                    "longTraders":item.get("longTraders",0),"shortTraders":item.get("shortTraders",0),
                    "tradersQualified":item.get("tradersQualified",0),
                    "longWinRate":round(long_wr,4),"shortWinRate":round(short_wr,4),
                    "longNotional":long_notional,"shortNotional":short_notional,
                    "entry":entry,"period":"3d"})
    except Exception as e: print(f"  Warning smart money: {e}", file=sys.stderr)
    return signals

def load_price(symbol):
    try:
        resp = requests.get("https://www.okx.com/api/v5/market/ticker", params={"instId":f"{symbol.upper()}-USDT"}, timeout=10)
        data = resp.json()
        if data.get("code")=="0" and data["data"]:
            t = data["data"][0]
            return {"symbol":f"{symbol.upper()}-USDT","price":float(t["last"]),
                "high_24h":float(t.get("high24h",0)),"low_24h":float(t.get("low24h",0)),
                "volume_24h":float(t.get("vol24h",0))}
    except: pass
    return None

def analyze_market():
    print("Market Scanner v3 starting...")
    print("  Loading RSS news...")
    rss = load_rss_news()
    print(f"    {len(rss)} items")
    print("  Loading OKX news...")
    okx = load_okx_news()
    print(f"    {len(okx)} items")
    print("  Loading zhihu...")
    zhihu = load_zhihu()
    print(f"    {len(zhihu)} items")
    print("  Loading smart money...")
    sm = load_okx_smartmoney()
    print(f"    {len(sm)} instruments")
    print("  Fetching prices...")
    btc = load_price("btc")
    eth = load_price("eth")
    if btc: print(f"    BTC: ${btc['price']:,.0f}")
    if eth: print(f"    ETH: ${eth['price']:,.0f}")

    all_news = rss + okx
    coin_scores = defaultdict(list)
    coin_sm = {}
    for item in all_news:
        for coin in item.get("ccyList",[]):
            coin_scores[coin].append(item["sentiment_score"])
    for s in sm:
        ccy = s.get("ccy","")
        if ccy: coin_sm[ccy] = s
    zhihu_avg = sum(z["sentiment_score"] for z in zhihu)/len(zhihu) if zhihu else 0

    signals = []
    watch = set(list(coin_scores.keys()) + list(coin_sm.keys()))
    for coin in sorted(watch):
        scores = coin_scores.get(coin,[])
        s = coin_sm.get(coin)
        if not scores and not s: continue
        news_avg = sum(scores)/len(scores) if scores else 0

        # Smart money: long ratio as signal (-1 to 1)
        sm_score = 0
        if s:
            lr = s.get("longRatio",0.5)
            sm_score = (lr - 0.5) * 2

        # AB² weights: news component = 48% of overall signal
        # Within news component: OKX/RSS 60%, Smart Money 25%, Zhihu 15%
        if s:
            combined = news_avg*0.60 + sm_score*0.25 + zhihu_avg*0.15
        else:
            # No smart money: OKX/RSS 70%, Zhihu 30%
            combined = news_avg*0.70 + zhihu_avg*0.30

        direction = "long" if combined > 0.15 else "short" if combined < -0.15 else "neutral"
        confidence = min(abs(combined)*2, 1.0) if direction != "neutral" else 0

        p = None
        if coin=="BTC" and btc: p = btc["price"]
        elif coin=="ETH" and eth: p = eth["price"]
        else: pp = load_price(coin.lower()); p = pp["price"] if pp else None

        if direction != "neutral" and p:
            if direction == "long":
                entry,stop,t1,t2 = p, p*0.97, p*1.03, p*1.05
            else:
                entry,stop,t1,t2 = p, p*1.03, p*0.97, p*0.95
            rr = abs(t1-entry)/abs(stop-entry) if abs(stop-entry)>0 else 0
            reasons = [f"news:{news_avg:+.3f}({len(scores)})"]
            if s:
                reasons.append(f"sm:{sm_score:+.3f}(lr={s.get('longRatio',0):.0%},wr={s.get('longWinRate',0):.0%},traders={s.get('longTraders',0)}+{s.get('shortTraders',0)})")
            reasons.append(f"zhihu:{zhihu_avg:+.3f}")
            reasons.append(f"combined:{combined:+.3f}")
            signals.append({"inst":f"{coin}-USDT-SWAP","price":p,"direction":direction,
                "score":round(confidence*10,1),"confidence":round(confidence,2),
                "entry":entry,"stop":stop,"target_1":t1,"target_2":t2,"risk_reward":round(rr,2),
                "sentiment":round(combined,3),"news_count":len(scores),"smartmoney":bool(s),"reasons":reasons})

    signals.sort(key=lambda x: x["confidence"], reverse=True)
    scan = {"version":"v3","timestamp":datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M"),
        "market":{"btc_price":btc["price"] if btc else None,"eth_price":eth["price"] if eth else None,
            "zhihu_sentiment":round(zhihu_avg,3),"rss_count":len(rss),"okx_count":len(okx),
            "zhihu_count":len(zhihu),"smartmoney_count":len(sm)},
        "signals":signals}
    filepath = SCAN_DIR / f"scan_{scan['timestamp']}.json"
    with open(filepath,"w") as f: json.dump(scan, f, indent=2)
    print(f"\n  Scan complete: {len(signals)} signals")
    print(f"  Sources: RSS={len(rss)} OKX={len(okx)} Zhihu={len(zhihu)} SM={len(sm)}")
    print(f"  Saved: {filepath}")
    for s in signals[:5]:
        sm_tag = " [SM]" if s.get("smartmoney") else ""
        print(f"    {s['inst']}: {s['direction']} (conf={s['confidence']}){sm_tag}")
        print(f"      Entry: ${s['entry']:,.2f} | Stop: ${s['stop']:,.2f} | Target: ${s['target_1']:,.2f}")
    return scan

if __name__ == "__main__":
    analyze_market()
