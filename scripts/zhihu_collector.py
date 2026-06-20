#!/usr/bin/env python3
"""知乎情绪采集器 - 每小时运行 - OKX对齐格式"""
import json, sys, time, os, re
from pathlib import Path

# Load .env
env_path = Path.home() / ".hermes" / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

sys.path.insert(0, str(Path(__file__).parent))
from zhihu_api import search, hot_list, load_quota, save_quota, ALL_KEYWORDS, DATA_DIR

BJT_OFFSET = 28800  # UTC+8

# Coin mapping for extracting from Chinese text
COIN_MAP = {
    "比特币": "BTC", "btc": "BTC", "以太坊": "ETH", "eth": "ETH",
    "Solana": "SOL", "sol": "SOL", "XRP瑞波": "XRP", "xrp": "XRP",
    "DOGE狗狗币": "DOGE", "doge": "DOGE", "ADA": "ADA", "AVAX": "AVAX",
    "DOT": "DOT", "LINK": "LINK", "UNI": "UNI", "TON": "TON",
    "SUI": "SUI", "APT": "APT", "NEAR": "NEAR", "PEPE": "PEPE",
    "ARB": "ARB", "OP": "OP", "AAVE": "AAVE", "BNB": "BNB",
    "DeFi": "DEFI", "NFT": "NFT", "Layer2": "L2", "Web3": "WEB3",
    "稳定币": "STABLECOIN", "ETF": "ETF", "挖矿": "MINING", "空投": "AIRDROP",
    "苹果": "AAPL", "特斯拉": "TSLA", "英伟达": "NVDA", "谷歌": "GOOGL",
    "微软": "MSFT", "Meta": "META", "亚马逊": "AMZN", "台积电": "TSM",
    "小米": "XIACY", "比亚迪": "BYDDY",
    "美联储": "FED", "通胀": "CPI", "GDP": "GDP", "利率": "RATE",
    "降息": "RATE_CUT", "加息": "RATE_HIKE", "衰退": "RECESSION",
    "就业": "EMPLOYMENT", "CPI": "CPI", "PPI": "PPI"
}

# Sentiment keywords
BULLISH_ZH = ["牛市", "看涨", "上涨", "突破", "利好", "买入", "抄底", "反弹", "暴涨", "起飞", "增长", "创新高", "强势"]
BEARISH_ZH = ["熊市", "看跌", "下跌", "暴跌", "利空", "卖出", "恐慌", "崩盘", "割肉", "风险", "爆仓", "清算", "监管"]

def extract_coins_from_text(text):
    """Extract coin symbols from Chinese text."""
    coins = set()
    for cn, sym in COIN_MAP.items():
        if cn in text:
            coins.add(sym)
    return list(coins)

def analyze_sentiment(text):
    """Analyze sentiment from Chinese text."""
    bull = sum(1 for w in BULLISH_ZH if w in text)
    bear = sum(1 for w in BEARISH_ZH if w in text)
    total = bull + bear
    if total == 0:
        return 0.0, "neutral"
    score = (bull - bear) / total
    sentiment = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return round(score, 3), sentiment

def convert_to_okx_format(results):
    """Convert zhihu results to OKX-aligned format."""
    items = []
    for r in results:
        title = r.get("title", "")
        content = r.get("content_text", "")
        text = f"{title} {content}"
        
        coins = extract_coins_from_text(text)
        score, sentiment = analyze_sentiment(text)
        
        items.append({
            "title": title[:200],
            "summary": content[:300],
            "ccyList": coins,
            "ccySentiments": [{"ccy": c, "sentiment": sentiment} for c in coins],
            "importance": "high" if abs(score) > 0.5 else "medium" if abs(score) > 0.2 else "low",
            "sentiment_score": score,
            "source": "zhihu",
            "platform": "zhihu",
            "sourceUrl": r.get("url", ""),
            "cTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r.get("edit_time", time.time()))),
            "type": "zhihu",
            "keyword": r.get("keyword", ""),
            "votes": r.get("votes", 0),
            "comments": r.get("comments", 0)
        })
    return items

def collect_batch(batch_size=20):
    state = load_quota()
    results = []
    done = set(state.get("searches_done", []))
    remaining = [kw for kw in ALL_KEYWORDS if kw not in done]
    if not remaining:
        state["searches_done"] = []
        remaining = ALL_KEYWORDS.copy()
    
    batch = remaining[:batch_size]
    calls = 0
    
    for kw in batch:
        zp = state["pools"]["zhihu_search"]
        gp = state["pools"]["global_search"]
        if zp["used"] >= zp["limit"] or gp["used"] >= gp["limit"]:
            break
        
        for ep in ["zhihu", "global"]:
            r = search(kw, endpoint=ep)
            pool = "zhihu_search" if ep == "zhihu" else "global_search"
            state["pools"][pool]["used"] += 1
            calls += 1
            results.extend(r)
            time.sleep(0.8)
        
        state["searches_done"].append(kw)
    
    # Hot list at 00/06/12/18 BJT
    now_bjt = time.gmtime(time.time() + BJT_OFFSET)
    hour = now_bjt.tm_hour
    if hour in (0, 6, 12, 18) and state["pools"]["hot_list"]["used"] < state["pools"]["hot_list"]["limit"]:
        hot = hot_list(15)
        results.extend(hot)
        state["pools"]["hot_list"]["used"] += 1
        calls += 1
    
    if results:
        date_str = time.strftime("%Y-%m-%d", now_bjt)
        hour_dir = DATA_DIR / "daily"
        hour_dir.mkdir(parents=True, exist_ok=True)
        filepath = hour_dir / f"{date_str}_{hour:02d}00.json"
        
        # Convert to OKX-aligned format
        okx_items = convert_to_okx_format(results)
        
        with open(filepath, "w") as f:
            json.dump({
                "date": date_str, 
                "hour": hour, 
                "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S", now_bjt),
                "pools": state["pools"], 
                "count": len(okx_items),
                "results": okx_items
            }, f, ensure_ascii=False, indent=2)
        print(f"  Saved {len(okx_items)} results to {filepath.name}")
    
    save_quota(state)
    return calls

def burn_remaining():
    """Burn remaining quota - loops until exhausted."""
    state = load_quota()
    all_results = []
    total_calls = 0
    
    # Burn hot list first
    h_remaining = state["pools"]["hot_list"]["limit"] - state["pools"]["hot_list"]["used"]
    if h_remaining > 0:
        for _ in range(h_remaining):
            hot = hot_list(30)
            all_results.extend(hot)
            state["pools"]["hot_list"]["used"] += 1
            total_calls += 1
            time.sleep(0.5)
        print(f"  Burned {h_remaining} hot list calls")
    
    # Loop until search quota exhausted
    while (state["pools"]["zhihu_search"]["used"] < state["pools"]["zhihu_search"]["limit"] and
           state["pools"]["global_search"]["used"] < state["pools"]["global_search"]["limit"]):
        
        # Reset keywords if all done
        done = set(state.get("searches_done", []))
        keywords = [kw for kw in ALL_KEYWORDS if kw not in done]
        if not keywords:
            state["searches_done"] = []
            keywords = ALL_KEYWORDS.copy()
        
        # Process one batch
        for kw in keywords:
            if (state["pools"]["zhihu_search"]["used"] >= state["pools"]["zhihu_search"]["limit"] or
                state["pools"]["global_search"]["used"] >= state["pools"]["global_search"]["limit"]):
                break
            
            for ep in ["zhihu", "global"]:
                pool = "zhihu_search" if ep == "zhihu" else "global_search"
                if state["pools"][pool]["used"] >= state["pools"][pool]["limit"]:
                    break
                r = search(kw, endpoint=ep)
                state["pools"][pool]["used"] += 1
                total_calls += 1
                all_results.extend(r)
                time.sleep(0.3)
            
            state["searches_done"].append(kw)
        
        # Save intermediate results
        if all_results:
            now_bjt = time.gmtime(time.time() + 28800)
            date_str = time.strftime("%Y-%m-%d", now_bjt)
            hour = now_bjt.tm_hour
            hour_dir = DATA_DIR / "daily"
            hour_dir.mkdir(parents=True, exist_ok=True)
            filepath = hour_dir / f"{date_str}_{hour:02d}00_burn.json"
            
            okx_items = convert_to_okx_format(all_results)
            
            with open(filepath, "w") as f:
                json.dump({
                    "date": date_str, 
                    "hour": hour, 
                    "mode": "burn",
                    "pools": state["pools"], 
                    "count": len(okx_items),
                    "results": okx_items
                }, f, ensure_ascii=False, indent=2)
            print(f"  Saved {len(okx_items)} results (calls: {total_calls})")
            all_results = []
        
        save_quota(state)
    
    save_quota(state)
    return total_calls

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    if cmd == "burn":
        print(f"=== Zhihu Burn Mode ===")
        print(f"Time: {time.strftime('%Y-%m-%d %H:%M BJT', time.gmtime(time.time() + BJT_OFFSET))}")
        calls = burn_remaining()
        print(f"Burned: {calls} calls")
        from zhihu_api import check_quota
        check_quota()
        return
    if cmd == "collect":
        print(f"=== Zhihu Collector ===")
        print(f"Time: {time.strftime('%Y-%m-%d %H:%M BJT', time.gmtime(time.time() + BJT_OFFSET))}")
        calls = collect_batch()
        print(f"Calls: {calls}")
    elif cmd == "status":
        from zhihu_api import check_quota
        check_quota()

if __name__ == "__main__":
    main()
