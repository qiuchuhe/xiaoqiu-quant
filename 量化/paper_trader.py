# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════╗
║   🦀 小秋模拟盘独立交易台 v1.0             ║
║   命令行模拟交易 + 持仓管理                ║
╚══════════════════════════════════════════════╝

用法:
  python paper_trader.py status             查看模拟持仓和资金
  python paper_trader.py buy 600279 4.50    模拟买入(100股, 策略B信号)
  python paper_trader.py sell 600179 4.80   模拟卖出(止盈)
  python paper_trader.py plan               显示今日交易计划
  python paper_trader.py reset              重置模拟盘(3000元初始资金)
  python paper_trader.py log                查看交易日志(最近20条)
  python paper_trader.py pnl                查看累计盈亏统计

参数:
  buy  <代码> <价格> [理由]       模拟买入
  sell <代码> <价格> [理由]       模拟卖出
"""

import sys, os, json
from datetime import datetime

# ─── 编码 ───
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

# ─── 路径 ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, ".monitor_state.json")
POSITION_FILE = os.path.join(BASE_DIR, ".position.json")
LOG_FILE = os.path.join(BASE_DIR, ".trade_log.txt")
PLAN_FILE = os.path.join(BASE_DIR, ".tomorrow_plan.json")

# ─── 配置 ───
INIT_CAPITAL = 3000
FIXED_SHARES = 100
MAX_POSITION = 1
STOP_LOSS_PCT = -5.0
TAKE_PROFIT_PCT = 10.0


# ═══════════════════════════════════════════
# 颜色
# ═══════════════════════════════════════════

class C:
    R = "\033[1;31m"; G = "\033[1;32m"; Y = "\033[1;33m"
    B = "\033[1;36m"; M = "\033[1;35m"; D = "\033[2;37m"; Z = "\033[0m"


# ═══════════════════════════════════════════
# 状态管理
# ═══════════════════════════════════════════

def load_state():
    """加载模拟盘状态"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"positions": {}, "trades": [], "capital": INIT_CAPITAL, "last_signal": {}}


def save_state(state):
    """保存模拟盘状态"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def write_log(msg):
    """写交易日志"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass


# ═══════════════════════════════════════════
# 模拟交易操作
# ═══════════════════════════════════════════

def cmd_buy(code, name, price, reason=""):
    """模拟买入"""
    state = load_state()

    # 检查持仓数量
    if len(state["positions"]) >= MAX_POSITION:
        existing = list(state["positions"].values())
        held_name = existing[0].get("name", "") if existing else ""
        print(f"{C.R}⛔ 已达最大持仓{MAX_POSITION}只 (当前持有: {held_name}){C.Z}")
        print(f"{C.Y}💡 提示: 先卖出再买入, 或使用 paper_trader.py sell{C.Z}")
        return False

    # 固定100股
    shares = FIXED_SHARES
    cost = shares * price * 1.0003  # 含手续费

    if cost > state["capital"]:
        print(f"{C.R}⛔ 资金不足! 需{cost:,.0f}元, 剩余{state['capital']:,.0f}元{C.Z}")
        return False

    # 如果没有传名称，尝试从 .position.json 或 .my_watchlist.json 查找
    if not name or name == code:
        name = lookup_name(code)

    stop_loss_price = round(price * (1 + STOP_LOSS_PCT/100), 2)
    take_profit_price = round(price * (1 + TAKE_PROFIT_PCT/100), 2)

    now = datetime.now()
    state["positions"][code] = {
        "name": name,
        "shares": shares,
        "buy_price": price,
        "buy_date": now.strftime("%Y-%m-%d"),
        "buy_time": now.strftime("%H:%M:%S"),
        "reason": reason or "手动模拟买入",
        "hold_days": 0,
        "high_price": price,
        "cost": cost,
        "stop_loss": stop_loss_price,
        "take_profit": take_profit_price,
    }

    state["capital"] = round(state["capital"] - cost, 2)

    trade = {
        "type": "BUY", "code": code, "name": name,
        "price": price, "shares": shares, "reason": reason or "手动买入",
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    state["trades"].append(trade)

    save_state(state)
    write_log(f"🔴 [模拟买入] {name}({code}) {price:.2f} x {shares}股 = {cost:,.0f}元 "
              f"止损{stop_loss_price} 止盈{take_profit_price} | {reason}")

    print(f"""
{C.G}✅ 模拟买入成功!{C.Z}
  📛 名称: {name}
  🏷️  代码: {code}
  💵 价格: {price:.2f}
  📦 数量: {shares}股
  💰 花费: {cost:,.0f}元
  🛑 止损: {stop_loss_price} ({STOP_LOSS_PCT}%)
  🎯 止盈: {take_profit_price} ({TAKE_PROFIT_PCT}%)
  💳 剩余资金: {state['capital']:,.0f}元
""")
    return True


def cmd_sell(code, price, reason=""):
    """模拟卖出"""
    state = load_state()

    if code not in state["positions"]:
        print(f"{C.R}❌ 持仓中没有 {code}{C.Z}")
        return False

    pos = state["positions"][code]
    name = pos.get("name", "")
    shares = pos["shares"]
    buy_price = pos["buy_price"]
    income = round(shares * price * 0.997, 2)  # 含手续费
    pnl_pct = round((price - buy_price) / buy_price * 100, 2)
    pnl_amount = round(income - pos["cost"], 2)

    state["capital"] = round(state["capital"] + income, 2)

    trade = {
        "type": "SELL", "code": code, "name": name,
        "price": price, "shares": shares, "pnl_pct": pnl_pct,
        "pnl_amount": pnl_amount,
        "reason": reason or "手动卖出",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    state["trades"].append(trade)
    del state["positions"][code]

    save_state(state)

    emoji = "🟢" if pnl_pct > 0 else "🔴"
    write_log(f"{emoji} [模拟卖出] {name}({code}) {price:.2f} x {shares}股 "
              f"盈亏: {pnl_pct:+.2f}% ({pnl_amount:+,.0f}元) | {reason}")

    print(f"""
{C.G if pnl_pct > 0 else C.R}✅ 模拟卖出成功!{C.Z}
  📛 名称: {name}
  🏷️  代码: {code}
  💵 卖价: {price:.2f} (成本: {buy_price:.2f})
  📦 数量: {shares}股
  💰 收入: {income:,.0f}元
  📊 盈亏: {pnl_pct:+.2f}% ({pnl_amount:+,.0f}元)
  💳 当前资金: {state['capital']:,.0f}元
""")
    return True


def cmd_status():
    """查看模拟盘状态"""
    state = load_state()
    positions = state["positions"]
    trades = state.get("trades", [])
    capital = state.get("capital", INIT_CAPITAL)

    # 计算总资产
    total_value = capital
    # 尝试获取实时价格计算市值
    quotes = {}
    if positions:
        try:
            quotes = get_position_quotes(positions)
        except:
            pass

    print(f"""
{C.M}╔══════════════════════════════════════════════╗
║   🦀 小秋模拟盘状态                         ║
╚══════════════════════════════════════════════╝{C.Z}

{C.B}💰 资金状况{C.Z}
  初始资金: {INIT_CAPITAL:,.0f}元
  可用资金: {capital:,.0f}元
  已用资金: {INIT_CAPITAL - capital:,.0f}元
""")

    if positions:
        print(f"{C.Y}📦 当前持仓 ({len(positions)}只){C.Z}")
        print(f"  {'─'*55}")
        for code, pos in positions.items():
            buy_price = pos.get("buy_price", 0)
            shares = pos.get("shares", 0)
            name = pos.get("name", "")
            buy_date = pos.get("buy_date", "")
            q = quotes.get(code)

            if q and q.get("price"):
                price = q["price"]
                pnl_pct = (price - buy_price) / buy_price * 100
                market_value = shares * price
                c = C.R if pnl_pct >= 0 else C.G
                total_value += market_value
                print(f"  {name}({code}) | 成本{buy_price:.2f} → 现价{price:.2f} "
                      f"| {c}{pnl_pct:+.2f}%{C.Z} | 市值{market_value:,.0f}")
                print(f"    买入: {buy_date} | {shares}股 | "
                      f"止损{pos.get('stop_loss','?'):.2f} | 止盈{pos.get('take_profit','?'):.2f}")
            else:
                total_value += shares * buy_price
                print(f"  {name}({code}) | 成本{buy_price:.2f} x {shares}股 "
                      f"| 买入: {buy_date}")
                print(f"    止损{pos.get('stop_loss','?'):.2f} | 止盈{pos.get('take_profit','?'):.2f}")
        print(f"  {'─'*55}")
    else:
        print(f"{C.D}📦 当前空仓{C.Z}")

    total_pnl = total_value - INIT_CAPITAL
    total_pnl_pct = total_pnl / INIT_CAPITAL * 100
    c = C.R if total_pnl >= 0 else C.G

    print(f"""
{C.B}📊 总体统计{C.Z}
  总资产: {total_value:,.0f}元
  累计盈亏: {c}{total_pnl:+,.0f}元 ({total_pnl_pct:+.2f}%){C.Z}
  累计交易: {len(trades)}笔
""")

    # 最近5笔交易
    if trades:
        print(f"{C.D}📜 最近交易:{C.Z}")
        for t in trades[-5:]:
            ttype = "🔴买" if t["type"] == "BUY" else "🟢卖"
            pnl = f" {t.get('pnl_pct', 0):+.2f}%" if t["type"] == "SELL" else ""
            print(f"  {t['time']} {ttype} {t.get('name','')}({t.get('code','')}) "
                  f"{t.get('price',0):.2f} x {t.get('shares',0)}股{pnl}")

    print()


def cmd_plan():
    """显示交易计划"""
    if not os.path.exists(PLAN_FILE):
        print(f"{C.Y}📅 暂无明日计划文件，请先运行 config_tomorrow.py{C.Z}")
        return

    with open(PLAN_FILE, encoding="utf-8") as f:
        plan = json.load(f)

    print(f"""
{C.M}╔══════════════════════════════════════════════╗
║   📅 明日监控计划                           ║
╚══════════════════════════════════════════════╝{C.Z}
""")

    stocks = plan.get("stocks", plan.get("watch", []))
    if stocks:
        for i, s in enumerate(stocks[:15], 1):
            code = s.get("code", "")
            name = s.get("name", "")
            strategy = s.get("strategy", "")
            trigger = s.get("trigger", s.get("reason", ""))
            print(f"  {i}. {name}({code}) | 策略:{strategy} | {trigger}")
    else:
        plan_str = json.dumps(plan, ensure_ascii=False, indent=2)
        print(plan_str[:500])


def cmd_reset():
    """重置模拟盘"""
    print(f"{C.R}⚠️  将清空所有模拟持仓和交易记录!{C.Z}")
    print(f"确认重置? (输入 yes 继续)")
    if input("  > ").strip().lower() != "yes":
        print("已取消")
        return

    fresh = {"positions": {}, "trades": [], "capital": INIT_CAPITAL, "last_signal": {}}
    save_state(fresh)
    write_log("🔄 [重置] 模拟盘已重置, 初始资金3000元")
    print(f"{C.G}✅ 模拟盘已重置, 初始资金 {INIT_CAPITAL} 元{C.Z}")


def cmd_log():
    """查看交易日志"""
    if not os.path.exists(LOG_FILE):
        print(f"{C.Y}📜 暂无交易日志{C.Z}")
        return

    with open(LOG_FILE, encoding="utf-8") as f:
        lines = f.readlines()

    print(f"\n{C.M}📜 交易日志 (最近20条){C.Z}\n")
    for line in lines[-20:]:
        print(f"  {line.strip()}")
    print()


def cmd_pnl():
    """累计盈亏统计"""
    state = load_state()
    trades = state.get("trades", [])
    sell_trades = [t for t in trades if t.get("type") == "SELL"]

    if not sell_trades:
        print(f"{C.Y}📊 暂无已完成交易，无法统计盈亏{C.Z}")
        return

    total_pnl = sum(t.get("pnl_amount", 0) for t in sell_trades)
    win_trades = [t for t in sell_trades if t.get("pnl_pct", 0) > 0]
    lose_trades = [t for t in sell_trades if t.get("pnl_pct", 0) <= 0]

    avg_win = sum(t.get('pnl_pct',0) for t in win_trades) / len(win_trades) if win_trades else 0
    avg_lose = sum(t.get('pnl_pct',0) for t in lose_trades) / len(lose_trades) if lose_trades else 0

    print(f"""
{C.M}╔══════════════════════════════════════════════╗
║   📊 模拟盘盈亏统计                         ║
╚══════════════════════════════════════════════╝{C.Z}

  总交易: {len(sell_trades)}笔
  {C.R}盈利: {len(win_trades)}笔{C.Z} | {C.G}亏损: {len(lose_trades)}笔{C.Z}
  胜率: {len(win_trades)/len(sell_trades)*100:.1f}%
  累计盈亏: {C.R if total_pnl>=0 else C.G}{total_pnl:+,.0f}元{C.Z}

  平均盈利: {avg_win:+.2f}% ({len(win_trades)}笔)
  平均亏损: {avg_lose:+.2f}% ({len(lose_trades)}笔)
""")


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def lookup_name(code):
    """从各种文件中查找股票名称"""
    # 先从 .my_watchlist.json 找
    watchlist_file = os.path.join(BASE_DIR, ".my_watchlist.json")
    if os.path.exists(watchlist_file):
        with open(watchlist_file, encoding="utf-8") as f:
            wl = json.load(f)
        raw = code
        for prefix in ["sh", "sz"]:
            if f"{prefix}{raw}" in wl:
                return wl[f"{prefix}{raw}"]
        if raw in wl:
            return wl[raw]

    # 再从 .position.json 找
    pos_file = os.path.join(BASE_DIR, ".position.json")
    if os.path.exists(pos_file):
        with open(pos_file, encoding="utf-8") as f:
            data = json.load(f)
        for h in data.get("holdings", []):
            if h.get("code") == code:
                return h.get("name", code)

    return code


def get_position_quotes(positions):
    """获取持仓实时行情"""
    import urllib.request
    import re

    codes = []
    for code in positions:
        raw = code
        prefix = "sh" if raw.startswith(("6","9")) else "sz"
        codes.append(f"{prefix}{raw}")

    url = "http://qt.gtimg.cn/q=" + ",".join(codes)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("gbk")
    except:
        return {}

    result = {}
    for line in raw.strip().split(";\n"):
        m = re.search(r'="(.+)"$', line.strip())
        if not m: continue
        f = m.group(1).split("~")
        if len(f) < 40: continue
        try:
            result[f[2]] = {
                "name": f[1], "price": float(f[3]),
                "pct": (float(f[3]) - float(f[4])) / float(f[4]) * 100 if f[4] else None,
            }
        except:
            continue
    return result


# ═══════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════

def print_usage():
    print(f"""
{C.M}╔══════════════════════════════════════════════╗
║   🦀 小秋模拟盘独立交易台 v1.0             ║
╚══════════════════════════════════════════════╝{C.Z}

用法:
  python paper_trader.py status             查看模拟持仓和资金
  python paper_trader.py buy <代码> <价格> [理由]
  python paper_trader.py sell <代码> <价格> [理由]
  python paper_trader.py plan               查看交易计划
  python paper_trader.py reset              重置模拟盘
  python paper_trader.py log                查看交易日志
  python paper_trader.py pnl                盈亏统计

示例:
  python paper_trader.py buy 600279 4.50 "策略B多头信号"
  python paper_trader.py sell 600179 4.80 "止盈+10%"
  python paper_trader.py buy 002568 18.50
""")


def main():
    if len(sys.argv) < 2:
        print_usage()
        return

    cmd = sys.argv[1].lower()

    if cmd == "status":
        cmd_status()

    elif cmd == "buy":
        if len(sys.argv) < 4:
            print(f"{C.R}用法: python paper_trader.py buy <代码> <价格> [理由]{C.Z}")
            return
        code = sys.argv[2]
        try:
            price = float(sys.argv[3])
        except ValueError:
            print(f"{C.R}❌ 价格格式错误{C.Z}")
            return
        reason = sys.argv[4] if len(sys.argv) > 4 else ""
        cmd_buy(code, "", price, reason)

    elif cmd == "sell":
        if len(sys.argv) < 4:
            print(f"{C.R}用法: python paper_trader.py sell <代码> <价格> [理由]{C.Z}")
            return
        code = sys.argv[2]
        try:
            price = float(sys.argv[3])
        except ValueError:
            print(f"{C.R}❌ 价格格式错误{C.Z}")
            return
        reason = sys.argv[4] if len(sys.argv) > 4 else ""
        cmd_sell(code, price, reason)

    elif cmd == "plan":
        cmd_plan()

    elif cmd == "reset":
        cmd_reset()

    elif cmd == "log":
        cmd_log()

    elif cmd == "pnl":
        cmd_pnl()

    else:
        print(f"{C.R}❌ 未知命令: {cmd}{C.Z}")
        print_usage()


if __name__ == "__main__":
    main()
