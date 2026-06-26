# -*- coding: utf-8 -*-
"""
当晚掘金 —— 一站式晚间情报处理
用法: python nightly_dig.py

流程:
    1. 收集晚间情报 (market_intel_v2.py)
    2. 提取机构观点 (extract_views.py)
    3. 策略扫描 (scanner.py)
    4. 汇总生成当晚掘金报告

定时: 每晚22:00自动执行
"""
import subprocess, os, sys, json, re
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, "每日新闻")
NOW = datetime.now()
TODAY = NOW.strftime("%Y-%m-%d")
TOMORROW = (NOW + timedelta(days=1)).strftime("%Y-%m-%d")
WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


def run(cmd, cwd=None, timeout=120):
    """运行命令并返回输出"""
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace"
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return f"[超时] {cmd}"
    except Exception as e:
        return f"[错误] {e}"


def step1_collect_intel():
    """步骤1: 收集晚间情报"""
    print("\n[1/4] 晚间情报收集...")
    out = run("python market_intel_v2.py", cwd=BASE, timeout=120)
    # 检查输出文件
    intel_path = os.path.join(OUTPUT, f"{TODAY}-晚间情报.md")
    if os.path.exists(intel_path):
        size = os.path.getsize(intel_path)
        print(f"  OK: {intel_path} ({size//1024}KB)")
        return intel_path
    else:
        print(f"  ERR: 情报文件未生成")
        return None


def step2_extract_views():
    """步骤2: 提取机构观点"""
    print("\n[2/4] 机构观点提取...")
    out = run(f"python extract_views.py --date {TODAY}", cwd=BASE, timeout=60)
    views_path = os.path.join(OUTPUT, f"{TODAY}-机构观点.md")
    if os.path.exists(views_path):
        # 读取统计
        with open(views_path, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"从晚间情报提取: (\d+)条", content)
        count = m.group(1) if m else "?"
        print(f"  OK: 提取{count}条观点")
        return views_path
    else:
        print(f"  WARN: 无机构观点（当日情报可能不含研报类内容）")
        return None


def step3_scan_strategy():
    """步骤3: 策略扫描"""
    print("\n[3/4] 策略1扫描...")
    strategy_dir = os.path.join(os.path.dirname(BASE), "策略量化", "策略1")
    out = run("python scanner.py --once", cwd=strategy_dir, timeout=120)

    result_path = os.path.join(strategy_dir, "策略一_result.json")
    signals = []
    if os.path.exists(result_path):
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            signals = data.get("candidates", [])
            # 只统计有买点的
            signals = [s for s in signals if s.get('buy_signals')]
            print(f"  OK: {len(signals)}个信号")
            for s in signals:
                print(f"    {s.get('name','')}({s.get('code','')}) {s.get('buy_type','')} {s.get('reason','')[:50]}")
        except:
            print(f"  WARN: 结果解析失败")
    else:
        print(f"  WARN: 策略结果文件不存在")

    # 持仓巡检
    print("\n  持仓巡检...")
    monitor_dir = os.path.join(os.path.dirname(BASE), "量化")
    out = run("python monitor.py --once", cwd=monitor_dir, timeout=60)

    pos_path = os.path.join(monitor_dir, ".position.json")
    positions = {}
    if os.path.exists(pos_path):
        try:
            with open(pos_path, "r", encoding="utf-8") as f:
                positions = json.load(f)
            holdings = positions.get("holdings", [])
            print(f"  OK: {len(holdings)}只持仓")
        except:
            pass

    return signals, positions


def step4_generate_digest(intel_path, views_path, signals, positions):
    """步骤4: 生成当晚掘金报告"""
    print("\n[4/4] 生成掘金报告...")

    digest_path = os.path.join(OUTPUT, f"{TODAY}-当晚掘金.md")
    tomorrow_wd = WEEKDAY_CN[(NOW + timedelta(days=1)).weekday()]

    lines = []
    lines.append(f"# 当晚掘金报告 | {TODAY}")
    lines.append(f"> 生成: {NOW.strftime('%H:%M')} | 明日: {TOMORROW} 周{tomorrow_wd}")
    lines.append("")

    # ====== 情报摘要 ======
    if intel_path and os.path.exists(intel_path):
        with open(intel_path, "r", encoding="utf-8") as f:
            intel = f.read()
        # 提取关键信息：前30条新闻标题
        titles = re.findall(r'- \[.*?\] (.*?)$', intel, re.MULTILINE)
        lines.append("## 一、今日情报速览")
        lines.append("")
        lines.append(f"共{len(titles)}条新闻，以下为最新30条：")
        lines.append("")
        for t in titles[:30]:
            lines.append(f"- {t[:100]}")
        lines.append("")
        lines.append(f"> 完整情报: [{TODAY}-晚间情报.md]({TODAY}-晚间情报.md)")
        lines.append("")

    # ====== 机构观点 ======
    lines.append("## 二、机构观点")
    lines.append("")
    if views_path and os.path.exists(views_path):
        with open(views_path, "r", encoding="utf-8") as f:
            views = f.read()
        m = re.search(r"从晚间情报提取: (\d+)条", views)
        count = int(m.group(1)) if m else 0
        if count > 0:
            # 提取逐条观点
            view_items = re.findall(r'- \[.*?\] \*\*(.*?)\*\*: (.*?)$', views, re.MULTILINE)
            # 按方向分类
            bullish = [v for v in view_items if any(w in v[1] for w in ["看好","上调","买入","增持","推荐","拐点","超预期"])]
            bearish = [v for v in view_items if any(w in v[1] for w in ["看空","下调","减持","卖出","谨慎","风险"])]

            if bullish:
                lines.append("### 偏多观点")
                for org, text in bullish:
                    lines.append(f"- **{org}**: {text[:100]}")
                lines.append("")
            if bearish:
                lines.append("### 偏空/谨慎观点")
                for org, text in bearish:
                    lines.append(f"- **{org}**: {text[:100]}")
                lines.append("")
            if not bullish and not bearish:
                lines.append(f"共{count}条机构观点，详见完整报告。")
                lines.append("")
        else:
            lines.append("> 今日暂无机构观点（情报中未检测到券商研报类内容）")
            lines.append("")
    else:
        lines.append("> 今日暂无机构观点")
        lines.append("")
    lines.append(f"> 完整: [{TODAY}-机构观点.md]({TODAY}-机构观点.md)")
    lines.append("")

    # ====== 策略信号 ======
    lines.append("## 三、策略1信号")
    lines.append("")
    if signals:
        lines.append("| 股票 | 代码 | 买点 | 现价 | 量比 | 理由 |")
        lines.append("|------|------|------|------|------|------|")
        for s in signals:
            buy_types = '+'.join([sig.get('type','') for sig in s.get('buy_signals',[])])
            vol_r = s.get('vol_ratio', 0)
            reason_parts = [sig.get('detail','')[:60] for sig in s.get('buy_signals',[])]
            reason = ' | '.join(reason_parts)
            lines.append(f"| {s.get('name','')} | {s.get('code','')} | {buy_types} | {s.get('price','')} | {vol_r:.1f}x | {reason} |")
        lines.append("")
    else:
        lines.append("> 今日无信号触发")
        lines.append("")
    lines.append("")

    # ====== 持仓 ======
    lines.append("## 四、当前持仓")
    lines.append("")
    holdings = positions.get("holdings", [])
    if holdings:
        lines.append("| 标的 | 成本 | 数量 | 止损 | 止盈 |")
        lines.append("|------|------|------|------|------|")
        for h in holdings:
            lines.append(f"| {h.get('name','')}({h.get('code','')}) | {h.get('buy_price','')} | {h.get('shares','')}股 | {h.get('stop_loss','')} | {h.get('take_profit','')} |")

        cash_used = positions.get("cash_used", 0)
        cash_rem = positions.get("cash_remaining", 0)
        pnl = positions.get("realized_pnl", 0)
        lines.append("")
        lines.append(f"占用: {cash_used} | 剩余: {cash_rem} | 已实现盈亏: {pnl}")
    else:
        lines.append("> 空仓")
    lines.append("")

    # ====== 明日关注 ======
    lines.append("## 五、明日关注")
    lines.append("")
    lines.append("> 根据以上信息，标注明天需要关注的标的和方向")
    lines.append("")
    if signals:
        lines.append("| 优先级 | 标的/方向 | 逻辑 |")
        lines.append("|------|------|------|")
        for i, s in enumerate(signals):
            buy_types = '+'.join([sig.get('type','') for sig in s.get('buy_signals',[])])
            price = s.get('price', 0)
            logic = f"策略1买点{buy_types}，现价{price:.2f}，量比{s.get('vol_ratio',0):.1f}x"
            priority = '🔥高' if 'A_' in buy_types and 'B_' in buy_types else ('⭐中' if 'A_' in buy_types else '📌低')
            lines.append(f"| {priority} | {s.get('name','')}({s.get('code','')}) | {logic} |")
        lines.append("")
    else:
        lines.append("| 优先级 | 标的/方向 | 逻辑 |")
        lines.append("|------|------|------|")
        lines.append("| | | |")
        lines.append("")

    with open(digest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  OK: {digest_path}")
    return digest_path


# ====================================================================

def main():
    print(f"\n{'='*55}")
    print(f"  当晚掘金 | {TODAY} {NOW.strftime('%H:%M')}")
    print(f"  流程: 情报 → 机构观点 → 策略 → 汇总")
    print(f"{'='*55}")

    # Step 1
    intel_path = step1_collect_intel()

    # Step 2
    views_path = step2_extract_views()

    # Step 3
    signals, positions = step3_scan_strategy()

    # Step 4
    digest_path = step4_generate_digest(intel_path, views_path, signals, positions)

    print(f"\n{'='*55}")
    print(f"  掘金完成: {digest_path}")
    print(f"  明天早盘直接打开这个文件即可")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
