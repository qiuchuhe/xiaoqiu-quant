# -*- coding: utf-8 -*-
"""
机构观点提取器 —— 从晚间情报中识别机构研报/观点
思路: 财经新闻里大量"中信证券：xxx""天风证券认为xxx"本身就是研报摘要
      不需要单独拉研报，从已收集的新闻中提取机构观点即可

用法:
    python extract_views.py              # 读取当日晚间情报，输出机构观点
    python extract_views.py --date 2026-06-22  # 指定日期

输出: 每日新闻/{日期}-机构观点.md
"""
import os, re, sys
from datetime import datetime
from collections import defaultdict

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "每日新闻")
NOW = datetime.now()
TODAY = NOW.strftime("%Y-%m-%d")

# ===== 机构匹配模式 =====
# 格式: (正则, 提取机构名的方式)
INSTITUTION_PATTERNS = [
    # 核心：券商+"研报/评级/目标价/看好/上调"等研究行为词
    # "中信证券：半导体拐点"  "天风证券认为xxx"  "华泰证券给予买入评级"
    (r'(高盛|摩根士丹利|摩根大通|花旗|瑞银|美银|德银|汇丰|野村|瑞信|巴克莱|贝莱德|桥水|中金公司|中信证券|中信建投|天风证券|华泰证券|国泰君安|申万宏源|海通证券|招商证券|广发证券|国信证券|光大证券|安信证券|兴业证券|东方证券|国金证券|方正证券|长江证券|国盛证券|民生证券|浙商证券|华创证券|国海证券|东吴证券|华安证券|西南证券|华鑫证券|中邮证券|国元证券|东兴证券|太平洋证券|华龙证券|开源证券|诚通证券|华源证券|中航证券)', 1),
    # 通用模式：xx证券/xx研究 + 研究行为词
    (r'([一-龥]{2,6}证券)[：:\s]*(?:认为|指出|表示|称|发布|看好|看空|给予|上调|下调|维持|重申|推荐|深度|首覆)', 1),
    (r'([一-龥]{2,6}(?:研究|研究院|研究所))[：:\s]*(?:认为|指出|表示|称|发布|看好|看空)', 1),
    # "据xx证券研报"
    (r'据([一-龥]{2,8}证券)研报', 1),
]

TIER1_ORGS = ["中信证券", "中金公司", "天风证券", "华泰证券", "国泰君安", "申万宏源",
              "海通证券", "中信建投", "招商证券", "广发证券", "国信证券", "光大证券",
              "安信证券", "兴业证券", "东方证券", "国金证券", "方正证券", "长江证券",
              "国盛证券", "民生证券", "浙商证券", "高盛", "摩根", "花旗", "瑞银", "美银"]

# 利好/利空判断词
# 必须是研究行为词 —— 过滤掉\"xx证券换帅\"\"xx银行发债\"这类非研报内容
RESEARCH_ACTION_WORDS = [
    "评级", "目标价", "研报", "推荐", "首覆", "深度报告",
    "看好", "看空", "上调", "下调", "给予", "维持", "重申",
    "买入", "增持", "减持", "卖出", "超配", "低配",
    "拐点", "反转", "超预期", "景气", "复苏",
    "EPS", "盈利预测", "估值", "PE",
]

BULLISH_WORDS = ["看好", "上调", "买入", "增持", "超配", "拐点", "反转", "超预期",
                 "加速", "突破", "放量", "景气", "机会", "推荐", "强烈推荐", "首覆"]
BEARISH_WORDS = ["看空", "下调", "减持", "卖出", "低配", "谨慎", "风险", "压力",
                 "放缓", "下行", "过剩", "降价", "警惕", "回避"]


def extract_from_markdown(md_path):
    """从晚间情报markdown中提取机构观点"""
    if not os.path.exists(md_path):
        print(f"  情报文件不存在: {md_path}")
        return []

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    views = []
    lines = content.split("\n")

    for line in lines:
        line = line.strip()
        if not line or len(line) < 15:
            continue

        # 跳过非新闻行（标题、表格等）
        if line.startswith("#") or line.startswith("|") or line.startswith(">"):
            continue

        # 尝试匹配机构
        for pattern, group_idx in INSTITUTION_PATTERNS:
            m = re.search(pattern, line)
            if m:
                org = m.group(group_idx)
                # 清理机构名
                org = re.sub(r'[：:，。\s]', '', org)

                # 质量过滤：必须含研究行为词，排除"换帅""发债""被调查"等非研报内容
                if not any(w in line for w in RESEARCH_ACTION_WORDS):
                    break

                # 判断方向
                direction = "neutral"
                if any(w in line for w in BULLISH_WORDS):
                    direction = "bullish"
                if any(w in line for w in BEARISH_WORDS):
                    direction = "bearish"

                # 提取提到的股票
                stocks = re.findall(r'([一-龥]{2,4}(?:股份|科技|集团|控股|电子|医疗|能源|银行|保险|证券|汽车|通信|传媒|锂业|钨业|铜业|铝业|光电|医药|生物|化工|材料|电力))', line)
                stock_codes = re.findall(r'[\(（](\d{6})[\)）]', line)

                # 提取行业/主题
                themes = re.findall(r'(半导体|AI|人工智能|大模型|算力|芯片|光模块|光伏|储能|锂电|机器人|低空|军工|创新药|消费|电力|化工|稀土|有色|黄金|5G|通信|自动驾驶|固态电池|人形机器人|具身智能|先进封装)', line)

                views.append({
                    "org": org,
                    "tier": 1 if any(t in org for t in TIER1_ORGS) else 2,
                    "direction": direction,
                    "stocks": list(set(stocks))[:3],
                    "stock_codes": list(set(stock_codes))[:3],
                    "themes": list(set(themes))[:3],
                    "text": line[:120],
                })
                break  # 一行只匹配一个机构

    # 去重（同一机构+相似文本）
    seen = set()
    unique = []
    for v in views:
        key = (v["org"], v["text"][:40])
        if key not in seen:
            seen.add(key)
            unique.append(v)

    return unique


def generate_report(views, target_date):
    """生成机构观点汇总"""
    md_path = os.path.join(OUTPUT_DIR, f"{target_date}-机构观点.md")

    if not views:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# 机构观点 | {target_date}\n\n> 未提取到机构观点\n")
        return md_path

    # 按机构分组
    org_views = defaultdict(list)
    for v in views:
        org_views[v["org"]].append(v)

    # 按方向分
    bullish = [v for v in views if v["direction"] == "bullish"]
    bearish = [v for v in views if v["direction"] == "bearish"]
    neutral = [v for v in views if v["direction"] == "neutral"]
    t1 = [v for v in views if v["tier"] == 1]

    lines = []
    lines.append(f"# 机构观点 | {target_date}")
    lines.append(f"> 从晚间情报提取: {len(views)}条机构观点")
    lines.append(f"> 一线机构: {len(t1)}条 | 偏多: {len(bullish)} | 偏空: {len(bearish)} | 中性: {len(neutral)}")
    lines.append("")

    # ---- 机构关注方向 ----
    lines.append("## 机构在讨论什么")
    lines.append("")

    # 按主题聚拢
    theme_views = defaultdict(list)
    for v in views:
        if v["themes"]:
            for t in v["themes"]:
                theme_views[t].append(v)
        else:
            theme_views["其他"].append(v)

    for theme, vlist in sorted(theme_views.items(), key=lambda x: -len(x[1])):
        t1c = sum(1 for v in vlist if v["tier"] == 1)
        t1m = f" (T1:{t1c})" if t1c else ""
        buoy = sum(1 for v in vlist if v["direction"] == "bullish")
        bear = sum(1 for v in vlist if v["direction"] == "bearish")
        dir_m = f" 偏多{buoy}/偏空{bear}"
        lines.append(f"**{theme}**: {len(vlist)}条{t1m}{dir_m}")
    lines.append("")

    # ---- 详细列表 ----
    lines.append("## 逐条观点")
    lines.append("")

    # T1优先，方向分色
    views_sorted = sorted(views, key=lambda v: (v["tier"], v["direction"] != "bullish"))

    for v in views_sorted:
        t1_tag = "[T1]" if v["tier"] == 1 else "[T2]"
        dir_tag = {"bullish": "[多]", "bearish": "[空]", "neutral": ""}[v["direction"]]

        extra = []
        if v["stocks"]:
            extra.append(f"标的: {'/'.join(v['stocks'])}")
        if v["themes"]:
            extra.append(f"主题: {'/'.join(v['themes'])}")

        lines.append(f"- {t1_tag}{dir_tag} **{v['org']}**: {v['text']}")
        if extra:
            lines.append(f"  {' | '.join(extra)}")
    lines.append("")

    # ---- 机构情绪概览 ----
    lines.append("## 机构情绪")
    lines.append("")

    org_sentiment = defaultdict(lambda: {"bullish": 0, "bearish": 0, "neutral": 0})
    for v in views:
        org_sentiment[v["org"]][v["direction"]] += 1

    lines.append("| 机构 | 偏多 | 偏空 | 中性 |")
    lines.append("|------|------|------|------|")
    for org in sorted(org_sentiment.keys(), key=lambda o: -(org_sentiment[o]["bullish"] + org_sentiment[o]["bearish"])):
        s = org_sentiment[org]
        lines.append(f"| {org} | {s['bullish']} | {s['bearish']} | {s['neutral']} |")
    lines.append("")

    # ---- 讨论区 ----
    lines.append("## 讨论")
    lines.append("")
    lines.append("> 哪些机构观点值得重视？哪些可以忽略？")
    lines.append("")
    lines.append("- _(待讨论)_")
    lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return md_path


def fetch_research_news():
    """专门抓取研报摘要类资讯"""
    import urllib.request
    views = []
    try:
        # 东方财富——资讯频道，关键词过滤机构观点
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get?"
            "cb=&fid=ctime&po=1&pz=30&pn=1&np=1&fltt=2&invt=2"
            "&fs=m:0+t:10&fields=f14,f20,f21,f22"
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://finance.eastmoney.com/"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = (data.get("data") or {}).get("diff") or []
        for item in items:
            title = item.get("f14", "")
            pub_time = str(item.get("f20", ""))[:10]
            org_name = item.get("f21", "")
            # 只保留匹配到机构的
            if not any(re.search(p, title) for p, _ in INSTITUTION_PATTERNS):
                continue
            matched_org = None
            for pattern, group_idx in INSTITUTION_PATTERNS:
                m = re.search(pattern, title)
                if m:
                    matched_org = re.sub(r'[：:，。\s]', '', m.group(group_idx))
                    break
            direction = "neutral"
            if any(w in title for w in BULLISH_WORDS):
                direction = "bullish"
            if any(w in title for w in BEARISH_WORDS):
                direction = "bearish"
            stocks = re.findall(r'([一-龥]{2,4}(?:股份|科技|集团|控股|电子|医疗|能源|银行|保险|证券|汽车|通信|传媒|锂业|钨业|铜业|铝业|光电|医药|生物|化工|材料|电力))', title)
            stock_codes = re.findall(r'[\(（](\d{6})[\)）]', title)
            themes = re.findall(r'(半导体|AI|人工智能|大模型|算力|芯片|光模块|光伏|储能|锂电|机器人|低空|军工|创新药|消费|电力|化工|稀土|有色|黄金|5G|通信|自动驾驶|固态电池|人形机器人|先进封装)', title)
            views.append({
                "org": matched_org or org_name or "机构",
                "tier": 1 if (matched_org and any(t in matched_org for t in TIER1_ORGS)) else 2,
                "direction": direction,
                "stocks": list(set(stocks))[:3],
                "stock_codes": list(set(stock_codes))[:3],
                "themes": list(set(themes))[:3],
                "text": f"[{pub_time}] {title[:120]}",
            })
    except Exception as e:
        print(f"  资讯频道: {e}")
    return views


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", type=str, default=TODAY)
    p.add_argument("--fetch", action="store_true", help="主动拉取研报资讯")
    args = p.parse_args()

    all_views = []

    # 1. 从晚间情报提取
    md_input = os.path.join(OUTPUT_DIR, f"{args.date}-晚间情报.md")
    print(f"  [提取] 晚间情报中机构观点...")
    news_views = extract_from_markdown(md_input)
    all_views.extend(news_views)
    print(f"  从情报提取: {len(news_views)}条")

    # 2. （可选）主动搜索研报资讯
    if args.fetch:
        print(f"  [搜索] 东方财富研报资讯...")
        research_news = fetch_research_news()
        all_views.extend(research_news)
        print(f"  主动搜索: {len(research_news)}条")

    # 去重
    seen = set()
    unique = []
    for v in all_views:
        key = (v["org"], v["text"][:50])
        if key not in seen:
            seen.add(key)
            unique.append(v)
    all_views = unique

    t1 = [v for v in all_views if v["tier"] == 1]
    bullish = [v for v in all_views if v["direction"] == "bullish"]
    bearish = [v for v in all_views if v["direction"] == "bearish"]

    print(f"  合计: {len(all_views)}条 | 一线: {len(t1)} | 偏多: {len(bullish)} | 偏空: {len(bearish)}")

    out = generate_report(all_views, args.date)
    print(f"  -> {out}")


if __name__ == "__main__":
    main()
