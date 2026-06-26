# -*- coding: utf-8 -*-
"""
掘金研报挖掘 v4.0 —— 晚间复盘素材（线程池加速）
用法:
    python research_report.py              # 拉近3天研报
    python research_report.py --days 5     # 近5天
    python research_report.py --top 50     # 只扫成交额前50名

思路:
    - 不是逐只翻20只自选股，而是扫描全市场有交易量的票
    - 遇到有研报的就挖出来，按主题/行业归档
    - 晚间掘金时按"新研报→行业→标的"逐层展开讨论
"""
import sys, os, json, re
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "每日新闻")
CACHE_DIR = os.path.join(OUTPUT_DIR, "report_cache")
NOW = datetime.now()
TODAY = NOW.strftime("%Y-%m-%d")

# ===== 主题关键词 =====
THEME_KW = {
    "AI与算力": ["AI", "人工智能", "大模型", "算力", "GPU", "芯片", "光模块", "CPO",
                 "数据中心", "液冷", "HBM", "先进封装", "Chiplet", "CoWoS", "豆包",
                 "智能体", "服务器", "PCB", "寒武纪", "海光"],
    "半导体":   ["半导体", "光刻", "晶圆", "封测", "存储", "设备", "EDA", "RISC-V",
                 "碳化硅", "氮化镓", "北方华创", "中微"],
    "新能源":   ["光伏", "储能", "锂电", "固态电池", "风电", "氢能", "钠离子",
                 "钙钛矿", "逆变器", "组件", "硅料", "宁德", "隆基", "阳光"],
    "机器人":   ["机器人", "人形", "具身智能", "减速器", "伺服", "传感器", "灵巧手"],
    "低空经济": ["低空", "eVTOL", "飞行汽车", "无人机", "空管"],
    "智能驾驶": ["自动驾驶", "智能驾驶", "激光雷达", "毫米波", "域控制", "车路云"],
    "稀土有色": ["稀土", "永磁", "钨", "铜", "铝", "黄金", "白银", "锂矿", "钴"],
    "军工航天": ["军工", "航天", "卫星", "导弹", "军机", "舰船"],
    "消费医药": ["消费", "白酒", "食品", "家电", "创新药", "CXO", "医疗器械"],
    "电力能源": ["电力", "火电", "水电", "核电", "绿电", "电网", "特高压"],
    "化工材料": ["化工", "新材料", "催化", "膜材料"],
    "通信5G":   ["5G", "6G", "通信", "光纤", "基站", "卫星互联网"],
    "金融地产": ["银行", "券商", "保险", "地产", "REITs"],
}

TIER1 = ["中信", "中金", "天风", "华泰", "国泰君安", "申万", "海通", "中信建投",
         "招商证券", "广发", "国信", "光大", "安信", "兴业", "东方证券", "国金",
         "方正", "长江", "国盛", "民生", "浙商"]


def _f(val):
    try: return float(val)
    except: return None


# ====================================================================
# 获取待扫描的股票池
# ====================================================================

def get_active_stocks(top_n=80):
    """从东方财富获取今日成交额最大的N只股票（这些才有交易价值）"""
    import urllib.request
    stocks = []
    pages = (top_n + 49) // 50
    for page in range(1, pages + 1):
        try:
            url = (
                "https://push2.eastmoney.com/api/qt/clist/get?"
                f"cb=&fid=f8&po=1&pz=50&pn={page}&np=1&fltt=2&invt=2"
                "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f8"
            )
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = (data.get("data") or {}).get("diff") or []
            for item in items:
                code = item.get("f12", "")
                name = item.get("f14", "")
                if code and name:
                    stocks.append({"code": code, "name": name})
        except Exception as e:
            print(f"  stock list page {page}: {e}")
    return stocks[:top_n]


# ====================================================================
# 报告拉取（单只）+ 缓存
# ====================================================================

def fetch_one(code):
    """拉取单只个股全部研报"""
    import akshare as ak
    try:
        df = ak.stock_research_report_em(symbol=code)
        if df is None or len(df) == 0:
            return code, []
        reports = []
        for _, row in df.iterrows():
            try:
                d = row.iloc[14]
                pub_date = d.strftime("%Y-%m-%d") if hasattr(d, 'strftime') else str(d)[:10]
                reports.append({
                    "date": pub_date,
                    "org": str(row.iloc[5]),
                    "title": str(row.iloc[3]),
                    "rating": str(row.iloc[4]),
                    "eps_2026": _f(row.iloc[7]),
                    "pe_2026": _f(row.iloc[8]),
                    "eps_2027": _f(row.iloc[9]),
                    "pe_2027": _f(row.iloc[10]),
                })
            except:
                continue
        return code, reports
    except Exception:
        return code, []


def scan_stocks(stock_list, days=3, threads=12):
    """线程池批量扫描，返回近N天的研报"""
    cutoff = (NOW - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = []
    all_data = {}
    total = len(stock_list)

    print(f"  [扫描] {total}只股票, {threads}线程...")
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(fetch_one, s["code"]): s for s in stock_list}
        done = 0
        for future in as_completed(futures):
            done += 1
            s = futures[future]
            try:
                code, reports = future.result()
            except:
                continue
            all_data[code] = {
                "name": s["name"],
                "total": len(reports),
                "reports": reports,
            }
            for r in reports:
                if r["date"] >= cutoff:
                    r["code"] = code
                    r["stock_name"] = s["name"]
                    recent.append(r)
            if done % 20 == 0:
                print(f"  ... {done}/{total} 命中{len(recent)}篇")

    print(f"  完成: {total}只 命中{len(recent)}篇研报（近{days}天）")
    return recent, all_data


# ====================================================================
# 分类
# ====================================================================

def classify(r):
    title = r.get("title", "")
    tags = [t for t, kws in THEME_KW.items() if any(kw in title for kw in kws)]
    return tags if tags else ["综合"]


def tier(org):
    return 1 if any(t in str(org) for t in TIER1) else 2


# ====================================================================
# 生成素材
# ====================================================================

def generate(recent, all_data, days):
    md_path = os.path.join(OUTPUT_DIR, f"{TODAY}-掘金素材.md")

    # 按主题分桶
    tb = defaultdict(list)
    for r in recent:
        for t in classify(r):
            tb[t].append(r)

    t1_reports = [r for r in recent if tier(r["org"]) == 1]

    lines = []
    lines.append(f"# 掘金素材 | {TODAY} 晚间复盘")
    lines.append(f"> 扫描范围: {len(all_data)}只活跃股 | 近{days}天命中{len(recent)}篇 | T1:{len(t1_reports)}篇")
    lines.append("")

    # ---- 热点预览 ----
    lines.append("## 热点概览")
    lines.append("")
    theme_order = sorted(tb.items(), key=lambda x: -len(x[1]))
    for theme, reps in theme_order:
        if theme == "综合": continue
        t1c = sum(1 for r in reps if tier(r["org"]) == 1)
        t1m = f" T1:{t1c}" if t1c else ""
        stocks = list(set(r["code"] for r in reps))
        lines.append(f"- **{theme}**: {len(reps)}篇{t1m} | 涉及{len(stocks)}只标的")
    lines.append("")

    # ---- 按主题详细展开 ----
    lines.append("## 逐主题研报")
    lines.append("")

    for theme, reps in theme_order:
        if theme == "综合": continue
        t1c = sum(1 for r in reps if tier(r["org"]) == 1)
        t1m = f" [T1:{t1c}]" if t1c else ""
        lines.append(f"### {theme} {t1m}")
        lines.append("")

        # T1在前，日期倒序
        reps_sorted = sorted(reps, key=lambda r: (tier(r["org"]), r["date"]), reverse=False)
        reps_sorted.sort(key=lambda r: r["date"], reverse=True)

        for r in reps_sorted[:10]:
            t1 = "**[T1]** " if tier(r["org"]) == 1 else ""
            lines.append(f"- {t1}[{r['date']}] {r['org']} | {r['stock_name']}({r['code']}) | {r.get('rating','')}")
            lines.append(f"  {r['title'][:90]}")
            if r.get("eps_2026"):
                eps = f"EPS26:{r['eps_2026']:.3f}" + (f" PE:{r['pe_2026']:.1f}x" if r.get('pe_2026') else "")
                lines.append(f"  {eps}")
        if len(reps) > 10:
            lines.append(f"  (...{len(reps)-10}篇省略)")
        lines.append("")

    # ---- 一线机构动向 ----
    if t1_reports:
        lines.append("## 一线机构最新动向")
        lines.append("")
        for r in sorted(t1_reports, key=lambda r: r["date"], reverse=True)[:20]:
            lines.append(f"- [{r['date']}] **{r['org']}** → {r['stock_name']}({r['code']}) | {r['title'][:70]}")
        lines.append("")

    # ---- 潜在机会因子 ----
    lines.append("## 潜在机会因子")
    lines.append("")
    lines.append("> 研报中反复出现的关键词，按出现频率排列，逐一讨论是否有交易机会。")
    lines.append("")

    # 找出现>=2次的细分关键词
    kw_hit = defaultdict(list)
    for r in recent:
        for theme, kws in THEME_KW.items():
            for kw in kws:
                if kw in r["title"]:
                    kw_hit[(theme, kw)].append(r)

    opportunities = [(k, rs) for k, rs in kw_hit.items() if len(rs) >= 2]
    opportunities.sort(key=lambda x: (-len(x[1]), -sum(1 for r in x[1] if tier(r["org"]) == 1)))

    for idx, ((theme, kw), reps) in enumerate(opportunities[:15], 1):
        t1c = sum(1 for r in reps if tier(r["org"]) == 1)
        t1m = f" T1:{t1c}" if t1c else ""
        stocks = list(set(r["code"] for r in reps))
        lines.append(f"{idx}. **[{theme}] {kw}** ({len(reps)}篇{t1m})")
        lines.append(f"   标的: {', '.join(stocks[:6])}")
        lines.append("")

    # ---- 盈利趋势 ----
    lines.append("## 盈利预测变动（有研报覆盖的票）")
    lines.append("")
    lines.append("| 股票 | 研报数 | 最新EPS | EPS趋势 | 最新机构 | 评级 |")
    lines.append("|------|--------|---------|---------|----------|------|")

    covered = [(c, d) for c, d in all_data.items() if d["total"] > 0 and d["reports"]]
    covered.sort(key=lambda x: -len(x[1]["reports"]))

    for code, info in covered[:30]:
        name = info["name"]
        reps = sorted(info["reports"], key=lambda r: r["date"], reverse=True)
        latest = reps[0]
        eps_str = f"{latest['eps_2026']:.3f}" if latest.get("eps_2026") else "-"

        eps_vals = [r["eps_2026"] for r in reps if r.get("eps_2026") and r["eps_2026"] > 0]
        if len(eps_vals) >= 2:
            delta = (eps_vals[0] - eps_vals[-1]) / eps_vals[-1] * 100
            eps_dir = f"上修+{delta:.0f}%" if delta > 10 else (f"下修{delta:.0f}%" if delta < -10 else "平稳")
        else:
            eps_dir = "-"

        lines.append(f"| {name}({code}) | {len(reps)} | {eps_str} | {eps_dir} | {latest['org']} | {latest.get('rating','-')} |")
    lines.append("")

    # ---- 讨论区 ----
    lines.append("## 讨论记录")
    lines.append("")
    lines.append("| 方向 | 逻辑链条 | 标的 | 优先级 | 备注 |")
    lines.append("|------|----------|------|--------|------|")
    lines.append("| _(待讨论)_ | | | | |")
    lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return md_path


# ====================================================================

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--top", type=int, default=80, help="扫描成交额前N只")
    p.add_argument("--threads", type=int, default=12)
    args = p.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"\n{'='*55}")
    print(f"  掘金素材 | 近{args.days}天 | 成交额TOP{args.top} | {NOW.strftime('%m-%d %H:%M')}")
    print(f"{'='*55}")

    # 获取活跃股票池
    print("\n  [池子] 获取成交额排名...")
    stocks = get_active_stocks(args.top)
    print(f"  获取: {len(stocks)}只")

    # 线程池扫描
    recent, all_data = scan_stocks(stocks, days=args.days, threads=args.threads)

    # 主题分布
    theme_cnt = defaultdict(int)
    for r in recent:
        for t in classify(r):
            theme_cnt[t] += 1

    print(f"\n  [主题分布]")
    for t, c in sorted(theme_cnt.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}篇")

    # 生成
    md_path = generate(recent, all_data, args.days)
    print(f"\n  [OK] {md_path}")


if __name__ == "__main__":
    main()
