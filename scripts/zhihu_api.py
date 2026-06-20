#!/usr/bin/env python3
"""知乎开放平台 API"""
import json, os, sys, time, urllib.request, urllib.parse
from pathlib import Path

ZHIHU_API_KEY = os.environ.get("ZHIHU_API_KEY", "")
BASE_URL = "https://developer.zhihu.com/api/v1/content/"
DATA_DIR = Path.home() / "workspace" / "projects" / "trading-system" / "zhihu_sentiment"
QUOTA_FILE = DATA_DIR / "quota_state.json"

CRYPTO_MAJOR = ["比特币","BTC","以太坊","ETH","Solana","SOL","XRP瑞波","DOGE狗狗币","ADA","AVAX","DOT","LINK","UNI","TON","SUI","APT","NEAR","PEPE","ARB","OP","AAVE","BNB"]
CRYPTO_NARRATIVE = ["DeFi","NFT","Layer2","Web3","稳定币","ETF","挖矿","空投"]
STOCKS_TECH = ["苹果","特斯拉","英伟达","谷歌","微软","Meta","亚马逊","台积电","小米","比亚迪"]
MACRO = ["美联储","通胀","GDP","利率","降息","加息","衰退","就业","CPI","PPI"]
ALL_KEYWORDS = CRYPTO_MAJOR + CRYPTO_NARRATIVE + STOCKS_TECH + MACRO

def _api_call(endpoint, params=None):
    url = BASE_URL + endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "Authorization": "Bearer " + ZHIHU_API_KEY,
        "X-Request-Timestamp": str(int(time.time())),
        "Content-Type": "application/json"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"Code": -1, "Message": str(e)}

def search(query, count=10, endpoint="zhihu"):
    ep = "zhihu_search" if endpoint == "zhihu" else "global_search"
    data = _api_call(ep, {"Query": query, "Count": min(count, 10)})
    if data.get("Code") != 0:
        return []
    return [{
        "keyword": query, "endpoint": endpoint,
        "title": i.get("Title",""), "content_type": i.get("ContentType",""),
        "content_text": i.get("ContentText","")[:500], "url": i.get("Url",""),
        "votes": i.get("VoteUpCount",0), "comments": i.get("CommentCount",0),
        "author": i.get("AuthorName",""), "edit_time": i.get("EditTime",0),
        "ranking_score": i.get("RankingScore",0)
    } for i in data.get("Data",{}).get("Items",[])]

def hot_list(limit=30):
    data = _api_call("hot_list", {"Limit": min(limit, 30)})
    if data.get("Code") != 0:
        return []
    return [{"title": i.get("Title",""), "url": i.get("Url",""), "summary": i.get("Summary",""), "type": "hot_list"}
            for i in data.get("Data",{}).get("Items",[])]

def load_quota():
    today = time.strftime("%Y-%m-%d", time.gmtime(28800))
    default = {"date": today, "pools": {"zhihu_search":{"used":0,"limit":1000},"global_search":{"used":0,"limit":1000},"hot_list":{"used":0,"limit":10},"zhida":{"used":0,"limit":10}}, "searches_done": []}
    if QUOTA_FILE.exists():
        try:
            with open(QUOTA_FILE) as f: state = json.load(f)
            if state.get("date") == today: return state
        except: pass
    return default

def save_quota(state):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(QUOTA_FILE, "w") as f: json.dump(state, f, indent=2)

def check_quota():
    state = load_quota()
    print("=== Zhihu Quota ===")
    for p, info in state.get("pools", {}).items():
        print(f"  {p}: {info['used']}/{info['limit']} ({info['limit']-info['used']} left)")
    print(f"  Keywords done: {len(state.get('searches_done',[]))}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: zhihu_api.py [search|global|hot|quota] [query/limit]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "search":
        q = sys.argv[2] if len(sys.argv) > 2 else "比特币"
        for r in search(q, endpoint="zhihu"):
            print(f"  [{r['votes']}↑ {r['comments']}💬] {r['title'][:70]}")
    elif cmd == "global":
        q = sys.argv[2] if len(sys.argv) > 2 else "比特币"
        for r in search(q, endpoint="global"):
            print(f"  [{r['votes']}↑ {r['comments']}💬] {r['title'][:70]}")
    elif cmd == "hot":
        for i, r in enumerate(hot_list(int(sys.argv[2]) if len(sys.argv)>2 else 15), 1):
            print(f"  {i}. {r['title'][:60]}")
    elif cmd == "quota":
        check_quota()
