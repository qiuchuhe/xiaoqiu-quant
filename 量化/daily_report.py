# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════╗
║   🦀 小秋每日信号扫描报告 v1.0              ║
║   双策略全池扫描 → Markdown 日报            ║
╚══════════════════════════════════════════════╝

用法:
  python daily_report.py              生成今日报告
  python daily_report.py --watch      只扫描自选池
  python daily_report.py --top100     全市场Top100扫描(慢)
  python daily_report.py --print      终端打印报告(不保存文件)

输出:
  reports/日报_2026-06-06.md
"""

import sys, os, time, json, re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── 编码 ───
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

# ─── 路径 ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
WATCHLIST_FILE = os.path.join(BASE_DIR, ".my_watchlist.json")
POSITION_FILE = os.path.join(BASE_DIR, ".position.json")
PLAN_FILE = os.path.join(BASE_DIR, ".tomorrow_plan.json")

# ─── HTTP ───
import urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

def http_get(url, timeout=10, decode="gbk"):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(decode)


# ═══════════════════════════════════════════
# 颜色
# ═══════════════════════════════════════════

class C:
    R = "\033[1;31m"; G = "\033[1;32m"; Y = "\033[1;33m"
    B = "\033[1;36m"; M = "\033[1;35m"; D = "\033[2;37m"; Z = "\033[0m"


# ═══════════════════════════════════════════
# K线 & 指标 (复用 monitor 逻辑)
# ═══════════════════════════════════════════

def get_kline(code, days=120):
    """获取日K线数据 (腾讯财经)"""
    raw_code = code.replace("sh","").replace("sz","").zfill(6)
    m = "sh" if raw_code.startswith(("6","9")) else "sz"
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={m}{raw_code},day,,,{days},qfq"
    try:
        raw = http_get(url, decode="utf-8")
        data = json.loads(raw)
        kl = data["data"][f"{m}{raw_code}"].get("day",[]) or \
             data["data"][f"{m}{raw_code}"].get("qfqday",[])
        return [{"date": it[0], "open": float(it[1]), "close": float(it[2]),
                 "high": float(it[3]), "low": float(it[4]), "volume": float(it[5])}
                for it in kl] if kl else None
    except:
        return None


def calc_ma(closes, n):
    """计算移动均线"""
    if len(closes) < n: return [None]*len(closes)
    r = [None]*(n-1)
    for i in range(n-1, len(closes)):
        r.append(sum(closes[i-n+1:i+1])/n)
    return r


def check_strategy_A(kl):
    """策略A: MA5金叉/死叉"""
    if not kl or len(kl) < 25: return None
    closes = [k["close"] for k in kl]
    ma5 = calc_ma(closes, 5)
    ma20 = calc_ma(closes, 20)
    if None in (ma5[-1], ma20[-1], ma5[-2], ma20[-2]): return None
    if ma5[-2] <= ma20[-2] and ma5[-1] > ma20[-1]:
        return "GOLDEN_CROSS"
    elif ma5[-2] >= ma20[-2] and ma5[-1] < ma20[-1]:
        return "DEATH_CROSS"
    return None


def check_strategy_B(kl):
    """策略B: 均线多头排列+温和放量"""
    if not kl or len(kl) < 35: return None
    closes = [k["close"] for k in kl]
    volumes = [k["volume"] for k in kl]
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma15 = calc_ma(closes, 15)
    ma30 = calc_ma(closes, 30)
    if None in (ma5[-1], ma10[-1], ma15[-1], ma30[-1]): return None
    if not (ma5[-1] > ma10[-1] > ma15[-1] > ma30[-1]): return None
    # 今日涨幅 1%-5%
    if closes[-2] <= 0: return None
    pct = (closes[-1] - closes[-2]) / closes[-2] * 100
    if pct < 1 or pct > 5: return None
    # 温和放量 1.2x-3x
    if len(volumes) < 6: return None
    avg_vol = sum(volumes[-6:-1]) / 5
    if avg_vol <= 0: return None
    vol_ratio = volumes[-1] / avg_vol
    if vol_ratio < 1.2 or vol_ratio > 3.0: return None
    # 股价 < 25
    if closes[-1] >= 25: return None
    return "BULLISH_ALIGN"


def check_ma_trend(kl):
    """检查均线趋势（比策略B宽松，只检查多头排列，不限制量价）"""
    if not kl or len(kl) < 35: return None
    closes = [k["close"] for k in kl]
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)
    if None in (ma5[-1], ma10[-1], ma20[-1], ma60[-1]): return None
    if ma5[-1] > ma10[-1] > ma20[-1] > ma60[-1]:
        return "STRONG_BULLISH"  # MA5>10>20>60 强多头
    if ma5[-1] > ma10[-1] > ma20[-1]:
        return "BULLISH"  # MA5>10>20 常规多头
    return None


def calc_volume_ratio(kl):
    """计算量比 (今日量 / 近5日均量)"""
    if not kl or len(kl) < 6: return None
    volumes = [k["volume"] for k in kl]
    avg5 = sum(volumes[-6:-1]) / 5
    return volumes[-1] / avg5 if avg5 > 0 else None


# ═══════════════════════════════════════════
# 行情获取
# ═══════════════════════════════════════════

def parse_tx(raw):
    """解析腾讯实时行情"""
    results = []
    for line in raw.strip().split(";\n"):
        m = re.search(r'="(.+)"$', line.strip())
        if not m: continue
        f = m.group(1).split("~")
        if len(f) < 40: continue
        try:
            price = float(f[3]) if f[3] else None
            preclose = float(f[4]) if f[4] else None
            pct = ((price - preclose) / preclose * 100) if (price and preclose) else None
            results.append({
                "code": f[2], "name": f[1], "price": price,
                "pct": pct, "preclose": preclose,
                "volume": float(f[6]) if f[6] else 0,
                "high": float(f[33]) if len(f)>33 and f[33] else None,
                "low": float(f[34]) if len(f)>34 and f[34] else None,
                "turnover": float(f[38]) if len(f)>38 and f[38] else None,
            })
        except: continue
    return results


def get_quotes(codes):
    """批量获取实时行情"""
    all_r = []
    for i in range(0, len(codes), 50):
        batch = codes[i:i+50]
        url = "http://qt.gtimg.cn/q=" + ",".join(batch)
        try:
            raw = http_get(url, timeout=10)
            all_r.extend(parse_tx(raw))
        except:
            continue
    return all_r


# ═══════════════════════════════════════════
# 过滤逻辑
# ═══════════════════════════════════════════

def is_valid_stock(code, name=""):
    """过滤创业板/科创板/ST/ETF"""
    raw = code.replace("sh","").replace("sz","")
    # 创业板 30xxxx
    if raw.startswith("30"): return False
    # 科创板 688xxx
    if raw.startswith("688"): return False
    # ST
    if "ST" in name.upper() or "*ST" in name.upper(): return False
    # ETF (159xxx, 510xxx, 513xxx等)
    if raw.startswith(("159","510","513","588","560")): return False
    return True


def load_watchlist():
    """加载自选池"""
    if not os.path.exists(WATCHLIST_FILE):
        return {}
    with open(WATCHLIST_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_positions():
    """加载持仓"""
    if not os.path.exists(POSITION_FILE):
        return []
    with open(POSITION_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("holdings", [])


def load_plan():
    """加载明日计划"""
    if not os.path.exists(PLAN_FILE):
        return None
    with open(PLAN_FILE, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════
# 单只股票分析
# ═══════════════════════════════════════════

def analyze_stock(code, name):
    """对单只股票执行完整分析，返回信号字典"""
    result = {
        "code": code.replace("sh","").replace("sz",""),
        "name": name,
        "strategy_a": None,
        "strategy_b": None,
        "ma_trend": None,
        "volume_ratio": None,
        "last_close": None,
        "last_pct": None,
    }

    kl = get_kline(code, days=120)
    if not kl or len(kl) < 30:
        return result

    closes = [k["close"] for k in kl]
    result["last_close"] = closes[-1]
    if len(closes) >= 2 and closes[-2] > 0:
        result["last_pct"] = (closes[-1] - closes[-2]) / closes[-2] * 100

    # 价格过滤 (20元上限)
    if closes[-1] > 20:
        return result

    result["strategy_a"] = check_strategy_A(kl)
    result["strategy_b"] = check_strategy_B(kl)
    result["ma_trend"] = check_ma_trend(kl)
    result["volume_ratio"] = calc_volume_ratio(kl)

    return result


# ═══════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════

def generate_report(results, positions, plan=None):
    """生成 Markdown 报告"""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    weekday = ["周一","周二","周三","周四","周五","周六","周日"][now.weekday()]

    # ── 筛选各类信号 ──
    golden_cross = [r for r in results if r["strategy_a"] == "GOLDEN_CROSS"]
    death_cross = [r for r in results if r["strategy_a"] == "DEATH_CROSS"]
    bullish_align = [r for r in results if r["strategy_b"] == "BULLISH_ALIGN"]
    strong_bullish = [r for r in results if r["ma_trend"] == "STRONG_BULLISH"]
    bullish = [r for r in results if r["ma_trend"] in ("BULLISH", "STRONG_BULLISH")]
    high_vol = [r for r in results if r["volume_ratio"] and r["volume_ratio"] > 2.0]

    # 综合评分 (多头+放量优先)
    scored = []
    for r in results:
        score = 0
        if r["strategy_a"] == "GOLDEN_CROSS": score += 30
        if r["strategy_b"] == "BULLISH_ALIGN": score += 40
        if r["ma_trend"] == "STRONG_BULLISH": score += 20
        elif r["ma_trend"] == "BULLISH": score += 10
        if r["volume_ratio"] and 1.2 <= r["volume_ratio"] <= 3.0: score += 10
        if score > 0:
            scored.append({**r, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    top_picks = scored[:10]

    # ── 构建报告 ──
    lines = []
    lines.append(f"# 📋 小秋量化日报")
    lines.append(f"")
    lines.append(f"**{today_str} {weekday}** | 生成时间: {now.strftime('%H:%M:%S')}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # ═══ 持仓体检 ═══
    lines.append(f"## 📦 当前持仓体检")
    lines.append(f"")

    if positions:
        # 获取持仓股实时行情
        pos_codes = []
        for p in positions:
            raw = p["code"]
            prefix = "sh" if raw.startswith(("6","9")) else "sz"
            pos_codes.append(f"{prefix}{raw}")

        quotes = get_quotes(pos_codes) if pos_codes else []
        quote_map = {q["code"]: q for q in quotes}

        lines.append(f"| 代码 | 名称 | 成本 | 现价 | 盈亏 | 止损价 | 止盈价 | 状态 |")
        lines.append(f"|------|------|------|------|------|--------|--------|------|")

        for p in positions:
            code = p["code"]
            quote = quote_map.get(code)
            name = p.get("name", "")
            buy_price = p.get("buy_price", 0)

            if quote and quote.get("price"):
                price = quote["price"]
                pnl = (price - buy_price) / buy_price * 100
                dist_stop = (price - p.get("stop_loss", 0)) / price * 100
                dist_profit = (p.get("take_profit", 999) - price) / price * 100

                if pnl <= -5:
                    status = "🔴 已触发止损!"
                elif pnl >= 10:
                    status = "🟢 已触发止盈!"
                elif dist_stop < 2:
                    status = f"🟠 逼近止损({dist_stop:.1f}%)"
                elif dist_profit < 3:
                    status = f"🟡 接近止盈({dist_profit:.1f}%)"
                else:
                    status = f"⭕ 正常 (距止损{dist_stop:.1f}%)"

                lines.append(f"| {code} | {name} | {buy_price:.2f} | {price:.2f} | "
                            f"{pnl:+.2f}% | {p.get('stop_loss',0):.2f} | "
                            f"{p.get('take_profit',0):.2f} | {status} |")
            else:
                lines.append(f"| {code} | {name} | {buy_price:.2f} | -- | -- | "
                            f"{p.get('stop_loss',0):.2f} | {p.get('take_profit',0):.2f} | "
                            f"⏸️ 无行情 |")

        lines.append(f"")
    else:
        lines.append(f"> ⭕ 当前空仓，无持仓风险")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"")

    # ═══ 策略A信号 ═══
    lines.append(f"## 🔴 策略A: MA5/MA20 金叉信号 ({len(golden_cross)}只)")
    lines.append(f"")
    if golden_cross:
        lines.append(f"| 代码 | 名称 | 收盘价 | 涨幅 | 建议 |")
        lines.append(f"|------|------|--------|------|------|")
        for r in golden_cross[:15]:
            pct_s = f"{r['last_pct']:+.2f}%" if r['last_pct'] else "--"
            lines.append(f"| {r['code']} | {r['name']} | {r['last_close']:.2f} | {pct_s} | 🟢 关注 |")
        lines.append(f"")
    else:
        lines.append(f"> 无金叉信号")
        lines.append(f"")

    if death_cross:
        lines.append(f"### ⚠️ 死叉预警 ({len(death_cross)}只)")
        lines.append(f"")
        lines.append(f"| 代码 | 名称 | 收盘价 | 建议 |")
        lines.append(f"|------|------|--------|------|")
        for r in death_cross[:10]:
            lines.append(f"| {r['code']} | {r['name']} | {r['last_close']:.2f} | 🔴 减仓/清仓 |")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"")

    # ═══ 策略B信号 ═══
    lines.append(f"## 🟡 策略B: 多头排列+温和放量 ({len(bullish_align)}只)")
    lines.append(f"")
    if bullish_align:
        lines.append(f"| 代码 | 名称 | 收盘价 | 涨幅 | 量比 | 建议 |")
        lines.append(f"|------|------|--------|------|------|------|")
        for r in bullish_align[:15]:
            pct_s = f"{r['last_pct']:+.2f}%" if r['last_pct'] else "--"
            vr = f"{r['volume_ratio']:.1f}x" if r['volume_ratio'] else "--"
            lines.append(f"| {r['code']} | {r['name']} | {r['last_close']:.2f} | {pct_s} | {vr} | 🟢 次日开盘关注 |")
        lines.append(f"")
    else:
        lines.append(f"> 无策略B信号")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"")

    # ═══ 均线多头排列 ═══
    lines.append(f"## 📈 均线多头排列 ({len(bullish)}只)")
    lines.append(f"")
    if bullish:
        strong = [r for r in bullish if r["ma_trend"] == "STRONG_BULLISH"]
        normal = [r for r in bullish if r["ma_trend"] == "BULLISH"]

        if strong:
            lines.append(f"### 💪 强多头 MA5>10>20>60 ({len(strong)}只)")
            lines.append(f"")
            lines.append(f"| 代码 | 名称 | 收盘价 | 涨幅 |")
            lines.append(f"|------|------|--------|------|")
            for r in strong[:10]:
                pct_s = f"{r['last_pct']:+.2f}%" if r['last_pct'] else "--"
                lines.append(f"| {r['code']} | {r['name']} | {r['last_close']:.2f} | {pct_s} |")
            lines.append(f"")

        if normal:
            lines.append(f"### 👍 常规多头 MA5>10>20 ({len(normal)}只)")
            lines.append(f"")
            lines.append(f"| 代码 | 名称 | 收盘价 | 涨幅 |")
            lines.append(f"|------|------|--------|------|")
            for r in normal[:10]:
                pct_s = f"{r['last_pct']:+.2f}%" if r['last_pct'] else "--"
                lines.append(f"| {r['code']} | {r['name']} | {r['last_close']:.2f} | {pct_s} |")
            lines.append(f"")
    else:
        lines.append(f"> 无多头排列信号")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"")

    # ═══ 量能异动 ═══
    if high_vol:
        lines.append(f"## 📊 放量异动 (量比>2x, {len(high_vol)}只)")
        lines.append(f"")
        lines.append(f"| 代码 | 名称 | 收盘价 | 量比 |")
        lines.append(f"|------|------|--------|------|")
        for r in high_vol[:10]:
            lines.append(f"| {r['code']} | {r['name']} | {r['last_close']:.2f} | {r['volume_ratio']:.1f}x |")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"")

    # ═══ 综合TOP10 ═══
    lines.append(f"## 🎯 综合评分 TOP10 (明日重点关注)")
    lines.append(f"")
    if top_picks:
        lines.append(f"| 排名 | 代码 | 名称 | 收盘价 | 得分 | 信号 |")
        lines.append(f"|------|------|------|--------|------|------|")
        for i, r in enumerate(top_picks, 1):
            signals = []
            if r["strategy_a"] == "GOLDEN_CROSS": signals.append("金叉")
            if r["strategy_b"] == "BULLISH_ALIGN": signals.append("策略B")
            if r["ma_trend"] == "STRONG_BULLISH": signals.append("强多头")
            elif r["ma_trend"] == "BULLISH": signals.append("多头")
            sig_str = "+".join(signals) if signals else "--"

            emoji = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}"
            lines.append(f"| {emoji} | {r['code']} | {r['name']} | {r['last_close']:.2f} | "
                        f"{r['score']}分 | {sig_str} |")
        lines.append(f"")
    else:
        lines.append(f"> 今日无符合条件的标的，建议观望")
        lines.append(f"")

    # ═══ 明日计划 ═══
    if plan:
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## 📅 明日监控计划")
        lines.append(f"")
        stocks = plan.get("stocks", plan.get("watch", []))
        if stocks:
            lines.append(f"| 代码 | 名称 | 策略 | 触发条件 |")
            lines.append(f"|------|------|------|----------|")
            for s in stocks[:10]:
                code = s.get("code", "")
                name = s.get("name", "")
                strategy = s.get("strategy", "")
                trigger = s.get("trigger", s.get("reason", ""))
                lines.append(f"| {code} | {name} | {strategy} | {trigger} |")
            lines.append(f"")

    # ═══ 风控提醒 ═══
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## ⚠️ 风控参数提醒")
    lines.append(f"")
    lines.append(f"- 💰 本金: **3000元** | 每笔: **100股** | 最大持仓: **1只**")
    lines.append(f"- 🛑 硬止损: **-5%** | 🎯 硬止盈: **+10%**")
    lines.append(f"- 📉 移动止盈: 从高点回撤 **-3%** 即卖")
    lines.append(f"- ⏰ 只做20元以内主板/中小板，不做创业板/科创板/ST")
    lines.append(f"")
    lines.append(f"> 🦀 小秋提醒：信号是概率，纪律是生命。到了止损线就砍，别犹豫。")

    return "\n".join(lines)


# ═══════════════════════════════════════════
# 终端彩色输出
# ═══════════════════════════════════════════

def print_summary(results, positions):
    """终端打印摘要"""
    golden = [r for r in results if r["strategy_a"] == "GOLDEN_CROSS"]
    death = [r for r in results if r["strategy_a"] == "DEATH_CROSS"]
    balign = [r for r in results if r["strategy_b"] == "BULLISH_ALIGN"]
    bullish = [r for r in results if r["ma_trend"] in ("BULLISH", "STRONG_BULLISH")]

    print(f"""
{C.M}╔══════════════════════════════════════════════╗
║   🦀 小秋量化日报 {datetime.now().strftime('%Y-%m-%d')}                    ║
╚══════════════════════════════════════════════╝{C.Z}

{C.R}🔴 策略A金叉: {len(golden)}只{C.Z}  {C.Y}🟡 策略B多头: {len(balign)}只{C.Z}  {C.B}📈 均线多头: {len(bullish)}只{C.Z}  {C.G}⚠️ 死叉: {len(death)}只{C.Z}

{C.Y}🏆 TOP5 综合评分:{C.Z}""")

    scored = []
    for r in results:
        score = 0
        if r["strategy_a"] == "GOLDEN_CROSS": score += 30
        if r["strategy_b"] == "BULLISH_ALIGN": score += 40
        if r["ma_trend"] == "STRONG_BULLISH": score += 20
        elif r["ma_trend"] == "BULLISH": score += 10
        if r["volume_ratio"] and 1.2 <= r["volume_ratio"] <= 3.0: score += 10
        if score > 0: scored.append({**r, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(scored[:5], 1):
        s = []
        if r["strategy_a"] == "GOLDEN_CROSS": s.append("金叉")
        if r["strategy_b"] == "BULLISH_ALIGN": s.append("策略B")
        if r["ma_trend"] == "STRONG_BULLISH": s.append("强多头")
        print(f"  {i}. {r['name']}({r['code']}) {r['last_close']:.2f} "
              f"{C.Y}{r['score']}分{C.Z} {'+'.join(s)}")

    # 持仓
    if positions:
        print(f"\n{C.M}📦 持仓体检:{C.Z}")
        pos_codes = []
        for p in positions:
            raw = p["code"]
            prefix = "sh" if raw.startswith(("6","9")) else "sz"
            pos_codes.append(f"{prefix}{raw}")

        quotes = get_quotes(pos_codes) if pos_codes else []
        quote_map = {q["code"]: q for q in quotes}

        for p in positions:
            q = quote_map.get(p["code"])
            if q and q.get("price"):
                pnl = (q["price"] - p["buy_price"]) / p["buy_price"] * 100
                c = C.R if pnl >= 0 else C.G
                dist = (q["price"] - p.get("stop_loss", 0)) / q["price"] * 100
                warn = f" {C.R}⚠️ 距止损仅{dist:.1f}%!{C.Z}" if dist < 3 else ""
                print(f"  {p['name']}({p['code']}) 成本{p['buy_price']:.2f} → 现价{q['price']:.2f} "
                      f"{c}{pnl:+.2f}%{C.Z}{warn}")
            else:
                print(f"  {p['name']}({p['code']}) 成本{p['buy_price']:.2f} → 无实时行情")

    print(f"\n{C.D}完整报告已保存到 reports/ 目录{C.Z}")


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

def main():
    watch_only = "--watch" in sys.argv
    top100 = "--top100" in sys.argv
    print_only = "--print" in sys.argv

    os.makedirs(REPORTS_DIR, exist_ok=True)

    print(f"{C.B}🦀 小秋量化日报生成中...{C.Z}")

    # 1. 加载数据
    watchlist = load_watchlist()
    positions = load_positions()
    plan = load_plan()

    if not watchlist:
        print(f"{C.R}❌ 未找到自选池文件 .my_watchlist.json{C.Z}")
        return

    print(f"📋 自选池: {len(watchlist)} 只 | 持仓: {len(positions)} 只")

    # 2. 过滤
    valid_stocks = []
    for code, name in watchlist.items():
        if is_valid_stock(code, name):
            valid_stocks.append((code, name))

    skipped = len(watchlist) - len(valid_stocks)
    print(f"🔍 有效标的: {len(valid_stocks)} 只 (过滤{skipped}只创业板/科创/ST/ETF)")

    # 3. 加入持仓（确保一定分析）
    for p in positions:
        code = p["code"]
        raw = code
        prefix = "sh" if raw.startswith(("6","9")) else "sz"
        full = f"{prefix}{raw}"
        if full not in [c for c, _ in valid_stocks]:
            valid_stocks.append((full, p.get("name", "")))

    # 4. 并行分析
    print(f"⚡ 并行拉取K线分析中 (ThreadPoolExecutor)...")
    t0 = time.time()

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(analyze_stock, code, name): (code, name)
                   for code, name in valid_stocks}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 20 == 0:
                print(f"  进度: {done}/{len(valid_stocks)}")
            try:
                r = future.result()
                if r and r["last_close"] is not None:
                    results.append(r)
            except:
                pass

    elapsed = time.time() - t0
    print(f"✅ 分析完成: {len(results)} 只有效 | 耗时 {elapsed:.1f}s")

    # 5. 生成报告
    report_md = generate_report(results, positions, plan)

    if not print_only:
        now = datetime.now()
        filename = f"日报_{now.strftime('%Y-%m-%d')}.md"
        filepath = os.path.join(REPORTS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"{C.G}📄 报告已保存: {filepath}{C.Z}")

        # 同时保存最新的 JSON 信号数据（方便其他脚本读取）
        json_path = os.path.join(REPORTS_DIR, "latest_signals.json")
        top_scored = []
        for r in results:
            score = 0
            if r["strategy_a"] == "GOLDEN_CROSS": score += 30
            if r["strategy_b"] == "BULLISH_ALIGN": score += 40
            if r["ma_trend"] == "STRONG_BULLISH": score += 20
            elif r["ma_trend"] == "BULLISH": score += 10
            if r["volume_ratio"] and 1.2 <= r["volume_ratio"] <= 3.0: score += 10
            if score > 0:
                top_scored.append({**r, "score": score})
        top_scored.sort(key=lambda x: x["score"], reverse=True)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "top_picks": top_scored[:10],
                "golden_cross": [r for r in results if r["strategy_a"] == "GOLDEN_CROSS"],
                "bullish_align": [r for r in results if r["strategy_b"] == "BULLISH_ALIGN"],
            }, f, ensure_ascii=False, indent=2)

    # 6. 终端摘要
    print_summary(results, positions)


if __name__ == "__main__":
    main()
