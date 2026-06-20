#!/usr/bin/env python3
"""
Market Scanner v3 - Unified News + Smart Money + Price
Aligned with OKX News API schema.
Sources: RSS (EN), OKX News (CN), Zhihu, Smart Money
Output: data/market_scans/scan_YYYY-MM-DD_HHMM.json
"""
import json, os, sys, requests, subprocess, time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent / "data"
NEWS_DIR = BASE_DIR / "news"
ZHIHU_DIR = BASE_DIR / "zhihu_sentiment" / "daily"
SCAN_DIR = BASE_DIR / "market_scans"
SCAN_DIR.mkdir(parents=True, exist_ok=True)

# ─── Unified Schema ─────────────────────────────────────────────────────────
# Each news item: {title, summary, ccyList, ccySentiments, importance,
#                  sentiment_score, source, platform, sourceUrl, cTime, type}

# ─── RSS Keywords ────────────────────────────────────────────────────────────
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
    if score > 0.15:
        return "bullish"
    elif score < -0.15:
        return "bearish"
    return "neutral"

def score_to_importance(score, news_count):
    abs_score = abs(score)
    if abs_score > 0.5 or news_count >= 5:
        return "high"
    elif abs_score > 0.2 or news_count >= 3:
        return "medium"
    return "low"

# ─── Data Loaders ────────────────────────────────────────────────────────────

def load_rss_news():
    """Load RSS news → unified schema."""
    items = []
    if not NEWS_DIR.exists():
        return items
    for f in sorted(NEWS_DIR.glob("*.json"))[-3:]:
        try:
            with open(f) as fh:
                data = json.load(fh)
            for item in data.get("news", []):
                title = item.get("title", "")
                desc = item.get("desc", "")
                text = f"{title} {desc}"
                score = score_text(text, BULLISH_EN, BEARISH_EN)
                coins = extract_coins(text)
                items.append({
                    "title": title[:200],
                    "summary": desc[:300],
                    "ccyList": coins,
                    "ccySentiments": [{"ccy": c, "sentiment": score_to_sentiment(score)} for c in coins],
                    "importance": score_to_importance(score, 1),
                    "sentiment_score": round(score, 3),
                    "source": "rss",
                    "platform": item.get("source", "unknown"),
                    "sourceUrl": item.get("url", ""),
                    "cTime": item.get("published", datetime.now(timezone.utc).isoformat()),
                    "type": "rss"
                })
        except Exception as e:
            print(f"  Warning RSS {f}: {e}", file=sys.stderr)
    return items

def load_okx_news():
    """Load news from OKX MCP via subprocess → unified schema."""
    items = []
    try:
        env = os.environ.copy()
        # Use live API keys for news (demo mode doesn't support news)
        okx_config = Path.home() / ".okx" / "config.toml"
        if okx_config.exists():
            import re
            content = okx_config.read_text()
            # Parse live profile
            live_match = re.search(r'\[profiles\.live\].*?api_key\s*=\s*"([^"]+)".*?api_secret\s*=\s*"([^"]+)".*?passphrase\s*=\s*"([^"]+)"', content, re.DOTALL)
            if live_match:
                env["OKX_API_KEY"] = live_match.group(1)
                env["OKX_SECRET_KEY"] = live_match.group(2)
                env["OKX_PASSPHRASE"] = live_match.group(3)

        proc = subprocess.Popen(
            ["npx", "@okx_ai/okx-trade-mcp", "--modules", "news"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env
        )

        # Initialize MCP
        init = json.dumps({"jsonrpc":"2.0","id":0,"method":"initialize",
            "params":{"protocolVersion":"2024-11-05","capabilities":{},
            "clientInfo":{"name":"scanner","version":"3.0"}}})
        proc.stdin.write(init + "\n")
        proc.stdin.flush()
        time.sleep(2)
        proc.stdout.readline()

        # Get latest news (high importance, last 6h)
        call = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
            "params":{"name":"news_get_latest","arguments":{"limit":20}}})
        proc.stdin.write(call + "\n")
        proc.stdin.flush()
        time.sleep(5)
        out = proc.stdout.readline()

        data = json.loads(out)
        content = data.get("result", {}).get("content", [{}])[0].get("text", "")
        parsed = json.loads(content)

        if parsed.get("ok") and parsed.get("data", {}).get("data"):
            for batch in parsed["data"]["data"]:
                for detail in batch.get("details", []):
                    ccy_list = detail.get("ccyList", [])
                    ccy_sentiments = []
                    for cs in detail.get("ccySentiments", []):
                        ccy_sentiments.append({"ccy": cs.get("ccy", ""), "sentiment": cs.get("sentiment", "neutral")})

                    # Compute numeric score from sentiment
                    sent_score = 0
                    for cs in ccy_sentiments:
                        if cs["sentiment"] == "bullish":
                            sent_score += 0.5
                        elif cs["sentiment"] == "bearish":
                            sent_score -= 0.5
                    if ccy_sentiments:
                        sent_score /= len(ccy_sentiments)

                    items.append({
                        "title": detail.get("title", "")[:200],
                        "summary": detail.get("summary", "")[:300],
                        "ccyList": ccy_list,
                        "ccySentiments": ccy_sentiments,
                        "importance": detail.get("importance", "medium"),
                        "sentiment_score": round(sent_score, 3),
                        "source": "okx",
                        "platform": ",".join(detail.get("platformList", ["okx"])),
                        "sourceUrl": detail.get("sourceUrl", ""),
                        "cTime": datetime.fromtimestamp(int(detail.get("cTime", 0))/1000, tz=timezone.utc).isoformat() if detail.get("cTime") else datetime.now(timezone.utc).isoformat(),
                        "type": "okx"
                    })

        proc.terminate()
    except Exception as e:
        print(f"  Warning OKX news: {e}", file=sys.stderr)
    return items

def load_zhihu():
    """Load zhihu sentiment → unified schema."""
    items = []
    if not ZHIHU_DIR.exists():
        return items
    for f in sorted(ZHIHU_DIR.glob("*.json"))[-2:]:
        try:
            with open(f) as fh:
                data = json.load(fh)
            for item in data.get("results", []):
                text = f"{item.get('title','')} {item.get('content_text','')}"
                score = score_text(text, BULLISH_ZH, BEARISH_ZH)
                items.append({
                    "title": item.get("title", "")[:100],
                    "summary": item.get("content_text", "")[:200],
                    "ccyList": extract_coins(text),
                    "ccySentiments": [],
                    "importance": "medium",
                    "sentiment_score": round(score, 3),
                    "source": "zhihu",
                    "platform": "zhihu",
                    "sourceUrl": "",
                    "cTime": item.get("crawl_time", datetime.now(timezone.utc).isoformat()),
                    "type": "zhihu"
                })
        except Exception as e:
            print(f"  Warning zhihu {f}: {e}", file=sys.stderr)
    return items

def load_okx_smartmoney():
    """Load smart money signals from OKX MCP."""
    signals = []
    try:
        env = os.environ.copy()
        okx_config = Path.home() / ".okx" / "config.toml"
        if okx_config.exists():
            import re
            content = okx_config.read_text()
            live_match = re.search(r'\[profiles\.live\].*?api_key\s*=\s*"([^"]+)".*?api_secret\s*=\s*"([^"]+)".*?passphrase\s*=\s*"([^"]+)"', content, re.DOTALL)
            if live_match:
                env["OKX_API_KEY"] = live_match.group(1)
                env["OKX_SECRET_KEY"] = live_match.group(2)
                env["OKX_PASSPHRASE"] = live_match.group(3)

        proc = subprocess.Popen(
            ["npx", "@okx_ai/okx-trade-mcp", "--modules", "smartmoney"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env
        )

        init = json.dumps({"jsonrpc":"2.0","id":0,"method":"initialize",
            "params":{"protocolVersion":"2024-11-05","capabilities":{},
            "clientInfo":{"name":"scanner","version":"3.0"}}})
        proc.stdin.write(init + "\n")
        proc.stdin.flush()
        time.sleep(2)
        proc.stdout.readline()

        # Get consensus signals for top instruments
        call = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
            "params":{"name":"smartmoney_get_signal_overview_by_filter",
            "arguments":{"topInstruments":"BTC,ETH,SOL,BNB,ARB,OP,SUI,AVAX,LINK,DOGE",
            "period":"24h","sortBy":"signalStrength"}}})
        proc.stdin.write(call + "\n")
        proc.stdin.flush()
        time.sleep(5)
        out = proc.stdout.readline()

        data = json.loads(out)
        content = data.get("result", {}).get("content", [{}])[0].get("text", "")
        parsed = json.loads(content)

        if parsed.get("ok") and parsed.get("data", {}).get("data"):
            for item in parsed["data"]["data"]:
                signals.append({
                    "inst": item.get("instId", ""),
                    "longRatio": item.get("longRatio", 0.5),
                    "shortRatio": item.get("shortRatio", 0.5),
                    "signalStrength": item.get("signalStrength", 0),
                    "capitalFlow": item.get("capitalFlow", 0),
                    "traderCount": item.get("traderCount", 0),
                    "avgPnl": item.get("avgPnl", 0),
                    "avgWinRate": item.get("avgWinRate", 0),
                    "period": "24h"
                })

        proc.terminate()
    except Exception as e:
        print(f"  Warning smart money: {e}", file=sys.stderr)
    return signals

def load_price(symbol):
    try:
        url = "https://www.okx.com/api/v5/market/ticker"
        resp = requests.get(url, params={"instId": f"{symbol.upper()}-USDT"}, timeout=10)
        data = resp.json()
        if data.get("code") == "0" and data["data"]:
            t = data["data"][0]
            return {"symbol":f"{symbol.upper()}-USDT","price":float(t["last"]),
                    "high_24h":float(t.get("high24h",0)),"low_24h":float(t.get("low24h",0)),
                    "volume_24h":float(t.get("vol24h",0))}
    except Exception as e:
        print(f"  Warning price {symbol}: {e}", file=sys.stderr)
    return None

# ─── Signal Generation ──────────────────────────────────────────────────────

def analyze_market():
    print("Market Scanner v3 starting...")

    # Load all sources
    print("  Loading RSS news...")
    rss_news = load_rss_news()
    print(f"    {len(rss_news)} items")

    print("  Loading OKX news...")
    okx_news = load_okx_news()
    print(f"    {len(okx_news)} items")

    print("  Loading zhihu sentiment...")
    zhihu = load_zhihu()
    print(f"    {len(zhihu)} items")

    print("  Loading OKX smart money...")
    smartmoney = load_okx_smartmoney()
    print(f"    {len(smartmoney)} instruments")

    print("  Fetching prices...")
    btc = load_price("btc")
    eth = load_price("eth")
    if btc:
        print(f"    BTC: ${btc['price']:,.0f}")
    if eth:
        print(f"    ETH: ${eth['price']:,.0f}")

    # ─── Aggregate sentiments per coin ───────────────────────────────────
    all_news = rss_news + okx_news
    coin_scores = defaultdict(list)      # sentiment_score per coin
    coin_sm = {}                         # smart money per coin

    for item in all_news:
        for coin in item.get("ccyList", []):
            coin_scores[coin].append(item["sentiment_score"])

    for sm in smartmoney:
        inst = sm.get("inst", "").replace("-USDT-SWAP", "").replace("-USDT", "")
        if inst:
            coin_sm[inst] = sm

    zhihu_avg = sum(z["sentiment_score"] for z in zhihu) / len(zhihu) if zhihu else 0

    # ─── Generate signals ────────────────────────────────────────────────
    signals = []
    watch_coins = set(list(coin_scores.keys()) + list(coin_sm.keys()))

    for coin in sorted(watch_coins):
        scores = coin_scores.get(coin, [])
        sm = coin_sm.get(coin)

        if not scores and not sm:
            continue

        # News sentiment (RSS + OKX)
        news_avg = sum(scores) / len(scores) if scores else 0

        # Smart money direction
        sm_score = 0
        if sm:
            lr = sm.get("longRatio", 0.5)
            sm_score = (lr - 0.5) * 2  # -1 to 1, positive = bullish

        # Weighted combination: news 40% + smart_money 35% + zhihu 25%
        if sm:
            combined = news_avg * 0.40 + sm_score * 0.35 + zhihu_avg * 0.25
        else:
            # No smart money data: news 60% + zhihu 40%
            combined = news_avg * 0.60 + zhihu_avg * 0.40

        if combined > 0.15:
            direction = "long"
            confidence = min(abs(combined) * 2, 1.0)
        elif combined < -0.15:
            direction = "short"
            confidence = min(abs(combined) * 2, 1.0)
        else:
            direction = "neutral"
            confidence = 0

        coin_price = None
        if coin == "BTC" and btc:
            coin_price = btc["price"]
        elif coin == "ETH" and eth:
            coin_price = eth["price"]
        else:
            p = load_price(coin.lower())
            if p:
                coin_price = p["price"]

        if direction != "neutral" and coin_price:
            if direction == "long":
                entry = coin_price
                stop = coin_price * 0.97
                t1 = coin_price * 1.03
                t2 = coin_price * 1.05
            else:
                entry = coin_price
                stop = coin_price * 1.03
                t1 = coin_price * 0.97
                t2 = coin_price * 0.95
            rr = abs(t1 - entry) / abs(stop - entry) if abs(stop - entry) > 0 else 0

            reasons = [f"news:{news_avg:+.3f}({len(scores)})"]
            if sm:
                reasons.append(f"sm:{sm_score:+.3f}(lr={sm.get('longRatio',0):.0%},wr={sm.get('avgWinRate',0):.0%})")
            reasons.append(f"zhihu:{zhihu_avg:+.3f}")
            reasons.append(f"combined:{combined:+.3f}")

            signals.append({
                "inst": f"{coin}-USDT-SWAP",
                "price": coin_price,
                "direction": direction,
                "score": round(confidence * 10, 1),
                "confidence": round(confidence, 2),
                "entry": entry,
                "stop": stop,
                "target_1": t1,
                "target_2": t2,
                "risk_reward": round(rr, 2),
                "sentiment": round(combined, 3),
                "news_count": len(scores),
                "smartmoney": bool(sm),
                "reasons": reasons
            })

    signals.sort(key=lambda x: x["confidence"], reverse=True)

    scan = {
        "version": "v3",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M"),
        "market": {
            "btc_price": btc["price"] if btc else None,
            "eth_price": eth["price"] if eth else None,
            "zhihu_sentiment": round(zhihu_avg, 3),
            "rss_count": len(rss_news),
            "okx_count": len(okx_news),
            "zhihu_count": len(zhihu),
            "smartmoney_count": len(smartmoney)
        },
        "signals": signals
    }

    filename = f"scan_{scan['timestamp']}.json"
    filepath = SCAN_DIR / filename
    with open(filepath, "w") as f:
        json.dump(scan, f, indent=2)

    print(f"\n  Scan complete: {len(signals)} signals")
    print(f"  Sources: RSS={len(rss_news)} OKX={len(okx_news)} Zhihu={len(zhihu)} SM={len(smartmoney)}")
    print(f"  Saved: {filepath}")
    if signals:
        print(f"\n  Top signals:")
        for s in signals[:5]:
            sm_tag = " [SM]" if s.get("smartmoney") else ""
            print(f"    {s['inst']}: {s['direction']} (conf={s['confidence']}){sm_tag}")
            print(f"      Entry: ${s['entry']:,.2f} | Stop: ${s['stop']:,.2f} | Target: ${s['target_1']:,.2f}")
    return scan

if __name__ == "__main__":
    analyze_market()
