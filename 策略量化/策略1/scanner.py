# -*- coding: utf-8 -*-
"""
策略一：均线多头 + 温和放量 —— 扫描引擎
  · 盘后模式：python scanner.py           → 全量扫描，生成明日候选
  · 盘中模式：python scanner.py --live    → 每5分钟扫描，实时信号
  · 单次快扫：python scanner.py --once    → 只跑一次，终端输出

数据源：腾讯财经（免费/国内直连/无需API Key）
"""

import sys, os, time, json, re
from datetime import datetime, timedelta
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

# 编码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except:
        pass

# 把上级目录加入 path，方便导入 stock_quant 的工具函数
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─── 依赖检查 ───
try:
    import urllib.request
    import urllib.error
except ImportError:
    print("❌ 需要 urllib（Python 内置，不应该缺少）")
    sys.exit(1)

# ─── 路径 ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = BASE_DIR  # 报告输出到策略1目录下

# ─── 并发设置 ───
CONCURRENT_WORKERS = 12  # 并发线程数（国内网络可开大点）

# ─── 加载配置 ───
from config import CONDITIONS, BUY_SIGNALS, SELL_SIGNALS, POSITION, DATA as CFG

# ═══════════════════════════════════════════
# 颜色
# ═══════════════════════════════════════════


class C:
    R = "\033[1;31m"
    G = "\033[1;32m"
    Y = "\033[1;33m"
    B = "\033[1;36m"
    M = "\033[1;35m"
    W = "\033[1;37m"
    D = "\033[2;37m"
    Z = "\033[0m"


# ═══════════════════════════════════════════
# HTTP 请求
# ═══════════════════════════════════════════

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def http_get(url, timeout=10, decode="gbk"):
    """HTTP GET，带UA和超时"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        # 尝试 utf-8 再 gbk
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode(decode, errors="replace")


# ═══════════════════════════════════════════
# 第一部分：股票列表
# ═══════════════════════════════════════════


def get_stock_list():
    """获取全A股列表（东方财富源 → 缓存24h）"""
    cache_path = os.path.join(BASE_DIR, ".stock_list_cache.json")

    # 读缓存
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < CFG["stock_list_cache_hours"] * 3600:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

    codes = {}
    # 东方财富分页拉取
    try:
        page = 1
        while True:
            url = (
                "http://80.push2.eastmoney.com/api/qt/clist/get?"
                f"pn={page}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f12"
                "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14"
            )
            raw = http_get(url, decode="utf-8", timeout=10)
            data = json.loads(raw)
            items = data["data"].get("diff", [])
            if not items:
                break
            for r in items:
                codes[r["f12"]] = r["f14"]
            total = data["data"].get("total", 0)
            if page * 100 >= total:
                break
            page += 1
    except Exception:
        pass

    if codes:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(codes, f, ensure_ascii=False)

    return codes


# ═══════════════════════════════════════════
# 第二部分：行情获取（腾讯批量）
# ═══════════════════════════════════════════


def fetch_quotes_batch(code_list, workers=10):
    """腾讯批量行情 → list[dict]（并发版）"""
    results = []
    batches = [code_list[i : i + 50] for i in range(0, len(code_list), 50)]
    batch_count = len(batches)

    def _fetch_one(batch):
        url = "http://qt.gtimg.cn/q=" + ",".join(batch)
        try:
            raw = http_get(url, timeout=10)
            return _parse_tencent_quote(raw)
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_fetch_one, b): i for i, b in enumerate(batches)}
        for fut in as_completed(futures):
            try:
                results.extend(fut.result())
            except Exception:
                continue

    return results


def _parse_tencent_quote(raw):
    """解析腾讯 v_xx="1~name~code~price~..." 格式"""
    results = []
    for line in raw.strip().split(";\n"):
        m = re.search(r'="(.+)"$', line.strip())
        if not m:
            continue
        f = m.group(1).split("~")
        if len(f) < 40:
            continue
        try:
            price = float(f[3]) if f[3] else 0
            preclose = float(f[4]) if f[4] else 0
            pct = ((price - preclose) / preclose * 100) if (price and preclose) else 0
            results.append(
                {
                    "code": f[2],
                    "name": f[1],
                    "price": price,
                    "pct": round(pct, 2),
                    "preclose": preclose,
                    "open": float(f[5]) if f[5] else 0,
                    "volume": float(f[6]) if f[6] else 0,
                    "high": float(f[33]) if len(f) > 33 and f[33] else 0,
                    "low": float(f[34]) if len(f) > 34 and f[34] else 0,
                    "amount": float(f[37]) if len(f) > 37 and f[37] else 0,
                    "turnover": float(f[38]) if len(f) > 38 and f[38] else 0,
                    "time": f[30] if len(f) > 30 else "",
                }
            )
        except Exception:
            continue
    return results


def get_tencent_code(raw_code):
    """把 '600519' 转成腾讯格式 'sh600519'"""
    raw = str(raw_code).zfill(6)
    return f"sh{raw}" if raw.startswith(("6", "9")) else f"sz{raw}"


# ═══════════════════════════════════════════
# 第三部分：K线获取（腾讯）
# ═══════════════════════════════════════════


def get_kline(code, days=60):
    """获取个股日K线"""
    raw = str(code).zfill(6)
    m = "sh" if raw.startswith(("6", "9")) else "sz"
    url = (
        f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
        f"param={m}{raw},day,,,{days},qfq"
    )
    try:
        raw_data = http_get(url, decode="utf-8")
        data = json.loads(raw_data)
        kl = (
            data["data"][f"{m}{raw}"].get("day", [])
            or data["data"][f"{m}{raw}"].get("qfqday", [])
        )
        if not kl:
            return None
        return [
            {
                "date": it[0],
                "open": float(it[1]),
                "close": float(it[2]),
                "high": float(it[3]),
                "low": float(it[4]),
                "volume": float(it[5]),
            }
            for it in kl
        ]
    except Exception:
        return None


# ═══════════════════════════════════════════
# 第四部分：技术指标
# ═══════════════════════════════════════════


def calc_ma(values, period):
    """简单移动平均"""
    if len(values) < period:
        return [None] * len(values)
    result = [None] * (period - 1)
    for i in range(period - 1, len(values)):
        result.append(sum(values[i - period + 1 : i + 1]) / period)
    return result


def calc_vol_ratio(volumes, period=5):
    """量比 = 当日量 / N日均量"""
    if len(volumes) < period + 1:
        return None
    avg = sum(volumes[-(period + 1) : -1]) / period
    return volumes[-1] / avg if avg > 0 else None


# ═══════════════════════════════════════════
# 第五部分：筛选逻辑
# ═══════════════════════════════════════════


def is_valid_board(code, name):
    """排除创业板/科创板/北证/ST"""
    raw = str(code).zfill(6)
    # 前缀排除
    for prefix in CONDITIONS["exclude_prefix"]:
        if raw.startswith(prefix):
            return False
    # ST 排除
    if CONDITIONS["exclude_st"] and ("ST" in name.upper() or "*ST" in name.upper()):
        return False
    # 必须是沪深主板 (0/2/6/9)
    if not raw.startswith(("0", "2", "6", "9")):
        return False
    return True


def initial_filter(all_stocks):
    """
    第一轮：行情初筛
    - 股价 < 20
    - 换手率 5~10%
    - 非ST/创业板/科创板/北证

    返回：候选列表 [{code, name, price, pct, turnover, volume, ...}]
    """
    # 转为腾讯格式代码
    code_map = {}
    for raw_code, name in all_stocks.items():
        raw = str(raw_code).zfill(6)
        if is_valid_board(raw, name):
            code_map[raw] = name

    if not code_map:
        print(f"  {C.Y}无有效标的{C.Z}")
        return []

    # 分批获取行情
    tx_codes = [get_tencent_code(c) for c in code_map]
    all_quotes = fetch_quotes_batch(tx_codes, workers=CONCURRENT_WORKERS)

    candidates = []
    for q in all_quotes:
        code = q.get("code", "")
        price = q.get("price", 0)
        turnover = q.get("turnover", 0)
        name = code_map.get(code, q.get("name", ""))

        # 价格过滤
        if price <= 0 or price >= CONDITIONS["price_max"]:
            continue

        # 换手率过滤
        if turnover < CONDITIONS["turnover_min"] or turnover > CONDITIONS["turnover_max"]:
            continue

        candidates.append(
            {
                "code": code,
                "name": name,
                "price": price,
                "pct": q.get("pct", 0),
                "turnover": turnover,
                "volume": q.get("volume", 0),
                "open": q.get("open", 0),
                "high": q.get("high", 0),
                "low": q.get("low", 0),
                "preclose": q.get("preclose", 0),
            }
        )

    return candidates


def deep_analyze(candidate):
    """
    第二轮：K线深度分析
    - 均线多头排列 MA5 > MA10 > MA20
    - 量比 1~10
    - 检测买点 A（回调MA10）/ 买点 B（放量站MA5）

    返回：带分析结果的 dict，不满足条件返回 None
    """
    code = candidate["code"]
    kl = get_kline(code, days=CFG["kline_days"])
    if not kl or len(kl) < 35:
        return None

    closes = [k["close"] for k in kl]
    volumes = [k["volume"] for k in kl]

    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)

    # 检查均线是否有值
    if None in (ma5[-1], ma10[-1], ma20[-1]):
        return None

    # ─── 均线多头排列 ───
    if not (ma5[-1] > ma10[-1] > ma20[-1]):
        return None

    # ─── 量比 ───
    vol_ratio = calc_vol_ratio(volumes, 5)
    if vol_ratio is None:
        return None
    if vol_ratio < CONDITIONS["vol_ratio_min"] or vol_ratio > CONDITIONS["vol_ratio_max"]:
        return None

    # ─── 检测买点 ───
    buy_signals = []

    # 买点A：回调MA10不破 + 收阳
    # 收盘 ≥ MA10 × 0.98（距MA10不超过2%）且 收盘 > 开盘
    close_today = closes[-1]
    open_today = kl[-1]["open"]
    if close_today >= ma10[-1] * 0.98 and close_today > open_today:
        buy_signals.append(
            {
                "type": "A_pullback_ma10",
                "name": BUY_SIGNALS["A_pullback_ma10"]["name"],
                "detail": (
                    f"收盘{close_today:.2f}距MA10({ma10[-1]:.2f})仅"
                    f"{(close_today - ma10[-1]) / ma10[-1] * 100:+.1f}%，收阳确认"
                ),
            }
        )

    # 买点B：放量站稳MA5
    if close_today >= ma5[-1] and vol_ratio >= 1.5:
        buy_signals.append(
            {
                "type": "B_breakout_ma5",
                "name": BUY_SIGNALS["B_breakout_ma5"]["name"],
                "detail": (
                    f"收盘{close_today:.2f}站稳MA5({ma5[-1]:.2f})，量比{vol_ratio:.1f}x"
                ),
            }
        )

    return {
        **candidate,
        "ma5": round(ma5[-1], 2),
        "ma10": round(ma10[-1], 2),
        "ma20": round(ma20[-1], 2),
        "vol_ratio": round(vol_ratio, 2),
        "close": close_today,
        "buy_signals": buy_signals,
    }


# ═══════════════════════════════════════════
# 第六部分：报告输出
# ═══════════════════════════════════════════


def print_console_report(results, mode="EOD"):
    """终端彩色输出"""
    now = datetime.now().strftime("%H:%M:%S")

    print(f"\n{C.M}╔══════════════════════════════════════════════════════╗")
    print(f"║  📊 策略一：均线多头+温和放量  {'盘后扫描' if mode=='EOD' else '盘中快扫'}")
    print(f"║  时间: {now}                                          ║")
    print(f"╚══════════════════════════════════════════════════════╝{C.Z}\n")

    if not results:
        print(f"  {C.Y}⭕ 今日无符合条件的股票{C.Z}")
        print(f"  {C.D}条件: 股价<20 | MA5>10>20 | 换手5-10% | 量比1-10x{C.Z}\n")
        return

    # 有买点的排前面
    with_signal = [r for r in results if r.get("buy_signals")]
    no_signal = [r for r in results if not r.get("buy_signals")]

    print(f"  {C.Y}初筛通过: {len(results)} 只  |  触发买点: {len(with_signal)} 只{C.Z}\n")

    if with_signal:
        print(f"  {C.R}━━━ 🔥 触发买入信号 ━━━{C.Z}\n")
        for i, r in enumerate(with_signal, 1):
            _print_one_stock(i, r)

    if no_signal:
        print(f"  {C.D}━━━ 📋 符合条件但未触发买点 ━━━{C.Z}\n")
        for i, r in enumerate(no_signal, len(with_signal) + 1):
            _print_one_stock(i, r)

    # 条件说明
    print(f"  {C.D}{'─'*70}{C.Z}")
    print(f"  {C.D}条件: 股价<20元 | MA5>MA10>MA20 | 换手5-10% | 量比1-10x{C.Z}")
    print(f"  {C.D}买点A: 回调MA10不破+收阳 → 次日开盘买{C.Z}")
    print(f"  {C.D}买点B: 放量站稳MA5+量比≥1.5 → 次日开盘买{C.Z}")
    print(f"  {C.D}⚠️ 获利盘<80%需在同花顺人工核对筹码峰{C.Z}\n")


def _print_one_stock(rank, r):
    """打印单只股票"""
    signals = r.get("buy_signals", [])
    has_signal = bool(signals)

    marker = "🔴" if signals and "A_pullback_ma10" in [s["type"] for s in signals] else (
        "🟡" if signals else "  "
    )
    name_color = C.R if has_signal else C.D

    print(
        f"  {marker} {rank}. {name_color}{r['name']}{C.Z} "
        f"({C.B}{r['code']}{C.Z})  "
        f"¥{r['price']:.2f}  "
        f"涨幅{C.R if r['pct']>0 else C.G}{r['pct']:+.2f}%{C.Z}"
    )
    print(
        f"      MA5:{r['ma5']:.2f} > MA10:{r['ma10']:.2f} > MA20:{r['ma20']:.2f}  |  "
        f"换手:{r['turnover']:.1f}%  |  量比:{r['vol_ratio']:.2f}x"
    )

    for sig in signals:
        sig_color = C.R if sig["type"] == "A_pullback_ma10" else C.Y
        print(f"      {sig_color}→ {sig['name']}:{C.Z} {sig['detail']}")

    print()


def save_report(results, mode="EOD"):
    """保存 Markdown 报告"""
    date_str = datetime.now().strftime("%Y%m%d")
    now = datetime.now().strftime("%H:%M:%S")

    with_signal = [r for r in results if r.get("buy_signals")]
    no_signal = [r for r in results if not r.get("buy_signals")]

    lines = []
    lines.append(f"# 📊 策略一扫描报告")
    lines.append(f"")
    lines.append(f"**日期**: {date_str} | **时间**: {now} | **模式**: {mode}")
    lines.append(f"")
    lines.append(f"## 选股条件")
    lines.append(f"")
    lines.append(f"| 条件 | 参数 |")
    lines.append(f"|------|------|")
    lines.append(f"| 股价 | < {CONDITIONS['price_max']}元 |")
    lines.append(f"| 均线 | MA5 > MA10 > MA20 |")
    lines.append(f"| 换手率 | {CONDITIONS['turnover_min']}% ~ {CONDITIONS['turnover_max']}% |")
    lines.append(f"| 量比 | {CONDITIONS['vol_ratio_min']}x ~ {CONDITIONS['vol_ratio_max']}x |")
    lines.append(f"| 排除 | ST / 创业板 / 科创板 / 北证 |")
    lines.append(f"| 获利盘 | < {CONDITIONS['profit_chip_max']}%（人工核查）|")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## 结果概览")
    lines.append(f"")
    lines.append(f"- 初筛通过: **{len(results)}** 只")
    lines.append(f"- 触发买点: **{len(with_signal)}** 只")
    lines.append(f"")

    if with_signal:
        lines.append(f"## 🔥 买入候选")
        lines.append(f"")
        lines.append(
            f"| 排名 | 代码 | 名称 | 现价 | 涨幅 | MA5 | MA10 | MA20 | 换手 | 量比 | 买点 |"
        )
        lines.append(
            f"|------|------|------|------|------|------|------|------|------|------|------|"
        )
        for i, r in enumerate(with_signal, 1):
            sig_names = " + ".join(s["name"] for s in r["buy_signals"])
            lines.append(
                f"| {i} | {r['code']} | {r['name']} | {r['price']:.2f} | "
                f"{r['pct']:+.2f}% | {r['ma5']:.2f} | {r['ma10']:.2f} | "
                f"{r['ma20']:.2f} | {r['turnover']:.1f}% | {r['vol_ratio']:.2f}x | "
                f"{sig_names} |"
            )

    if no_signal:
        lines.append(f"")
        lines.append(f"## 📋 观察列表（符合条件但未触发买点）")
        lines.append(f"")
        lines.append(
            f"| 排名 | 代码 | 名称 | 现价 | 涨幅 | MA5 | MA10 | MA20 | 换手 | 量比 |"
        )
        lines.append(
            f"|------|------|------|------|------|------|------|------|------|------|"
        )
        for i, r in enumerate(no_signal, len(with_signal) + 1):
            lines.append(
                f"| {i} | {r['code']} | {r['name']} | {r['price']:.2f} | "
                f"{r['pct']:+.2f}% | {r['ma5']:.2f} | {r['ma10']:.2f} | "
                f"{r['ma20']:.2f} | {r['turnover']:.1f}% | {r['vol_ratio']:.2f}x |"
            )

    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## ⚠️ 风控提醒")
    lines.append(f"")
    lines.append(f"| 规则 | 参数 |")
    lines.append(f"|------|------|")
    lines.append(f"| 仓位 | {POSITION['fixed_shares']}股/笔，最多{POSITION['max_holdings']}只 |")
    lines.append(f"| 止损 | {POSITION['stop_loss_pct']}% 硬止损 |")
    lines.append(f"| 止盈 | +{POSITION['take_profit_pct']}% |")
    lines.append(f"| 本金 | {POSITION['init_capital']}元 |")
    lines.append(f"")
    lines.append(f"> 🦀 小秋提醒：获利盘请在同花顺F10 → 筹码集中度 核对，>80%不碰。")
    lines.append(f"> 打板追涨是概率游戏，仓位管理才是活下来的关键。")

    report_path = os.path.join(OUTPUT_DIR, "策略一_扫描报告.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  {C.G}📄 报告已保存: {report_path}{C.Z}\n")

    # 同时存 JSON
    json_path = os.path.join(OUTPUT_DIR, "策略一_result.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": date_str,
                "time": now,
                "total": len(results),
                "with_signal": len(with_signal),
                "candidates": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"  {C.G}📄 JSON结果: {json_path}{C.Z}\n")


# ═══════════════════════════════════════════
# 第七部分：主入口
# ═══════════════════════════════════════════


def run_scan(mode="EOD"):
    """执行一次完整扫描"""
    print(f"\n  {C.B}⏳ 加载股票列表...{C.Z}")
    all_stocks = get_stock_list()
    if not all_stocks:
        print(f"  {C.R}❌ 获取股票列表失败（网络问题）{C.Z}")
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
                sys.stdout.write(
                    f"\r  {C.D}  K线分析: {done}/{total}  通过: {len(results)}{C.Z}"
                )
                sys.stdout.flush()
    sys.stdout.write(f"\r{C.D}{' '*50}{C.Z}\r")

    print(f"  {C.G}深度通过: {len(results)} 只{C.Z}")

    # 按买点数量排序
    results.sort(key=lambda x: len(x.get("buy_signals", [])), reverse=True)

    print_console_report(results, mode)
    save_report(results, mode)

    return results


def run_live(interval=300):
    """盘中实时监控模式"""
    print(f"\n  {C.M}📡 策略一 盘中监控 (刷新: {interval}s, Ctrl+C 退出){C.Z}\n")
    last_signals = set()

    try:
        while True:
            results = run_scan(mode="LIVE")
            current_signals = {
                r["code"] for r in results if r.get("buy_signals")
            }
            new_signals = current_signals - last_signals
            if new_signals:
                new_stocks = [
                    r for r in results
                    if r["code"] in new_signals and r.get("buy_signals")
                ]
                print(
                    f"\n  {C.R}🆕 新触发买点: "
                    f"{', '.join(s['name'] for s in new_stocks)}{C.Z}\n"
                )
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

    mode = "EOD"
    interval = 300

    args = sys.argv[1:]
    if "--live" in args:
        idx = args.index("--live")
        if idx + 1 < len(args):
            try:
                interval = int(args[idx + 1])
            except ValueError:
                pass
        run_live(interval=interval)
        return

    if "--once" in args:
        run_scan(mode="QUICK")
        return

    # 默认：盘后扫描
    run_scan(mode="EOD")


if __name__ == "__main__":
    main()
