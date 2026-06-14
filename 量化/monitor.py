# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════╗
║  🦀 小秋持仓监控 v4.0 — 四点巡检            ║
║  单次检查 → 打印状态 → 退出（零Token）     ║
╚══════════════════════════════════════════════╝

用法:
  python monitor.py              单次巡检（自动识别时段）
  python monitor.py --test       测试模式（模拟触发）

巡检时间点:
  09:45  早盘确认 — 开盘情绪释放完毕，确认今日方向
  11:30  午前收网 — 上午收盘前，消化整个早盘走势
  14:00  午后检查 — 午后运行一小时，观察尾盘蓄力
  14:55  收盘前哨 — 尾盘异动检测，决定次日操作

卖出信号（按优先级）:
  🔴 P1: 亏损 ≥ 5% → 硬止损，次日开盘卖
  🔴 P2: 移动止盈回撤 ≥ 3% → 当日卖出
  🟡 P3: MA5 下穿 MA10 → 趋势破坏，次日开盘卖
  🟢 P4: 盈利 ≥ 10% → 止盈，次日开盘卖
  🔵 P5: 量比>2 且 涨幅<1% → 放量滞涨，当日卖出
"""

import sys, os, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from 小秋核心.utils import C
from 小秋核心.data import get_quotes, get_kline
from 小秋核心.indicators import calc_ma

# ─── 路径 ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSITION_FILE = os.path.join(BASE_DIR, ".position.json")
ALERT_LOG = os.path.join(BASE_DIR, ".alert_log.txt")
TRADE_LOG = os.path.join(BASE_DIR, ".trade_log.txt")

# ─── 风控参数 ───
STOP_LOSS_PCT = -5.0
TAKE_PROFIT_PCT = 10.0
TRAILING_DRAWDOWN = -3.0

# ─── 巡检时间点 ───
CHECKPOINTS = [
    ("09:45", "早盘确认", "开盘情绪释放完毕，确认今日方向"),
    ("11:30", "午前收网", "上午收盘前，消化整个早盘走势"),
    ("14:00", "午后检查", "午后运行一小时，观察尾盘蓄力"),
    ("14:55", "收盘前哨", "尾盘异动检测，决定次日操作"),
]


# ═══════════════════════════════════════════
# 巡检点识别
# ═══════════════════════════════════════════

def get_checkpoint():
    """根据当前时间自动识别巡检点"""
    now = datetime.now()
    t = now.strftime("%H:%M")
    best = None
    for cp_time, cp_name, cp_desc in CHECKPOINTS:
        if t >= cp_time:
            best = (cp_time, cp_name, cp_desc)
    if best is None:
        best = ("盘前", "盘前检查", "开盘前例行巡检")
    return best


# ═══════════════════════════════════════════
# 日志 & 通知
# ═══════════════════════════════════════════

def log_msg(level, msg):
    now = datetime.now().strftime("%H:%M:%S")
    line = f"[{now}] [{level}] {msg}"
    print(line)
    try:
        with open(ALERT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {msg}\n")
    except Exception:
        pass


# ═══════════════════════════════════════════
# 持仓 I/O
# ═══════════════════════════════════════════

def load_positions():
    if not os.path.exists(POSITION_FILE):
        return None
    with open(POSITION_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_positions(data):
    data["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tmp = POSITION_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, POSITION_FILE)


# ═══════════════════════════════════════════
# 卖出信号检测
# ═══════════════════════════════════════════

def check_signals(pos, quote, kl):
    """五级卖出信号检测，按优先级返回第一个触发"""
    cost = pos.get("buy_price", pos.get("cost", 0) / max(pos.get("shares", 100), 1))
    price = quote.get("price", 0)
    if price <= 0 or cost <= 0:
        return None

    pnl_pct = (price - cost) / cost * 100

    # P1: 硬止损 -5%
    if pnl_pct <= STOP_LOSS_PCT:
        return {"id": "hard_stop", "name": "硬止损", "priority": 1,
                "detail": f"亏损{pnl_pct:.2f}%（阈值{STOP_LOSS_PCT}%）",
                "action": "次日开盘无条件卖出", "level": 3}

    # P2: 移动止盈（已涨超5%后回撤≥3%）
    high_price = pos.get("high_price", cost)
    if high_price > cost * 1.05:
        drawdown = (price - high_price) / high_price * 100
        if drawdown <= TRAILING_DRAWDOWN:
            return {"id": "trailing_stop", "name": "移动止盈", "priority": 2,
                    "detail": f"最高{high_price:.2f}→现价{price:.2f} 回撤{drawdown:+.2f}%",
                    "action": "当日卖出", "level": 3}

    # P3: MA5死叉MA10
    if kl and len(kl) >= 15:
        closes = [k["close"] for k in kl]
        ma5 = calc_ma(closes, 5)
        ma10 = calc_ma(closes, 10)
        if None not in (ma5[-1], ma10[-1], ma5[-2], ma10[-2]):
            if ma5[-2] >= ma10[-2] and ma5[-1] < ma10[-1]:
                return {"id": "ma5_cross_ma10", "name": "趋势破坏", "priority": 3,
                        "detail": f"MA5({ma5[-1]:.2f})下穿MA10({ma10[-1]:.2f})",
                        "action": "次日开盘卖出", "level": 2}

    # P4: 硬止盈 +10%
    if pnl_pct >= TAKE_PROFIT_PCT:
        return {"id": "take_profit", "name": "止盈", "priority": 4,
                "detail": f"盈利{pnl_pct:.2f}%（阈值+{TAKE_PROFIT_PCT}%）",
                "action": "次日开盘卖出", "level": 3}

    # P5: 放量滞涨
    if kl and len(kl) >= 6:
        volumes = [k["volume"] for k in kl]
        avg5 = sum(volumes[-6:-1]) / 5
        if avg5 > 0:
            vr = volumes[-1] / avg5
            if vr > 2 and quote.get("pct", 0) < 1:
                return {"id": "volume_spike_stall", "name": "放量滞涨", "priority": 5,
                        "detail": f"量比{vr:.1f}x但涨幅仅{quote.get('pct',0):.2f}%",
                        "action": "当日卖出", "level": 2}

    return None


# ═══════════════════════════════════════════
# 单次巡检（核心逻辑）
# ═══════════════════════════════════════════

def run_check(test_mode=False):
    """执行一次完整巡检 → 打印结果 → 返回"""
    cp_time, cp_name, cp_desc = get_checkpoint()
    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%H:%M:%S")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now().weekday()]

    # ── 头部 ──
    print(f"""
{C.M}╔══════════════════════════════════════════════════╗
║  🦀 小秋持仓巡检 v4.0                            ║
║  {today} {weekday}  {now_str}                      ║
╠══════════════════════════════════════════════════╣
║  📍 {cp_time} {cp_name} — {cp_desc}
╚══════════════════════════════════════════════════╝{C.Z}""")

    # ── 加载持仓 ──
    data = load_positions()
    if not data:
        print(f"\n  {C.Y}📭 无持仓数据（.position.json 不存在）{C.Z}\n")
        return

    holdings = data.get("holdings", [])
    if not holdings:
        print(f"\n  {C.G}📭 当前空仓，无需监控{C.Z}")
        print(f"  累计盈亏: {data.get('realized_pnl', 0):+.0f}元")
        print(f"  可用资金: ¥{data.get('cash_remaining', 0):,.0f}\n")
        return

    # ── 获取行情 ──
    codes = [h.get("code", "") for h in holdings]
    quotes = get_quotes(codes)

    dirty = False
    any_signal = False

    # ── 逐只检查 ──
    for h in holdings:
        code = h.get("code", "")
        name = h.get("name", "")
        buy_price = h.get("buy_price", 0)
        total_cost = h.get("cost", buy_price * h.get("shares", 100))
        shares = h.get("shares", 100)

        q = next((q for q in quotes if q["code"] == code), None)
        if not q or q.get("price", 0) <= 0:
            print(f"\n  {C.D}{name}({code}) 无实时行情{C.Z}")
            continue

        price = q["price"]
        pnl_pct = (price - buy_price) / buy_price * 100 if buy_price > 0 else 0
        pnl_c = C.R if pnl_pct >= 0 else C.G
        stop = h.get("stop_loss", buy_price * (1 + STOP_LOSS_PCT / 100))
        tp = h.get("take_profit", buy_price * (1 + TAKE_PROFIT_PCT / 100))
        dist_stop = (price - stop) / price * 100
        dist_tp = (tp - price) / price * 100

        # ── 更新日内最高价 ──
        if h.get("daily_high_date") != today:
            h["daily_high"] = q.get("high", 0)
            h["daily_high_date"] = today
            dirty = True
        elif q.get("high", 0) > (h.get("daily_high") or 0):
            h["daily_high"] = q.get("high", 0)
            dirty = True
        if price > (h.get("high_price", 0) or 0):
            h["high_price"] = price
            dirty = True

        # ── 状态行 ──
        print(f"""
  {C.B}── {name}({code}) ──{C.Z}
  │  现价: {price:.2f}  ({C.R if q.get('pct',0)>=0 else C.G}{q.get('pct',0):+.2f}%{C.Z})
  │  成本: {buy_price:.2f}  →  盈亏: {pnl_c}{pnl_pct:+.2f}%{C.Z}
  │  止损: {stop:.2f} (距{dist_stop:+.1f}%)  │  止盈: {tp:.2f} (距{dist_tp:+.1f}%)
  │  最高: {q.get('high',0):.2f}  │  最低: {q.get('low',0):.2f}  │  换手: {q.get('turnover',0):.1f}%""")

        # ── 信号检测 ──
        kl = get_kline(code, days=30)
        signal = check_signals(h, q, kl)

        if signal:
            any_signal = True
            icon = {3: "🔴", 2: "🟡", 1: "🟢"}.get(signal["level"], "⚪")
            print(f"  │")
            print(f"  ├── {icon} {C.R}{signal['name']}触发!{C.Z}")
            print(f"  │   {signal['detail']}")
            print(f"  │   → {signal['action']}")

            # 写交易日志
            try:
                with open(TRADE_LOG, "a", encoding="utf-8") as f:
                    f.write(f"\n{'='*50}\n"
                            f"卖出信号 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"标的: {name}({code}) | 巡检点: {cp_name}\n"
                            f"成本: {buy_price:.2f} | 现价: {price:.2f} | 盈亏: {pnl_pct:+.2f}%\n"
                            f"信号: {signal['name']} | {signal['detail']}\n"
                            f"操作: {signal['action']}\n{'='*50}\n")
            except Exception:
                pass

            log_msg("SIGNAL", f"{name}({code}) {signal['name']}: {signal['detail']}")
        else:
            # 距离预警
            if pnl_pct <= 0 and dist_stop <= 3:
                warn = "🟠 逼近止损!" if dist_stop <= 1 else "🟡 注意止损"
                print(f"  │   {warn}")
            elif pnl_pct > 0 and dist_tp <= 5:
                print(f"  │   🟡 接近止盈区")
            else:
                print(f"  │   ⭕ 正常")

    # ── 汇总 ──
    total_cost = sum(h.get("cost", h.get("buy_price", 0) * h.get("shares", 100)) for h in holdings)
    total_pnl = data.get("realized_pnl", 0)

    print(f"""
  {C.D}{'─'*50}{C.Z}
  {C.B}持仓汇总{C.Z}: {len(holdings)}只 | 占用资金 ¥{total_cost:,.0f} | 累计盈亏{C.R if total_pnl>=0 else C.G}{total_pnl:+.0f}元{C.Z}""")

    if any_signal:
        print(f"  {C.R}⚠️  有卖出信号触发，请查看上方详情{C.Z}")
    else:
        print(f"  {C.G}✅ 无需操作，继续持有{C.Z}")
        print(f"  {C.D}下次巡检: 下一个时间点运行 python monitor.py{C.Z}")

    print()

    # ── 保存状态 ──
    if dirty:
        save_positions(data)

    # ── 测试模式 ──
    if test_mode:
        print(f"  {C.Y}🧪 测试模式: 以上为模拟数据{C.Z}\n")


# ═══════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════

def main():
    test_mode = "--test" in sys.argv
    run_check(test_mode=test_mode)


if __name__ == "__main__":
    main()
