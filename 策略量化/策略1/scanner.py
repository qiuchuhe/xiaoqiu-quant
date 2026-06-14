# -*- coding: utf-8 -*-
"""
策略一：均线多头 + 温和放量 —— 扫描引擎
  · 盘后模式：python scanner.py           → 全量扫描
  · 盘中模式：python scanner.py --live    → 每5分钟扫描
  · 单次快扫：python scanner.py --once    → 只跑一次

数据源：腾讯财经（免费/国内直连/无需API Key）
"""

import sys, os, time, json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 引入小秋核心共享库
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from 小秋核心.utils import C, to_tx_code, to_raw_code
from 小秋核心.data import get_stock_list, get_quotes, get_kline
from 小秋核心.indicators import calc_ma, calc_vol_ratio

# ─── 路径 ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = BASE_DIR
CONCURRENT_WORKERS = 12

# ─── 配置 ───
from config import CONDITIONS, BUY_SIGNALS, SELL_SIGNALS, POSITION, DATA as CFG


# ═══════════════════════════════════════════
# 筛选逻辑
# ═══════════════════════════════════════════

def is_valid_board(code, name):
    """排除创业板/科创板/北证/ST"""
    raw = to_raw_code(code)
    for prefix in CONDITIONS["exclude_prefix"]:
        if raw.startswith(prefix):
            return False
    if CONDITIONS["exclude_st"] and ("ST" in name.upper() or "*ST" in name.upper()):
        return False
    return raw.startswith(("0", "2", "6", "9"))


def initial_filter(all_stocks):
    """第一轮：行情初筛（价格<20 + 换手5-10% + 非ST/创业板）"""
    valid_codes = {}
    for raw_code, name in all_stocks.items():
        raw = str(raw_code).zfill(6)
        if is_valid_board(raw, name):
            valid_codes[raw] = name

    if not valid_codes:
        print(f"  {C.Y}无有效标的{C.Z}")
        return []

    all_quotes = get_quotes(list(valid_codes.keys()), workers=CONCURRENT_WORKERS)

    candidates = []
    for q in all_quotes:
        code = q.get("code", "")
        price = q.get("price", 0)
        turnover = q.get("turnover", 0)
        name = valid_codes.get(code, q.get("name", ""))

        if price <= 0 or price >= CONDITIONS["price_max"]:
            continue
        if turnover < CONDITIONS["turnover_min"] or turnover > CONDITIONS["turnover_max"]:
            continue

        candidates.append({
            "code": code, "name": name, "price": price,
            "pct": q.get("pct", 0), "turnover": turnover,
            "volume": q.get("volume", 0), "open": q.get("open", 0),
            "high": q.get("high", 0), "low": q.get("low", 0),
            "preclose": q.get("preclose", 0),
        })
    return candidates


def deep_analyze(candidate):
    """第二轮：K线深度分析（均线多头+量比+买卖点）"""
    code = candidate["code"]
    kl = get_kline(code, days=CFG["kline_days"])
    if not kl or len(kl) < 35:
        return None

    closes = [k["close"] for k in kl]
    volumes = [k["volume"] for k in kl]
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)

    if None in (ma5[-1], ma10[-1], ma20[-1]):
        return None
    if not (ma5[-1] > ma10[-1] > ma20[-1]):
        return None

    vol_ratio = calc_vol_ratio(volumes, 5)
    if vol_ratio is None:
        return None
    if vol_ratio < CONDITIONS["vol_ratio_min"] or vol_ratio > CONDITIONS["vol_ratio_max"]:
        return None

    # 检测买点
    buy_signals = []
    close_today = closes[-1]
    open_today = kl[-1]["open"]

    # 买点A: 回调MA10不破 + 收阳
    if close_today >= ma10[-1] * 0.98 and close_today > open_today:
        buy_signals.append({
            "type": "A_pullback_ma10", "name": BUY_SIGNALS["A_pullback_ma10"]["name"],
            "detail": f"收盘{close_today:.2f}距MA10({ma10[-1]:.2f})仅{(close_today - ma10[-1]) / ma10[-1] * 100:+.1f}%，收阳确认",
        })

    # 买点B: 放量站稳MA5
    if close_today >= ma5[-1] and vol_ratio >= 1.5:
        buy_signals.append({
            "type": "B_breakout_ma5", "name": BUY_SIGNALS["B_breakout_ma5"]["name"],
            "detail": f"收盘{close_today:.2f}站稳MA5({ma5[-1]:.2f})，量比{vol_ratio:.1f}x",
        })

    return {
        **candidate,
        "ma5": round(ma5[-1], 2), "ma10": round(ma10[-1], 2), "ma20": round(ma20[-1], 2),
        "vol_ratio": round(vol_ratio, 2), "close": close_today, "buy_signals": buy_signals,
    }


# ═══════════════════════════════════════════
# 报告输出
# ═══════════════════════════════════════════

def print_console_report(results, mode="EOD"):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n{C.M}╔══════════════════════════════════════════════════════╗")
    print(f"║  📊 策略一：均线多头+温和放量  {'盘后扫描' if mode=='EOD' else '盘中快扫'}")
    print(f"║  时间: {now}                                          ║")
    print(f"╚══════════════════════════════════════════════════════╝{C.Z}\n")

    if not results:
        print(f"  {C.Y}⭕ 今日无符合条件的股票{C.Z}")
        print(f"  {C.D}条件: 股价<20 | MA5>10>20 | 换手5-10% | 量比1-10x{C.Z}\n")
        return

    with_signal = [r for r in results if r.get("buy_signals")]
    no_signal = [r for r in results if not r.get("buy_signals")]
    print(f"  {C.Y}初筛通过: {len(results)} 只  |  触发买点: {len(with_signal)} 只{C.Z}\n")

    if with_signal:
        print(f"  {C.R}━━━ 🔥 触发买入信号 ━━━{C.Z}\n")
        for i, r in enumerate(with_signal, 1):
            _print_one(i, r)

    if no_signal:
        print(f"  {C.D}━━━ 📋 符合条件但未触发买点 ━━━{C.Z}\n")
        for i, r in enumerate(no_signal, len(with_signal) + 1):
            _print_one(i, r)

    print(f"  {C.D}{'─'*70}{C.Z}")
    print(f"  {C.D}条件: 股价<{CONDITIONS['price_max']}元 | MA5>MA10>MA20 | 换手{CONDITIONS['turnover_min']}-{CONDITIONS['turnover_max']}% | 量比{CONDITIONS['vol_ratio_min']}-{CONDITIONS['vol_ratio_max']}x{C.Z}")
    print(f"  {C.D}买点A: 回调MA10不破+收阳 → 次日开盘买{C.Z}")
    print(f"  {C.D}买点B: 放量站稳MA5+量比≥1.5 → 次日开盘买{C.Z}")
    print(f"  {C.D}⚠️ 获利盘<80%需在同花顺人工核对筹码峰{C.Z}\n")


def _print_one(rank, r):
    signals = r.get("buy_signals", [])
    has = bool(signals)
    nc = C.R if has else C.D
    marker = "🔴" if has and any(s["type"] == "A_pullback_ma10" for s in signals) else ("🟡" if has else "  ")

    print(f"  {marker} {rank}. {nc}{r['name']}{C.Z} ({C.B}{r['code']}{C.Z})  ¥{r['price']:.2f}  "
          f"涨幅{C.R if r['pct']>0 else C.G}{r['pct']:+.2f}%{C.Z}")
    print(f"      MA5:{r['ma5']:.2f} > MA10:{r['ma10']:.2f} > MA20:{r['ma20']:.2f}  |  "
          f"换手:{r['turnover']:.1f}%  |  量比:{r['vol_ratio']:.2f}x")
    for sig in signals:
        sc = C.R if sig["type"] == "A_pullback_ma10" else C.Y
        print(f"      {sc}→ {sig['name']}:{C.Z} {sig['detail']}")
    print()


def save_report(results, mode="EOD"):
    date_str = datetime.now().strftime("%Y%m%d")
    now = datetime.now().strftime("%H:%M:%S")
    with_signal = [r for r in results if r.get("buy_signals")]

    # Markdown
    lines = [
        f"# 📊 策略一扫描报告", "",
        f"**日期**: {date_str} | **时间**: {now} | **模式**: {mode}", "",
        f"## 选股条件", "",
        f"| 条件 | 参数 |", "|------|------|",
        f"| 股价 | < {CONDITIONS['price_max']}元 |",
        f"| 均线 | MA5 > MA10 > MA20 |",
        f"| 换手率 | {CONDITIONS['turnover_min']}% ~ {CONDITIONS['turnover_max']}% |",
        f"| 量比 | {CONDITIONS['vol_ratio_min']}x ~ {CONDITIONS['vol_ratio_max']}x |",
        f"| 排除 | ST / 创业板 / 科创板 / 北证 |", "",
        f"---", "",
        f"## 结果概览", "",
        f"- 初筛通过: **{len(results)}** 只",
        f"- 触发买点: **{len(with_signal)}** 只", "",
    ]
    if with_signal:
        lines += [
            f"## 🔥 买入候选", "",
            f"| 排名 | 代码 | 名称 | 现价 | 涨幅 | MA5 | MA10 | MA20 | 换手 | 量比 | 买点 |",
            f"|------|------|------|------|------|------|------|------|------|------|------|",
        ]
        for i, r in enumerate(with_signal, 1):
            sig_names = " + ".join(s["name"] for s in r["buy_signals"])
            lines.append(
                f"| {i} | {r['code']} | {r['name']} | {r['price']:.2f} | {r['pct']:+.2f}% | "
                f"{r['ma5']:.2f} | {r['ma10']:.2f} | {r['ma20']:.2f} | {r['turnover']:.1f}% | "
                f"{r['vol_ratio']:.2f}x | {sig_names} |"
            )

    report_path = os.path.join(OUTPUT_DIR, "策略一_扫描报告.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  {C.G}📄 报告已保存: {report_path}{C.Z}\n")

    # JSON
    json_path = os.path.join(OUTPUT_DIR, "策略一_result.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"date": date_str, "time": now, "total": len(results),
                   "with_signal": len(with_signal), "candidates": results},
                  f, ensure_ascii=False, indent=2)
    print(f"  {C.G}📄 JSON结果: {json_path}{C.Z}\n")


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

def run_scan(mode="EOD"):
    """执行一次完整扫描"""
    print(f"\n  {C.B}⏳ 加载股票列表...{C.Z}")
    all_stocks = get_stock_list(cache_dir=BASE_DIR)
    if not all_stocks:
        print(f"  {C.R}❌ 获取股票列表失败{C.Z}")
        return []

    print(f"  {C.B}📡 全市场行情初筛（{len(all_stocks)} 只 → 换手+价格+板块过滤）...{C.Z}")
    candidates = initial_filter(all_stocks)
    print(f"  {C.Y}初筛通过: {len(candidates)} 只{C.Z}")

    if not candidates:
        print_console_report([])
        save_report([])
        return []

    print(f"  {C.B}🔍 K线深度分析（均线多头+量比，{CONCURRENT_WORKERS}线程并发）...{C.Z}")
    results = []
    total = len(candidates)

    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as ex:
        futures = {ex.submit(deep_analyze, c): i for i, c in enumerate(candidates)}
        done = 0
        for fut in as_completed(futures):
            done += 1
            try:
                r = fut.result()
                if r:
                    results.append(r)
            except Exception:
                pass
            if done % 20 == 0 or done == total:
                sys.stdout.write(f"\r  {C.D}  K线分析: {done}/{total}  通过: {len(results)}{C.Z}")
                sys.stdout.flush()
    sys.stdout.write(f"\r{C.D}{' '*50}{C.Z}\r")

    print(f"  {C.G}深度通过: {len(results)} 只{C.Z}")
    results.sort(key=lambda x: len(x.get("buy_signals", [])), reverse=True)

    print_console_report(results, mode)
    save_report(results, mode)
    return results


def run_live(interval=300):
    """盘中实时监控"""
    print(f"\n  {C.M}📡 策略一 盘中监控 (刷新: {interval}s, Ctrl+C 退出){C.Z}\n")
    last_signals = set()
    try:
        while True:
            results = run_scan(mode="LIVE")
            current_signals = {r["code"] for r in results if r.get("buy_signals")}
            new_signals = current_signals - last_signals
            if new_signals:
                new_stocks = [r for r in results if r["code"] in new_signals and r.get("buy_signals")]
                print(f"\n  {C.R}🆕 新触发买点: {', '.join(s['name'] for s in new_stocks)}{C.Z}\n")
            last_signals = current_signals
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n  {C.Y}👋 监控结束{C.Z}\n")


def main():
    print(f"""
{C.M}╔══════════════════════════════════════════════════════╗
║  📊 策略一：均线多头 + 温和放量                        ║
║  买点A: 回调MA10不破+收阳   买点B: 放量站稳MA5        ║
║  数据源: 腾讯财经 (免费/国内/无需API)                  ║
╚══════════════════════════════════════════════════════╝{C.Z}
""")
    args = sys.argv[1:]
    if "--live" in args:
        idx = args.index("--live")
        interval = int(args[idx + 1]) if idx + 1 < len(args) else 300
        run_live(interval=interval)
    elif "--once" in args:
        run_scan(mode="QUICK")
    else:
        run_scan(mode="EOD")


if __name__ == "__main__":
    main()
