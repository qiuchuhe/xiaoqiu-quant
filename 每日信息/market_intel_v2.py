# -*- coding: utf-8 -*-
"""
盘后情报收集 v2 — 多源新闻聚合 + 增量收集
用法:
    python market_intel_v2.py              # 收盘后跑一次
    python market_intel_v2.py --update     # 增量更新(追加新新闻)
    python market_intel_v2.py --final      # 隔夜终版(汇总+生成报告)
数据源: 新浪+华尔街见闻+东方财富(akshare)+百度经济+雪球热榜
"""
import sys, os, json, re, time
from datetime import datetime

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "每日新闻")
CACHE_FILE = os.path.join(OUTPUT_DIR, "daily_news_cache.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
NOW = datetime.now()
TODAY = NOW.strftime("%Y-%m-%d")

def fetch_sina_news(count=15):
    """新浪宏观新闻"""
    import urllib.request
    try:
        url = f"https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num={count}&page=1"
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        items = data.get("result", {}).get("data", [])
        news = []
        for item in items:
            ts = int(item.get("ctime", 0))
            dt = datetime.fromtimestamp(ts).strftime("%H:%M")
            news.append({"time": dt, "title": item.get("title", ""), "source": "新浪宏观"})
        return news
    except Exception as e:
        print(f"  新浪: {e}")
        return []

def fetch_wscn_news(channel="a-stock-channel", count=10):
    """华尔街见闻快讯"""
    import urllib.request
    try:
        url = f"https://api-one.wallstcn.com/apiv1/content/lives?channel={channel}&limit={count}"
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        items = data.get("data", {}).get("items", [])
        news = []
        for item in items:
            ts = item.get("display_time", 0)
            dt = datetime.fromtimestamp(ts).strftime("%H:%M")
            text = re.sub(r'<[^>]+>', '', item.get("content_text", "")[:120])
            news.append({"time": dt, "title": text, "source": f"华尔街见闻"})
        return news
    except Exception as e:
        print(f"  华尔街见闻: {e}")
        return []

def fetch_em_news():
    """东方财富新闻——通过akshare"""
    try:
        import akshare as ak
        df = ak.stock_news_em()
        news = []
        for _, row in df.iterrows():
            news.append({
                "time": str(row.iloc[3])[-8:-3] if len(str(row.iloc[3])) > 8 else str(row.iloc[3]),
                "title": str(row.iloc[1])[:150],
                "source": "东方财富",
            })
        return news
    except Exception as e:
        print(f"  东方财富(akshare): {e}")
        return []

def fetch_baidu_economic():
    """百度经济新闻——只保留中国相关"""
    try:
        import akshare as ak
        df = ak.news_economic_baidu(date=TODAY.replace("-", ""))
        news = []
        for _, row in df.iterrows():
            title = str(row.iloc[3])[:150] if len(row) > 3 else str(row.iloc[2])[:150]
            # 只保留中国/重大国际
            if not any(kw in title for kw in ["中国", "M2", "CPI", "PPI", "社融", "贷款", "LPR", "人民币",
                "上期所", "央行", "美联储", "美联", "欧央行", "加息", "降息", "GDP", "PMI", "非农", "原油"]):
                continue
            # 统一时间为今日日期
            news.append({
                "time": TODAY,
                "title": title,
                "source": "百度经济",
            })
        return news
    except Exception as e:
        print(f"  百度经济(akshare): {e}")
        return []

def fetch_hot_stocks():
    """热门股票——东方财富人气榜"""
    try:
        import akshare as ak
        df = ak.stock_hot_rank_em()
        stocks = []
        for _, row in df.head(15).iterrows():
            stocks.append(f"{row.iloc[1]}({row.iloc[2]})")
        return stocks
    except Exception as e:
        print(f"  热门股票: {e}")
        return []

def collect_all_news():
    """全量收集所有新闻源"""
    print(f"\n{'='*50}")
    print(f"  情报收集 | {NOW.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    all_news = []

    sources = [
        ("新浪宏观", lambda: fetch_sina_news(20)),
        ("华尔街见闻·A股", lambda: fetch_wscn_news("a-stock-channel", 15)),
        ("华尔街见闻·全球", lambda: fetch_wscn_news("global-channel", 15)),
        ("东方财富", fetch_em_news),
        ("百度经济", fetch_baidu_economic),
    ]

    for name, func in sources:
        print(f"  [{name}]...", end=" ")
        try:
            items = func()
            all_news.extend(items)
            print(f"{len(items)}条")
        except Exception as e:
            print(f"失败: {e}")

    # 去重
    seen = set()
    deduped = []
    for n in all_news:
        key = n["title"][:40]
        if key not in seen:
            seen.add(key)
            deduped.append(n)

    deduped.sort(key=lambda x: x["time"], reverse=True)
    print(f"\n  去重后: {len(deduped)}条")
    return deduped

def save_news_md(news, hot_stocks=None, mode="update"):
    """保存新闻到Markdown — 基于cache全量重写，不嵌套"""
    md_path = os.path.join(OUTPUT_DIR, f"{TODAY}-晚间情报.md")
    now_str = NOW.strftime("%H:%M")

    # 加载已有cache，合并去重
    all_news = load_cache()
    existing_keys = {n["title"][:40] for n in all_news}
    new_count = 0
    for n in news:
        key = n["title"][:40]
        if key not in existing_keys:
            existing_keys.add(key)
            all_news.append(n)
            new_count += 1

    # 排序：新浪/华尔街见闻优先，百度经济靠后
    priority = {"新浪宏观": 0, "华尔街见闻": 0, "东方财富": 1, "百度经济": 2}
    all_news.sort(key=lambda x: (priority.get(x["source"], 1), x["time"]), reverse=False)
    # 再按时间反序
    all_news.sort(key=lambda x: str(x["time"]), reverse=True)
    # 新闻源优先置顶
    all_news.sort(key=lambda x: priority.get(x["source"], 1))

    # 保存cache
    save_cache(all_news)

    # 生成MD — 只保留前80条，百度经济最多20条
    baidu_count = 0
    filtered = []
    for n in all_news:
        if n["source"] == "百度经济":
            if baidu_count >= 20:
                continue
            # 只保留中国相关
            if not any(kw in n["title"] for kw in ["中国", "M2", "CPI", "PPI", "社融", "贷款", "LPR", "人民币", "上期所"]):
                continue
            baidu_count += 1
        filtered.append(n)

    header = f"""# 晚间情报汇总 | {TODAY}
> 最后更新: {now_str} | 累计: {len(all_news)}条 | 新增: {new_count}条

"""

    if hot_stocks:
        header += f"""
## 🔥 热门股票
{', '.join(hot_stocks)}

"""

    header += "## 📰 最新要闻\n\n"
    news_md = ""
    for n in filtered[:80]:
        news_md += f"- [{n['time']}] 【{n['source']}】 {n['title']}\n"

    # 统计
    sources = {}
    for n in all_news:
        sources[n["source"]] = sources.get(n["source"], 0) + 1
    stats = "\n## 📈 新闻源统计\n\n" + "\n".join(f"| {s} | {c}条 |" for s, c in sorted(sources.items(), key=lambda x: -x[1]))

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(header + news_md + stats)

    print(f"  保存: {md_path} (累计{len(all_news)}条, 新增{new_count}条)")
    return md_path


def load_cache():
    """加载当日新闻缓存"""
    cache_file = os.path.join(OUTPUT_DIR, f"{TODAY}-cache.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []


def save_cache(news):
    """保存当日新闻缓存"""
    cache_file = os.path.join(OUTPUT_DIR, f"{TODAY}-cache.json")
    # 只保留最新的200条
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(news[-200:], f, ensure_ascii=False)

def generate_final_report():
    """生成最终版隔夜报告"""
    md_path = os.path.join(OUTPUT_DIR, f"{TODAY}-晚间情报.md")

    # 汇总当日所有新闻
    print("\n=== 生成隔夜终版 ===")
    news = collect_all_news()
    hot = fetch_hot_stocks()

    save_news_md(news, hot, mode="final")

    # 统计
    sources_count = {}
    for n in news:
        s = n["source"]
        sources_count[s] = sources_count.get(s, 0) + 1

    print(f"\n  新闻源统计:")
    for s, c in sorted(sources_count.items(), key=lambda x: -x[1]):
        print(f"    {s}: {c}条")

    # 高频关键词
    all_text = " ".join([n["title"] for n in news])
    keywords = re.findall(r'(半导体|芯片|AI|新能源|光伏|锂电|机器人|医药|军工|地产|降息|加息|央行|政策|关税|贸易|监管|IPO|退市|涨停|跌停|稀土|算力|大模型|自动驾驶|低空|固态电池|储能)', all_text)
    if keywords:
        from collections import Counter
        top_kw = Counter(keywords).most_common(10)
        print(f"\n  高频关键词: {', '.join(f'{k}({v})' for k,v in top_kw)}")

    return md_path

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--update', action='store_true', help='增量更新')
    parser.add_argument('--final', action='store_true', help='隔夜终版')
    parser.add_argument('--once', action='store_true', help='单次收集')
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.final:
        generate_final_report()
    elif args.update:
        news = collect_all_news()
        hot = fetch_hot_stocks()
        save_news_md(news, hot, mode="update")
    else:
        # 默认：单次收集
        news = collect_all_news()
        hot = fetch_hot_stocks()
        save_news_md(news, hot, mode="update")

if __name__ == "__main__":
    main()
