# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════╗
║   🦀 小秋量化监控系统 v1.0                   ║
║   双策略实时监控 + 自动交易触发               ║
║   券商: 国信证券 → 同花顺下单端              ║
╚══════════════════════════════════════════════╝

用法:
  python xiaoqiu_monitor.py                实盘监控(同花顺必须开着)
  python xiaoqiu_monitor.py --dry          模拟盘模式(不实际下单,只看信号)
  python xiaoqiu_monitor.py --once         单次扫描,不循环
  python xiaoqiu_monitor.py --interval 120 每120秒扫描一次(默认60秒)

策略:
  策略A: MA5金叉买入 / MA5死叉卖出
  策略B: 均线多头排列+温和放量 → 次日开盘买入 → 持有N天卖出
  通用止损: 持仓亏损超5% → 次日开盘卖出
  通用止盈: 持仓盈利超10% → 次日开盘卖出
"""

import sys, time, os, json, re
from datetime import datetime, timedelta
from collections import OrderedDict

# ─── 编码 ───
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

# ─── HTTP ───
import urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

def http_get(url, timeout=10, decode="gbk"):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(decode)


# ═══════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, ".monitor_state.json")
LOG_FILE = os.path.join(BASE_DIR, ".trade_log.txt")
XIADAN_PATH = r"D:\下载\同花顺\同花顺\xiadan.exe"

# 监控标的
WATCH_STOCKS = [
    {"code": "002351", "name": "漫步者",   "hold_days": 1,  "max_price": 11.60, "strategy": "B"},
    {"code": "002568", "name": "百润股份", "hold_days": 0,  "max_price": 20.50, "strategy": "A"},
    {"code": "600020", "name": "中原高速", "hold_days": 5,  "max_price": 4.20,  "strategy": "B"},
]

# 风控参数
STOP_LOSS_PCT = -5.0      # 止损线
TAKE_PROFIT_PCT = 10.0    # 止盈线
MAX_POSITION = 1          # 3000本金只持1只
FIXED_SHARES = 100        # 固定每次100股(小资金)
INIT_CAPITAL = 3000       # 初始资金(模拟盘用)

# 交易时间
MARKET_OPEN = "09:30"
MARKET_CLOSE = "15:00"


# ═══════════════════════════════════════════
# 颜色 & 日志
# ═══════════════════════════════════════════

class C:
    R = "\033[1;31m"; G = "\033[1;32m"; Y = "\033[1;33m"
    B = "\033[1;36m"; M = "\033[1;35m"; D = "\033[2;37m"; Z = "\033[0m"

def log(msg, level="INFO"):
    now = datetime.now().strftime("%H:%M:%S")
    line = f"[{now}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass


# ═══════════════════════════════════════════
# K线 & 指标
# ═══════════════════════════════════════════

def get_kline(code, days=120):
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
    if len(closes) < n: return [None]*len(closes)
    r = [None]*(n-1)
    for i in range(n-1, len(closes)):
        r.append(sum(closes[i-n+1:i+1])/n)
    return r


# ═══════════════════════════════════════════
# 行情获取
# ═══════════════════════════════════════════

def parse_tx(raw):
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
# 策略信号检测
# ═══════════════════════════════════════════

def check_strategy_A(kl):
    """策略A: MA5金叉/死叉信号"""
    if not kl or len(kl) < 25:
        return None
    closes = [k["close"] for k in kl]
    ma5 = calc_ma(closes, 5)
    ma20 = calc_ma(closes, 20)

    if None in (ma5[-1], ma20[-1], ma5[-2], ma20[-2]):
        return None

    if ma5[-2] <= ma20[-2] and ma5[-1] > ma20[-1]:
        return "BUY"        # 金叉 → 买入
    elif ma5[-2] >= ma20[-2] and ma5[-1] < ma20[-1]:
        return "SELL"       # 死叉 → 卖出
    return None


def check_strategy_B(kl):
    """策略B: 均线多头排列+温和放量 → 买入信号"""
    if not kl or len(kl) < 35:
        return None

    closes = [k["close"] for k in kl]
    volumes = [k["volume"] for k in kl]

    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma15 = calc_ma(closes, 15)
    ma30 = calc_ma(closes, 30)

    if None in (ma5[-1], ma10[-1], ma15[-1], ma30[-1]):
        return None
    if not (ma5[-1] > ma10[-1] > ma15[-1] > ma30[-1]):
        return None

    # 今日涨幅 1%-5%
    if closes[-2] <= 0: return None
    pct = (closes[-1] - closes[-2]) / closes[-2] * 100
    if pct < 1 or pct > 5:
        return None

    # 温和放量 1.2x-3x
    if len(volumes) < 6: return None
    avg_vol = sum(volumes[-6:-1]) / 5
    if avg_vol <= 0: return None
    vol_ratio = volumes[-1] / avg_vol
    if vol_ratio < 1.2 or vol_ratio > 3.0:
        return None

    # 股价 < 25
    if closes[-1] >= 25:
        return None

    return "BUY"


# ═══════════════════════════════════════════
# 状态管理
# ═══════════════════════════════════════════

def load_state():
    """加载持仓和信号状态"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"positions": {}, "trades": [], "capital": INIT_CAPITAL, "last_signal": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════
# 模拟交易引擎
# ═══════════════════════════════════════════

class SimTrader:
    """模拟盘交易引擎"""

    def __init__(self, state):
        self.state = state

    def buy(self, code, name, price, reason, hold_days=0):
        pos = self.state["positions"]
        if len(pos) >= MAX_POSITION:
            log(f"⛔ 已达最大持仓{MAX_POSITION}只, 跳过买入{name}", "WARN")
            return False

        # 固定100股(小资金模式)
        shares = FIXED_SHARES
        cost = shares * price * 1.0003
        if cost > self.state["capital"]:
            log(f"⛔ 资金不足买入{name}: 需{cost:,.0f} 剩余{self.state['capital']:,.0f}", "WARN")
            return False

        cost = shares * price * 1.0003  # 手续费
        pos[code] = {
            "name": name,
            "shares": shares,
            "buy_price": price,
            "buy_date": datetime.now().strftime("%Y-%m-%d"),
            "buy_time": datetime.now().strftime("%H:%M:%S"),
            "reason": reason,
            "hold_days": hold_days,
            "high_price": price,  # 持仓期间最高价(移动止盈用)
            "cost": cost,
        }
        self.state["capital"] = self.state["capital"] - cost
        self.state["trades"].append({
            "type": "BUY", "code": code, "name": name,
            "price": price, "shares": shares, "reason": reason,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        save_state(self.state)
        log(f"🔴 [模拟买入] {name}({code}) {price:.2f} x {shares}股 = {cost:,.0f}元 "
            f"原因: {reason}")
        return True

    def sell(self, code, price, reason):
        pos = self.state["positions"]
        if code not in pos:
            return False
        p = pos[code]
        shares = p["shares"]
        income = shares * price * 0.997  # 手续费
        pnl_pct = (price - p["buy_price"]) / p["buy_price"] * 100

        self.state["capital"] += income
        self.state["trades"].append({
            "type": "SELL", "code": code, "name": p["name"],
            "price": price, "shares": shares, "pnl_pct": round(pnl_pct, 2),
            "reason": reason,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        del pos[code]
        save_state(self.state)

        emoji = "🟢" if pnl_pct > 0 else "🔴"
        log(f"{emoji} [模拟卖出] {p['name']}({code}) {price:.2f} x {shares}股 "
            f"盈亏: {pnl_pct:+.2f}% 原因: {reason}")
        return True

    def show_status(self):
        state = self.state
        total_value = state["capital"]
        for p in state["positions"].values():
            total_value += p["shares"] * p["buy_price"]  # 简化用买入价
        total_pnl = total_value - INIT_CAPITAL
        pnl_pct = total_pnl / INIT_CAPITAL * 100

        print(f"\n  {'─'*55}")
        print(f"  💰 资金: {state['capital']:,.0f} | 总资产: {total_value:,.0f} | "
              f"{C.R if total_pnl>=0 else C.G}总盈亏: {total_pnl:+,.0f} ({pnl_pct:+.2f}%){C.Z}")
        print(f"  📦 持仓: {len(state['positions'])}只")
        for code, p in state["positions"].items():
            pnl = (p.get("current_price", p["buy_price"]) - p["buy_price"]) / p["buy_price"] * 100
            c = C.R if pnl >= 0 else C.G
            print(f"     {p['name']}({code}) 成本{p['buy_price']:.2f} "
                  f"x{p['shares']}股 {c}{pnl:+.2f}%{C.Z}")
        print(f"  {'─'*55}")


# ═══════════════════════════════════════════
# 实盘交易接口
# ═══════════════════════════════════════════

class RealTrader:
    """实盘交易接口(通过同花顺)"""

    def __init__(self):
        self.user = None

    def connect(self):
        try:
            import easytrader
            self.user = easytrader.use("ths")
            self.user.connect(XIADAN_PATH)
            log(f"✅ 已连接同花顺下单端")
            return True
        except Exception as e:
            log(f"❌ 连接同花顺失败: {e}", "ERROR")
            return False

    def buy(self, code, name, price, amount=100):
        if not self.user: return False
        try:
            self.user.buy(code, price=price, amount=amount)
            log(f"🔴 [实盘买入] {name}({code}) {price:.2f} x {amount}股")
            return True
        except Exception as e:
            log(f"❌ 买入失败 {name}: {e}", "ERROR")
            return False

    def sell(self, code, name, price, amount=100):
        if not self.user: return False
        try:
            self.user.sell(code, price=price, amount=amount)
            log(f"🟢 [实盘卖出] {name}({code}) {price:.2f} x {amount}股")
            return True
        except Exception as e:
            log(f"❌ 卖出失败 {name}: {e}", "ERROR")
            return False


# ═══════════════════════════════════════════
# 主监控循环
# ═══════════════════════════════════════════

def is_market_time():
    """检查是否在交易时间"""
    now = datetime.now()
    if now.weekday() >= 5:  # 周末
        return False
    t = now.strftime("%H:%M")
    return MARKET_OPEN <= t <= MARKET_CLOSE


def monitor_loop(dry_run=True, once=False, interval=60):
    """主监控循环"""
    state = load_state()

    if dry_run:
        trader = SimTrader(state)
        log(f"🟡 模拟盘模式 (不实际下单)")
    else:
        trader = RealTrader()
        if not trader.connect():
            log("❌ 无法连接交易端, 退出", "ERROR")
            return
        log(f"🔴 实盘模式 !!!")

    log(f"📋 监控 {len(WATCH_STOCKS)} 只票: "
        f"{', '.join(s['name'] for s in WATCH_STOCKS)}")
    log(f"📊 策略A: 双均线金叉/死叉 | 策略B: 多头排列+温和放量")
    log(f"🛑 止损: {STOP_LOSS_PCT}% | 🎯 止盈: {TAKE_PROFIT_PCT}%")
    log(f"⏱️  扫描间隔: {interval}s")
    log(f"{'═'*55}")

    scan_count = 0

    try:
        while True:
            scan_count += 1
            now = datetime.now()
            in_market = is_market_time()

            if not in_market and not once:
                log(f"{C.D}⏸️  非交易时间, 等待中...{C.Z}")
                time.sleep(60)
                continue

            log(f"\n{C.B}── 扫描 #{scan_count} {now.strftime('%H:%M:%S')} ──{C.Z}")

            # 1. 拉取实时行情
            tx_codes = []
            for s in WATCH_STOCKS:
                raw = s["code"]
                prefix = "sh" if raw.startswith(("6","9")) else "sz"
                tx_codes.append(f"{prefix}{raw}")

            quotes = get_quotes(tx_codes)
            quote_map = {q["code"]: q for q in quotes}

            # 2. 逐只分析
            for stock in WATCH_STOCKS:
                code = stock["code"]
                name = stock["name"]
                quote = quote_map.get(code)
                strategy = stock.get("strategy", "B")
                hold_days = stock.get("hold_days", 0)

                if not quote or quote.get("price") is None:
                    log(f"  {C.D}{name}({code}) 无行情数据{C.Z}")
                    continue

                price = quote["price"]
                pct = quote.get("pct", 0)
                turnover = quote.get("turnover", 0)

                # 显示当前状态
                pct_s = f"{C.R}{pct:+.2f}%{C.Z}" if pct and pct > 0 else \
                        f"{C.G}{pct:+.2f}%{C.Z}" if pct and pct < 0 else f"{pct:+.2f}%"
                log(f"  {name}({code}) {price:.2f} {pct_s} 换手{turnover:.2f}%")

                # 3. 检查持仓止损/止盈
                pos = state["positions"].get(code)
                if pos:
                    # 更新当前价
                    pos["current_price"] = price
                    # 更新最高价
                    if price > pos.get("high_price", 0):
                        pos["high_price"] = price

                    pnl_pct = (price - pos["buy_price"]) / pos["buy_price"] * 100

                    # 止损
                    if pnl_pct <= STOP_LOSS_PCT:
                        log(f"  {C.R}⚠️ 触发止损! {name} 亏损 {pnl_pct:.2f}%{C.Z}")
                        trader.sell(code, price, f"止损({pnl_pct:.2f}%)")

                    # 止盈
                    elif pnl_pct >= TAKE_PROFIT_PCT:
                        log(f"  {C.Y}🎯 触发止盈! {name} 盈利 {pnl_pct:.2f}%{C.Z}")
                        trader.sell(code, price, f"止盈({pnl_pct:.2f}%)")

                    # 移动止盈(从高点回撤3%)
                    elif pos.get("high_price", 0) > pos["buy_price"] * 1.05:
                        drawdown = (price - pos["high_price"]) / pos["high_price"] * 100
                        if drawdown <= -3:
                            log(f"  {C.Y}📉 移动止盈! {name} 从高点回撤{drawdown:.2f}%{C.Z}")
                            trader.sell(code, price, f"移动止盈(回撤{drawdown:.2f}%)")

                    # 持有天数到期(策略B)
                    if hold_days > 0 and pos.get("hold_days", 0) > 0:
                        held = (datetime.now() - datetime.strptime(
                            pos["buy_date"], "%Y-%m-%d")).days
                        if held >= hold_days:
                            log(f"  {C.B}⏰ 持有到期! {name} 已持{held}天{C.Z}")
                            trader.sell(code, price, f"持有{hold_days}天到期")

                    continue  # 已持仓, 跳过买入信号

                # 4. 买入信号检测
                kl = get_kline(code, days=60)
                if not kl:
                    continue

                signal = None
                signal_reason = ""

                if strategy == "A":
                    sig = check_strategy_A(kl)
                    if sig == "BUY":
                        signal = "BUY"
                        signal_reason = "策略A: MA5金叉"
                    elif sig == "SELL":
                        pass  # 卖信号只在持仓时处理

                elif strategy == "B":
                    sig = check_strategy_B(kl)
                    if sig == "BUY":
                        signal = "BUY"
                        signal_reason = f"策略B: 多头排列+温和放量(持有{hold_days}天)"

                # 防重复: 同一信号10分钟内不重复触发
                last_sig = state["last_signal"].get(code, {})
                last_time = last_sig.get("time", "")
                if last_time:
                    dt = (datetime.now() - datetime.strptime(last_time, "%H:%M:%S")).seconds
                    if dt < 600 and last_sig.get("type") == signal:
                        signal = None

                if signal == "BUY":
                    state["last_signal"][code] = {
                        "type": signal, "time": now.strftime("%H:%M:%S")
                    }
                    trader.buy(code, name, price, signal_reason, hold_days)

            # 5. 显示状态
            if dry_run and scan_count % 5 == 0:
                trader.show_status()

            if once:
                break

            log(f"{C.D}下次扫描: {interval}秒后{C.Z}")
            time.sleep(interval)

    except KeyboardInterrupt:
        log(f"\n{C.Y}👋 监控结束{C.Z}")
        if dry_run:
            trader.show_status()
            save_state(state)


# ═══════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════

def main():
    dry_run = "--dry" in sys.argv or "--sim" in sys.argv
    once = "--once" in sys.argv
    interval = 60

    for i, arg in enumerate(sys.argv):
        if arg == "--interval" and i+1 < len(sys.argv):
            interval = int(sys.argv[i+1])

    print(f"""
{C.M}╔══════════════════════════════════════════════╗
║   🦀 小秋量化监控系统 v1.0                   ║
║   双策略实时监控 + 自动交易触发               ║
╚══════════════════════════════════════════════╝{C.Z}

  模式: {C.Y if dry_run else C.R}{'模拟盘(安全)' if dry_run else '实盘(真实交易!)'}{C.Z}
  间隔: {interval}秒
  标的: {len(WATCH_STOCKS)} 只
  策略A: 双均线金叉/死叉
  策略B: 均线多头排列+温和放量
""")

    if not dry_run:
        print(f"  {C.R}⚠️  实盘模式! 将使用真金白银!{C.Z}")
        print(f"  {C.R}确认要继续吗? (输入 yes 继续){C.Z}")
        if input("  > ").strip().lower() != "yes":
            print("  已取消")
            return

    monitor_loop(dry_run=dry_run, once=once, interval=interval)


if __name__ == "__main__":
    main()
