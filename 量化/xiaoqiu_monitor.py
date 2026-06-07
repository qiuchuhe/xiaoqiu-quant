# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════╗
║   🦀 小秋持仓监控 v2.0                       ║
║   对接策略一：均线多头+温和放量               ║
║   盯持仓 → 四级卖出信号 → 报警/自动卖       ║
╚══════════════════════════════════════════════╝

用法:
  python xiaoqiu_monitor.py                   模拟盘监控
  python xiaoqiu_monitor.py --once            单次检查
  python xiaoqiu_monitor.py --interval 120    每120秒扫描
  python xiaoqiu_monitor.py --live            实盘模式(同花顺必须开着)

卖出信号（策略一）:
  🔴 优先级1: 亏损 ≥ 5% → 硬止损
  🟡 优先级2: MA5 下穿 MA10 → 趋势破坏
  🟢 优先级3: 盈利 ≥ 10% → 止盈
  🔵 优先级4: 量比>2 且 涨幅<1% → 放量滞涨
"""

import sys, time, os, json, re
from datetime import datetime

if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

import urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

def http_get(url, timeout=10, decode="gbk"):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(decode)

# ─── 路径 ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGY1_DIR = os.path.join(os.path.dirname(BASE_DIR), "策略量化", "策略1")
POSITION_FILE = os.path.join(BASE_DIR, ".position.json")
LOG_FILE = os.path.join(BASE_DIR, ".trade_log.txt")

# ─── 加载策略一参数 ───
sys.path.insert(0, STRATEGY1_DIR)
try:
    from config import POSITION as S1_POS, SELL_SIGNALS
except ImportError:
    S1_POS = {"stop_loss_pct": -5.0, "take_profit_pct": 10.0, "fixed_shares": 100}
    SELL_SIGNALS = []

# ═══════════════════════════════════════════
# 颜色 & 日志
# ═══════════════════════════════════════════

class C:
    R = "\033[1;31m"; G = "\033[1;32m"; Y = "\033[1;33m"
    B = "\033[1;36m"; M = "\033[1;35m"; D = "\033[2;37m"; Z = "\033[0m"

def log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    line = f"[{now}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except: pass


# ═══════════════════════════════════════════
# 持仓管理
# ═══════════════════════════════════════════

def load_positions():
    """从 .position.json 读取持仓"""
    if os.path.exists(POSITION_FILE):
        with open(POSITION_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    return []

def save_positions(positions):
    with open(POSITION_FILE, "w", encoding="utf-8") as f:
        json.dump(positions, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════
# 行情 & K线
# ═══════════════════════════════════════════

def get_quotes(codes):
    """腾讯批量行情"""
    results = []
    for i in range(0, len(codes), 50):
        batch = codes[i:i+50]
        try:
            url = "http://qt.gtimg.cn/q=" + ",".join(batch)
            raw = http_get(url, timeout=10)
            for line in raw.strip().split(";\n"):
                m = re.search(r'="(.+)"$', line.strip())
                if not m: continue
                f = m.group(1).split("~")
                if len(f) < 40: continue
                try:
                    price = float(f[3]) if f[3] else 0
                    preclose = float(f[4]) if f[4] else 0
                    pct = ((price-preclose)/preclose*100) if (price and preclose) else 0
                    results.append({
                        "code": f[2], "name": f[1], "price": price,
                        "pct": round(pct,2), "preclose": preclose,
                        "open": float(f[5]) if f[5] else 0,
                        "volume": float(f[6]) if f[6] else 0,
                        "high": float(f[33]) if len(f)>33 and f[33] else 0,
                        "low": float(f[34]) if len(f)>34 and f[34] else 0,
                        "turnover": float(f[38]) if len(f)>38 and f[38] else 0,
                    })
                except: continue
        except: continue
    return results

def get_kline(code, days=60):
    raw = str(code).zfill(6)
    m = "sh" if raw.startswith(("6","9")) else "sz"
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={m}{raw},day,,,{days},qfq"
    try:
        data = json.loads(http_get(url, decode="utf-8"))
        kl = data["data"][f"{m}{raw}"].get("day",[]) or \
             data["data"][f"{m}{raw}"].get("qfqday",[])
        return [{"date":it[0],"open":float(it[1]),"close":float(it[2]),
                 "high":float(it[3]),"low":float(it[4]),"volume":float(it[5])}
                for it in kl] if kl else None
    except: return None

def calc_ma(values, period):
    if len(values) < period: return [None]*len(values)
    r = [None]*(period-1)
    for i in range(period-1, len(values)):
        r.append(sum(values[i-period+1:i+1])/period)
    return r


# ═══════════════════════════════════════════
# 卖出信号检测（策略一）
# ═══════════════════════════════════════════

def check_sell_signals(pos, quote, kl):
    """
    检测策略一的四个卖出信号，按优先级返回第一个触发的。
    返回: dict{signal_id, name, action, detail} 或 None
    """
    code = pos.get("code", "")
    cost = pos.get("cost", pos.get("buy_price", 0))
    price = quote.get("price", 0)
    if price <= 0 or cost <= 0:
        return None

    pnl_pct = (price - cost) / cost * 100

    # 信号1: 硬止损 -5%
    if pnl_pct <= S1_POS["stop_loss_pct"]:
        return {
            "id": "hard_stop",
            "name": "硬止损",
            "priority": 1,
            "detail": f"亏损{pnl_pct:.2f}%（阈值{S1_POS['stop_loss_pct']}%）",
            "action": "次日开盘无条件卖出",
        }

    # 信号2: MA5下穿MA10
    if kl and len(kl) >= 15:
        closes = [k["close"] for k in kl]
        ma5 = calc_ma(closes, 5)
        ma10 = calc_ma(closes, 10)
        if None not in (ma5[-1], ma10[-1], ma5[-2], ma10[-2]):
            if ma5[-2] >= ma10[-2] and ma5[-1] < ma10[-1]:
                return {
                    "id": "ma5_cross_ma10",
                    "name": "短期趋势破坏",
                    "priority": 2,
                    "detail": f"MA5({ma5[-1]:.2f}) 下穿 MA10({ma10[-1]:.2f})",
                    "action": "次日开盘卖出",
                }

    # 信号3: 止盈 +10%
    if pnl_pct >= S1_POS["take_profit_pct"]:
        return {
            "id": "take_profit",
            "name": "止盈",
            "priority": 3,
            "detail": f"盈利{pnl_pct:.2f}%（阈值+{S1_POS['take_profit_pct']}%）",
            "action": "次日开盘卖出",
        }

    # 信号4: 放量滞涨
    if kl and len(kl) >= 6:
        volumes = [k["volume"] for k in kl]
        avg_vol_5 = sum(volumes[-6:-1]) / 5
        if avg_vol_5 > 0:
            vol_ratio = volumes[-1] / avg_vol_5
            gain = quote.get("pct", 0)
            if vol_ratio > 2 and gain < 1:
                return {
                    "id": "volume_spike_stall",
                    "name": "放量滞涨",
                    "priority": 4,
                    "detail": f"量比{vol_ratio:.1f}x 但涨幅仅{gain:.2f}%",
                    "action": "当日卖出",
                }

    return None


# ═══════════════════════════════════════════
# 模拟交易
# ═══════════════════════════════════════════

def sim_sell(position, quote, signal):
    """模拟卖出"""
    code = position.get("code", "")
    name = position.get("name", "")
    cost = position.get("cost", position.get("buy_price", 0))
    price = quote.get("price", 0)
    shares = position.get("shares", S1_POS.get("fixed_shares", 100))
    pnl_pct = (price - cost) / cost * 100 if cost > 0 else 0

    emoji = "🔴" if pnl_pct < 0 else "🟢"
    log(f"{emoji} [卖出信号] {name}({code}) "
        f"成本{cost:.2f} → 现价{price:.2f} "
        f"盈亏{C.R if pnl_pct<0 else C.G}{pnl_pct:+.2f}%{C.Z}")
    log(f"  触发: {C.R}{signal['name']}{C.Z} — {signal['detail']}")
    log(f"  操作: {signal['action']}")

    # 写交易日志
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"卖出信号 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"标的: {name}({code})\n")
            f.write(f"成本: {cost:.2f} | 现价: {price:.2f} | 盈亏: {pnl_pct:+.2f}%\n")
            f.write(f"信号: {signal['name']} | {signal['detail']}\n")
            f.write(f"操作: {signal['action']}\n")
            f.write(f"{'='*50}\n")
    except: pass


# ═══════════════════════════════════════════
# 主监控
# ═══════════════════════════════════════════

def is_market_time():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.strftime("%H:%M")
    return "09:30" <= t <= "15:00"


def monitor_loop(once=False, interval=60):
    """持仓监控循环"""
    positions = load_positions()

    if not positions:
        log(f"{C.Y}📭 当前无持仓，无需监控{C.Z}")
        log(f"{C.D}💡 先运行策略一扫描选股：python 策略量化/策略1/scanner.py{C.Z}")
        return

    log(f"{C.B}📊 监控 {len(positions)} 只持仓{C.Z}")
    for p in positions:
        log(f"   {p.get('name','')}({p.get('code','')}) 成本{p.get('cost',p.get('buy_price',0)):.2f}")

    log(f"{C.D}卖出信号: 硬止损{S1_POS['stop_loss_pct']}% | 死叉 | 止盈+{S1_POS['take_profit_pct']}% | 放量滞涨{C.Z}")
    log(f"{'═'*55}")

    scan_count = 0
    alerted = set()  # 已报警的股票，避免重复

    try:
        while True:
            scan_count += 1
            now = datetime.now()

            if not is_market_time() and not once:
                if scan_count == 1:
                    log(f"{C.D}⏸️  非交易时间，等待中...{C.Z}")
                time.sleep(60)
                continue

            # 重新加载持仓（可能被外部更新）
            positions = load_positions()
            if not positions:
                log(f"{C.Y}📭 持仓已清空{C.Z}")
                break

            # 获取行情
            tx_codes = []
            for p in positions:
                raw = str(p.get("code","")).zfill(6)
                prefix = "sh" if raw.startswith(("6","9")) else "sz"
                tx_codes.append(f"{prefix}{raw}")

            quotes = get_quotes(tx_codes)
            quote_map = {q["code"]: q for q in quotes}

            # 逐只检查
            for pos in positions:
                code = str(pos.get("code", "")).zfill(6)
                name = pos.get("name", "")
                quote = quote_map.get(code)

                if not quote or quote.get("price", 0) <= 0:
                    continue

                price = quote["price"]
                cost = pos.get("cost", pos.get("buy_price", 0))
                pnl_pct = (price - cost) / cost * 100 if cost > 0 else 0

                # 状态显示（每5次扫描显示一次）
                if scan_count % 5 == 0:
                    pnl_c = C.R if pnl_pct < 0 else C.G
                    log(f"  {name}({code}) {price:.2f} {pnl_c}{pnl_pct:+.2f}%{C.Z}")

                # K线（用于MA交叉和放量滞涨检测）
                kl = get_kline(code, days=30)

                # 检测卖出信号
                signal = check_sell_signals(pos, quote, kl)
                if signal and code not in alerted:
                    sim_sell(pos, quote, signal)
                    alerted.add(code)

                    # 自动从持仓移除（模拟盘）
                    positions = [p for p in positions if str(p.get("code","")).zfill(6) != code]
                    save_positions(positions)

            if once:
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        log(f"\n{C.Y}👋 监控结束{C.Z}")


def main():
    once = "--once" in sys.argv
    interval = 60

    for i, arg in enumerate(sys.argv):
        if arg == "--interval" and i+1 < len(sys.argv):
            try: interval = int(sys.argv[i+1])
            except: pass

    print(f"""
{C.M}╔══════════════════════════════════════════════╗
║  🦀 小秋持仓监控 v2.0                          ║
║  对接策略一：均线多头+温和放量                  ║
╚══════════════════════════════════════════════╝{C.Z}

  持仓文件: .position.json
  卖出信号: 🔴硬止损{S1_POS['stop_loss_pct']}% 🟡MA5死叉 🟢止盈+{S1_POS['take_profit_pct']}% 🔵放量滞涨
  扫描间隔: {interval}秒
""")

    monitor_loop(once=once, interval=interval)


if __name__ == "__main__":
    main()
