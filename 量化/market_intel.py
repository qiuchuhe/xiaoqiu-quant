# -*- coding: utf-8 -*-
"""盘后情报收集 —— 每日行业大事 + 板块表现 + 三大指数 → HTML报告"""
import urllib.request, json, re, os, sys
from datetime import datetime

# ── 配置 ──
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "每日新闻")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
TODAY_DISPLAY = NOW.strftime("%Y年%m月%d日")

# 重点行业板块 (腾讯代码 → 名称) —— 已验证有效代码
SECTORS = {
    "pt01801010": "农林牧渔",
    "pt01801015": "商业",
    "pt01801016": "种植业",
    "pt01801036": "钢铁",
    "pt01801050": "有色金属",
    "pt01801056": "能源金属",
    "pt01801072": "通信设备",
    "pt01801074": "专用设备",
    "pt01801077": "工程机械",
    "pt01801078": "自动化设备",
    "pt01801080": "电气设备",
    "pt01801081": "半导体",
    "pt01801082": "消费电子",
    "pt01801085": "电子元件",
    "pt01801093": "汽车零部件",
    "pt01801095": "乘用车",
    "pt01801101": "风电设备",
    "pt01801102": "光伏设备",
    "pt01801103": "IT服务",
    "pt01801104": "软件开发",
    "pt01801110": "家用电器",
    "pt01801120": "食品饮料",
    "pt01801125": "白酒",
    "pt01801127": "物流",
    "pt01801130": "纺织服饰",
    "pt01801150": "医药生物",
    "pt01801151": "化学制药",
    "pt01801153": "医疗器械",
    "pt01801155": "中药",
    "pt01801161": "电力",
    "pt01801170": "交通运输",
    "pt01801178": "银行",
    "pt01801180": "房地产",
    "pt01801193": "证券",
    "pt01801194": "保险",
}

# 华尔街见闻频道
WSCN_CHANNELS = [
    ("a-stock-channel", "A股要闻"),
    ("global-channel", "7x24快讯"),
    ("commodity-channel", "商品期货"),
]


def fetch_json(url, referer=None):
    """通用JSON抓取"""
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read())


def fetch_text(url, encoding="gbk"):
    """通用文本抓取"""
    headers = {"User-Agent": UA}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return resp.read().decode(encoding, errors="replace")


# ═══════════════════════════════════════════
# 1. 三大指数
# ═══════════════════════════════════════════
def get_indices():
    """获取上证/深证/创业板"""
    try:
        url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?"
               "fltt=2&invt=2&fields=f2,f3,f4,f12,f14,f6,f20"
               "&secids=1.000001,0.399001,0.399006")
        data = fetch_json(url, "https://finance.eastmoney.com/")
        items = data.get("data", {}).get("diff", [])
        result = {}
        for item in items:
            result[item["f14"]] = {
                "price": item["f2"],
                "pct": item["f3"],
                "change": item["f4"],
                "volume": item.get("f6", 0),
                "market_cap": item.get("f20", 0),
            }
        return result
    except Exception as e:
        print(f"  [!] 东财指数失败, 尝试腾讯备用: {e}")
        return get_indices_tencent()


def get_indices_tencent():
    """腾讯行情备用——获取三大指数"""
    try:
        codes = {"sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指"}
        url = f"http://qt.gtimg.cn/q={','.join(codes)}"
        raw = fetch_text(url, "gbk")
        result = {}
        for line in raw.strip().split(";\n"):
            m = re.search(r'="(.+)"', line.strip())
            if not m:
                continue
            f = m.group(1).split("~")
            if len(f) < 40:
                continue
            name = codes.get(f[2], f[1])
            price = float(f[3])
            preclose = float(f[4])
            pct = (price - preclose) / preclose * 100
            result[name] = {
                "price": price,
                "pct": round(pct, 2),
                "change": round(price - preclose, 2),
                "volume": float(f[6]) if f[6] else 0,
                "market_cap": 0,
            }
        return result
    except Exception as e:
        print(f"  [!] 腾讯指数也失败: {e}")
        return {}


# ═══════════════════════════════════════════
# 2. 行业板块涨跌
# ═══════════════════════════════════════════
def get_sectors():
    """获取行业板块涨跌"""
    if not SECTORS:
        return []

    codes = list(SECTORS.keys())
    results = []

    # 分批请求（每次最多20个）
    for i in range(0, len(codes), 20):
        batch = codes[i:i+20]
        try:
            url = f"http://qt.gtimg.cn/q={','.join(batch)}"
            raw = fetch_text(url, "gbk")
            for line in raw.strip().split(";\n"):
                m = re.search(r'="(.+)"', line.strip())
                if not m:
                    continue
                f = m.group(1).split("~")
                if len(f) < 10:
                    continue
                code = f[2]
                price = float(f[3]) if f[3] else 0
                preclose = float(f[4]) if f[4] else 0
                if preclose <= 0:
                    continue
                pct = (price - preclose) / preclose * 100
                results.append({
                    "code": code,
                    "name": SECTORS.get(code, f[1]),
                    "price": price,
                    "pct": round(pct, 2),
                    "volume": float(f[6]) if f[6] else 0,
                })
        except Exception as e:
            print(f"  [!] 板块数据失败 (batch {i}): {e}")

    results.sort(key=lambda x: x["pct"], reverse=True)
    return results


# ═══════════════════════════════════════════
# 3. 多源新闻聚合 (新浪宏观 + 华尔街见闻快讯)
# ═══════════════════════════════════════════
def get_sina_news(count=15):
    """获取新浪财经宏观新闻"""
    try:
        url = (f"https://feed.mix.sina.com.cn/api/roll/get?"
               f"pageid=153&lid=2509&k=&num={count}&page=1")
        data = fetch_json(url)
        items = data.get("result", {}).get("data", [])
        news = []
        for item in items:
            ts = int(item.get("ctime", 0))
            dt = datetime.fromtimestamp(ts).strftime("%H:%M")
            news.append({
                "time": dt,
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": "新浪宏观",
            })
        return news
    except Exception as e:
        print(f"  [!] 新浪新闻失败: {e}")
        return []


def get_wscn_news(channel="a-stock-channel", count=10):
    """获取华尔街见闻7x24快讯"""
    try:
        url = (f"https://api-one.wallstcn.com/apiv1/content/lives?"
               f"channel={channel}&limit={count}")
        data = fetch_json(url)
        items = data.get("data", {}).get("items", [])
        news = []
        for item in items:
            ts = item.get("display_time", 0)
            dt = datetime.fromtimestamp(ts).strftime("%H:%M")
            # 取纯文本内容，去掉HTML标签
            text = item.get("content_text", "")[:120]
            text = re.sub(r'<[^>]+>', '', text)
            ch_name = item.get("global_channel_name", "快讯")
            news.append({
                "time": dt,
                "title": text,
                "url": f"https://wallstreetcn.com/live/{item.get('id','')}",
                "source": f"华尔街见闻·{ch_name}",
            })
        return news
    except Exception as e:
        print(f"  [!] 华尔街见闻({channel})失败: {e}")
        return []


def get_news():
    """聚合所有新闻源"""
    all_news = []

    # 新浪宏观
    sina = get_sina_news(15)
    all_news.extend(sina)

    # 华尔街见闻 A股+全球
    for ch, label in WSCN_CHANNELS:
        wscn = get_wscn_news(ch, 8)
        all_news.extend(wscn)

    # 去重(简单按标题相似度)
    seen = set()
    deduped = []
    for n in all_news:
        key = n["title"][:30]
        if key not in seen:
            seen.add(key)
            deduped.append(n)

    # 按时间排序(倒序)
    deduped.sort(key=lambda x: x["time"], reverse=True)
    return deduped[:40]


# ═══════════════════════════════════════════
# 4. 市场总览摘要
# ═══════════════════════════════════════════
def build_summary(indices, sectors, news):
    """根据数据生成一句话总结"""
    parts = []

    # 指数概况
    up = sum(1 for v in indices.values() if v["pct"] > 0)
    down = sum(1 for v in indices.values() if v["pct"] < 0)
    if down > up:
        parts.append("三大指数全线下跌")
    elif up > down:
        parts.append("三大指数全线上涨")
    else:
        parts.append("三大指数涨跌互现")

    # 板块概况
    if sectors:
        up_sectors = [s for s in sectors if s["pct"] > 0]
        down_sectors = [s for s in sectors if s["pct"] < 0]
        if up_sectors:
            parts.append(f"领涨: {', '.join(s['name'] for s in up_sectors[:3])}")
        if down_sectors:
            parts.append(f"领跌: {', '.join(s['name'] for s in down_sectors[:3])}")

    # 新闻关键词
    keywords = set()
    kw_pattern = re.compile(r'(降息|加息|央行|政策|制裁|关税|AI|芯片|新能源|光伏|锂电|机器人|医药|'
                           r'军工|地产|通胀|GDP|PMI|汇率|贸易|监管|IPO|退市|涨停|跌停)')
    for n in news[:15]:
        found = kw_pattern.findall(n["title"])
        keywords.update(found)
    if keywords:
        parts.append(f"热词: {'/'.join(list(keywords)[:5])}")

    return " | ".join(parts)


# ═══════════════════════════════════════════
# 5. 生成HTML报告
# ═══════════════════════════════════════════
def generate_html(indices, sectors, news, summary):
    """生成精美的HTML盘后简报"""

    # ── 指数卡片 ──
    index_cards = ""
    colors = {"上证指数": "#e63946", "深证成指": "#457b9d", "创业板指": "#2a9d8f"}
    for name in ["上证指数", "深证成指", "创业板指"]:
        v = indices.get(name)
        if not v:
            continue
        direction = "↑" if v["pct"] > 0 else ("↓" if v["pct"] < 0 else "→")
        color = colors.get(name, "#333")
        pct_color = "#d32f2f" if v["pct"] > 0 else ("#2e7d32" if v["pct"] < 0 else "#666")
        index_cards += f"""
        <div class="index-card">
            <div class="index-name">{name}</div>
            <div class="index-price">{v['price']:.2f}</div>
            <div class="index-change" style="color:{pct_color}">{direction} {v['pct']:+.2f}%</div>
            <div class="index-detail">成交额: {v['volume']/1e8:.0f}亿</div>
        </div>"""

    # ── 板块表格 ──
    sector_rows = ""
    for i, s in enumerate(sectors[:20]):
        pct_class = "up" if s["pct"] > 0 else ("down" if s["pct"] < 0 else "flat")
        pct_str = f"+{s['pct']:.2f}%" if s["pct"] > 0 else f"{s['pct']:.2f}%"
        sector_rows += f"""
        <tr class="{pct_class}">
            <td>{i+1}</td>
            <td>{s['name']}</td>
            <td class="num">{s['price']:.2f}</td>
            <td class="num pct">{pct_str}</td>
        </tr>"""

    # ── 新闻列表 ──
    news_items = ""
    for n in news[:20]:
        news_items += f"""
        <li><span class="news-time">[{n['time']}]</span><span class="news-source">[{n['source']}]</span> {n['title']}</li>"""

    # ── 下跌板块 ──
    down_sectors = [s for s in sectors if s["pct"] < 0]
    down_rows = ""
    for i, s in enumerate(down_sectors[:10]):
        down_rows += f"""
        <tr class="down">
            <td>{i+1}</td>
            <td>{s['name']}</td>
            <td class="num pct">{s['pct']:.2f}%</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>盘后简报 {TODAY_STR}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", sans-serif; background: #f5f6fa; color: #2d3436; padding: 20px; }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    h1 {{ text-align: center; font-size: 24px; margin-bottom: 5px; color: #1a1a2e; }}
    .subtitle {{ text-align: center; color: #636e72; font-size: 14px; margin-bottom: 20px; }}

    /* 概述条 */
    .summary-bar {{ background: linear-gradient(135deg, #1a1a2e, #16213e); color: #fff; padding: 14px 20px; border-radius: 10px; text-align: center; font-size: 15px; margin-bottom: 20px; line-height: 1.6; }}

    /* 指数卡片 */
    .index-row {{ display: flex; gap: 15px; margin-bottom: 20px; }}
    .index-card {{ flex: 1; background: #fff; border-radius: 10px; padding: 16px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    .index-name {{ font-size: 13px; color: #636e72; margin-bottom: 4px; }}
    .index-price {{ font-size: 26px; font-weight: 700; margin: 4px 0; }}
    .index-change {{ font-size: 16px; font-weight: 600; }}
    .index-detail {{ font-size: 11px; color: #999; margin-top: 4px; }}

    /* 板块表格 */
    .section-title {{ font-size: 18px; font-weight: 700; margin: 24px 0 12px 0; color: #1a1a2e; border-left: 4px solid #e63946; padding-left: 10px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 10px; }}
    th {{ background: #f8f9fa; padding: 10px 14px; text-align: left; font-size: 13px; color: #636e72; font-weight: 600; }}
    td {{ padding: 9px 14px; font-size: 14px; border-top: 1px solid #f1f2f6; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; font-family: "SF Mono", "Consolas", monospace; }}
    .pct {{ font-weight: 600; }}
    .up .pct {{ color: #d32f2f; }}
    .down .pct {{ color: #2e7d32; }}
    .flat .pct {{ color: #999; }}
    tr:hover {{ background: #f8f9ff; }}

    /* 新闻 */
    .news-list {{ background: #fff; border-radius: 10px; padding: 14px 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    .news-list li {{ padding: 7px 0; border-bottom: 1px solid #f5f5f5; font-size: 14px; line-height: 1.5; }}
    .news-list li:last-child {{ border-bottom: none; }}
    .news-time {{ color: #e63946; font-size: 12px; margin-right: 6px; font-family: "SF Mono", "Consolas", monospace; }}
    .news-source {{ color: #0984e3; font-size: 11px; margin-right: 6px; }}

    /* 双栏 */
    .two-col {{ display: flex; gap: 20px; }}
    .col {{ flex: 1; }}
    @media (max-width: 600px) {{ .two-col {{ flex-direction: column; }} .index-row {{ flex-direction: column; }} }}

    .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 30px; padding: 10px; }}
</style>
</head>
<body>
<div class="container">
    <h1>📊 盘后简报</h1>
    <div class="subtitle">{TODAY_DISPLAY} · {NOW.strftime('%A')} · 数据来源: 东方财富 / 新浪财经 / 腾讯行情</div>

    <div class="summary-bar">📌 {summary}</div>

    <div class="index-row">{index_cards}</div>

    <div class="two-col">
        <div class="col">
            <div class="section-title">🔥 涨幅榜 TOP20</div>
            <table>
                <tr><th>#</th><th>板块</th><th>指数</th><th>涨跌</th></tr>
                {sector_rows}
            </table>
        </div>
        <div class="col">
            <div class="section-title">📉 跌幅榜</div>
            <table>
                <tr><th>#</th><th>板块</th><th>涨跌</th></tr>
                {down_rows}
            </table>
        </div>
    </div>

    <div class="section-title">📰 今日宏观要闻</div>
    <ol class="news-list">{news_items}</ol>

    <div class="footer">
        盘后简报 {TODAY_STR} · 自动生成 · 数据仅供参考不构成投资建议
    </div>
</div>
</body>
</html>"""
    return html


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("  === 盘后情报收集 ===")
    print(f"  {TODAY_DISPLAY}  {NOW.strftime('%H:%M:%S')}")
    print("=" * 60)
    print()

    # 1. 三大指数
    print("[1/3] 获取三大指数...")
    indices = get_indices()
    for name, v in indices.items():
        direction = "↑" if v["pct"] > 0 else ("↓" if v["pct"] < 0 else "→")
        print(f"  {name}: {v['price']:.2f}  {direction} {v['pct']:+.2f}%")

    # 2. 行业板块
    print("\n[2/3] 获取行业板块...")
    sectors = get_sectors()
    if sectors:
        print(f"  共 {len(sectors)} 个板块")
        top3_up = [f"{s['name']}({s['pct']:+.1f}%)" for s in sectors[:3]]
        top3_down = [f"{s['name']}({s['pct']:+.1f}%)" for s in sectors[-3:]]
        print(f"  领涨TOP3: {', '.join(top3_up)}")
        print(f"  领跌TOP3: {', '.join(top3_down)}")
    else:
        print("  [!] 未获取到板块数据")

    # 3. 宏观要闻
    print("\n[3/3] 获取宏观要闻...")
    news = get_news()
    print(f"  共 {len(news)} 条")
    for n in news[:5]:
        print(f"  [{n['time']}] {n['title'][:60]}")

    # 生成摘要
    summary = build_summary(indices, sectors, news)
    print(f"\n  [*] {summary}")

    # 生成HTML
    html = generate_html(indices, sectors, news, summary)

    # 保存
    filename = f"{TODAY_STR}-盘后简报.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n  [OK] 报告已保存: 每日新闻/{filename}")
    print(f"     路径: {filepath}")
    print(f"     大小: {len(html):,} bytes")

    return filepath


if __name__ == "__main__":
    main()
