# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════╗
║   🦀 小秋止损止盈预警守护 v1.0              ║
║   三级预警 + 桌面通知 + 日志记录            ║
╚══════════════════════════════════════════════╝

用法:
  python alert_daemon.py                 前台持续监控(默认30s间隔)
  python alert_daemon.py --once          单次检查后退出
  python alert_daemon.py --interval 60   60秒扫描间隔
  python alert_daemon.py --daemon        后台无窗口运行(需pythonw)
  python alert_daemon.py --test          测试模式(模拟触发止损)
"""

import sys, os, time, json, re
from datetime import datetime

# ─── 编码 ───
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

# ─── 路径 ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSITION_FILE = os.path.join(BASE_DIR, ".position.json")
ALERT_LOG_FILE = os.path.join(BASE_DIR, ".alert_log.txt")

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
# 风控参数
# ═══════════════════════════════════════════

STOP_LOSS_PCT = -5.0        # 硬止损
TAKE_PROFIT_PCT = 10.0      # 硬止盈
TRAILING_DRAWDOWN = -3.0    # 移动止盈回撤
YELLOW_WARN_PCT = 2.0       # 黄警: 距触发还有2%
ORANGE_WARN_PCT = 1.0       # 橙警: 距触发还有1%

# 交易时间
MARKET_OPEN = "09:30"
MARKET_CLOSE = "15:00"


# ═══════════════════════════════════════════
# 日志
# ═══════════════════════════════════════════

def alert_log(level, msg):
    """写预警日志"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now}] [{level}] {msg}"
    print(line)
    try:
        with open(ALERT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass


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
                "high": float(f[33]) if len(f)>33 and f[33] else None,
                "low": float(f[34]) if len(f)>34 and f[34] else None,
                "volume": float(f[6]) if f[6] else 0,
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
# 警示通知
# ═══════════════════════════════════════════

def send_notification(title, msg):
    """Windows 桌面通知"""
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, msg, duration=5, threaded=True)
    except ImportError:
        pass  # win10toast 未安装则跳过

    # 备用方案: 控制台响铃 + 显眼输出
    print(f"\a")  # BEL
    print(f"\n{'='*60}")
    print(f"{C.R}🔔 {title}{C.Z}")
    print(f"{C.Y}{msg}{C.Z}")
    print(f"{'='*60}\n")


def beep():
    """控制台响铃"""
    print("\a", end="")


# ═══════════════════════════════════════════
# 持仓加载
# ═══════════════════════════════════════════

def load_positions():
    """加载持仓"""
    if not os.path.exists(POSITION_FILE):
        alert_log("WARN", "未找到持仓文件 .position.json")
        return []

    with open(POSITION_FILE, encoding="utf-8") as f:
        data = json.load(f)

    holdings = data.get("holdings", [])

    # 兼容旧格式
    if not holdings and "code" in data:
        holdings = [data]

    return holdings


def save_positions(holdings, principal=3000):
    """保存持仓（更新最高价等）"""
    cash_used = sum(h.get("cost", h.get("buy_price", 0) * h.get("shares", 0))
                    for h in holdings)
    data = {
        "holdings": holdings,
        "principal": principal,
        "cash_used": cash_used,
        "cash_remaining": principal - cash_used,
    }
    with open(POSITION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════
# 预警检查
# ═══════════════════════════════════════════

def check_alerts(holdings, test_mode=False):
    """
    检查所有持仓的预警状态
    返回: (最高预警级别, 触发的预警列表)
    级别: 0=正常 1=黄 2=橙 3=红
    """
    if not holdings:
        return 0, []

    # 构建行情查询代码
    codes = []
    for h in holdings:
        raw = h["code"]
        prefix = "sh" if raw.startswith(("6","9")) else "sz"
        codes.append(f"{prefix}{raw}")

    quotes = get_quotes(codes)
    quote_map = {q["code"]: q for q in quotes}

    max_level = 0
    alerts = []

    for h in holdings:
        code = h["code"]
        name = h.get("name", "")
        buy_price = h.get("buy_price", 0)
        shares = h.get("shares", 0)
        stop_loss_price = h.get("stop_loss", buy_price * (1 + STOP_LOSS_PCT/100))
        take_profit_price = h.get("take_profit", buy_price * (1 + TAKE_PROFIT_PCT/100))

        quote = quote_map.get(code)
        if not quote or quote.get("price") is None:
            alert_log("WARN", f"{name}({code}) 无实时行情")
            continue

        price = quote["price"]
        pnl_pct = (price - buy_price) / buy_price * 100

        # 更新最高价 (移动止盈用)
        high_price = h.get("high_price", buy_price)
        if price > high_price:
            high_price = price
            h["high_price"] = high_price

        # ── 止损检查 ──
        dist_to_stop = (price - stop_loss_price) / price * 100  # 距止损还有多少%

        if pnl_pct <= STOP_LOSS_PCT:
            # 🔴 硬止损触发!
            level = 3
            max_level = max(max_level, level)
            msg = (f"🔴 止损触发! {name}({code})\n"
                   f"   成本:{buy_price:.2f} 现价:{price:.2f} "
                   f"盈亏:{pnl_pct:+.2f}% | 建议立即卖出{shares}股!")
            alerts.append({"level": level, "code": code, "name": name,
                          "type": "STOP_LOSS", "msg": msg, "price": price})
            alert_log("CRITICAL", msg.replace("\n", " | "))
            send_notification(f"🛑 止损触发! {name}", msg)
            beep()

        elif dist_to_stop <= ORANGE_WARN_PCT:
            # 🟠 橙色预警
            level = 2
            max_level = max(max_level, level)
            msg = (f"🟠 逼近止损! {name}({code})\n"
                   f"   成本:{buy_price:.2f} 现价:{price:.2f} "
                   f"盈亏:{pnl_pct:+.2f}% | 距止损仅{dist_to_stop:.1f}%!")
            alerts.append({"level": level, "code": code, "name": name,
                          "type": "NEAR_STOP", "msg": msg, "price": price})
            alert_log("WARNING", msg.replace("\n", " | "))

        elif dist_to_stop <= YELLOW_WARN_PCT:
            # 🟡 黄色预警
            level = 1
            max_level = max(max_level, level)
            msg = (f"🟡 注意止损! {name}({code})\n"
                   f"   成本:{buy_price:.2f} 现价:{price:.2f} "
                   f"盈亏:{pnl_pct:+.2f}% | 距止损{dist_to_stop:.1f}%")
            alerts.append({"level": level, "code": code, "name": name,
                          "type": "WATCH_STOP", "msg": msg, "price": price})
            alert_log("INFO", msg.replace("\n", " | "))

        # ── 止盈检查 ──
        dist_to_profit = (take_profit_price - price) / price * 100

        if pnl_pct >= TAKE_PROFIT_PCT:
            # 🔴 硬止盈触发!
            level = 3
            max_level = max(max_level, level)
            msg = (f"🎯 止盈触发! {name}({code})\n"
                   f"   成本:{buy_price:.2f} 现价:{price:.2f} "
                   f"盈亏:{pnl_pct:+.2f}% | 建议立即卖出{shares}股!")
            alerts.append({"level": level, "code": code, "name": name,
                          "type": "TAKE_PROFIT", "msg": msg, "price": price})
            alert_log("CRITICAL", msg.replace("\n", " | "))
            send_notification(f"🎯 止盈触发! {name}", msg)
            beep()

        elif pnl_pct > 0 and dist_to_profit <= ORANGE_WARN_PCT:
            # 🟠 接近止盈
            level = 2
            max_level = max(max_level, level)
            msg = (f"🟠 接近止盈! {name}({code})\n"
                   f"   成本:{buy_price:.2f} 现价:{price:.2f} "
                   f"盈亏:{pnl_pct:+.2f}% | 距止盈仅{dist_to_profit:.1f}%!")
            alerts.append({"level": level, "code": code, "name": name,
                          "type": "NEAR_PROFIT", "msg": msg, "price": price})
            alert_log("INFO", msg.replace("\n", " | "))

        elif pnl_pct > 0 and dist_to_profit <= YELLOW_WARN_PCT:
            # 🟡 靠近止盈
            level = 1
            max_level = max(max_level, level)
            msg = (f"🟡 靠近止盈! {name}({code})\n"
                   f"   成本:{buy_price:.2f} 现价:{price:.2f} "
                   f"盈亏:{pnl_pct:+.2f}% | 距止盈{dist_to_profit:.1f}%")
            alerts.append({"level": level, "code": code, "name": name,
                          "type": "WATCH_PROFIT", "msg": msg, "price": price})
            alert_log("INFO", msg.replace("\n", " | "))

        # ── 移动止盈检查 ──
        if high_price > buy_price * 1.05:  # 已涨超5%
            drawdown = (price - high_price) / high_price * 100
            if drawdown <= TRAILING_DRAWDOWN:
                level = 3
                max_level = max(max_level, level)
                msg = (f"📉 移动止盈! {name}({code})\n"
                       f"   最高价:{high_price:.2f} 现价:{price:.2f} "
                       f"回撤:{drawdown:+.2f}% | 建议卖出{shares}股!")
                alerts.append({"level": level, "code": code, "name": name,
                              "type": "TRAILING_STOP", "msg": msg, "price": price})
                alert_log("CRITICAL", msg.replace("\n", " | "))
                send_notification(f"📉 移动止盈! {name}", msg)
                beep()

        # ── 测试模式：强制触发 ──
        if test_mode:
            msg = f"🧪 [测试] {name}({code}) 现价{price:.2f} 盈亏{pnl_pct:+.2f}%"
            alerts.append({"level": 3, "code": code, "name": name,
                          "type": "TEST", "msg": msg, "price": price})
            alert_log("TEST", msg)
            max_level = 3

    return max_level, alerts


# ═══════════════════════════════════════════
# 状态显示
# ═══════════════════════════════════════════

def print_status(holdings, quotes):
    """打印持仓状态面板"""
    print(f"\n{C.B}── 持仓状态 {datetime.now().strftime('%H:%M:%S')} ──{C.Z}")
    for h in holdings:
        code = h["code"]
        name = h.get("name", "")
        buy_price = h.get("buy_price", 0)
        q = next((q for q in quotes if q["code"] == code), None)
        if q and q.get("price"):
            price = q["price"]
            pnl = (price - buy_price) / buy_price * 100
            c = C.R if pnl >= 0 else C.G
            stop = h.get("stop_loss", buy_price * 0.95)
            dist = (price - stop) / price * 100
            print(f"  {name}({code}) {buy_price:.2f}→{price:.2f} "
                  f"{c}{pnl:+.2f}%{C.Z} | 止损线{stop:.2f}(距{dist:.1f}%)")
        else:
            print(f"  {name}({code}) {buy_price:.2f}→? 无行情")


# ═══════════════════════════════════════════

def is_market_time():
    """检查是否交易时间"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.strftime("%H:%M")
    return MARKET_OPEN <= t <= MARKET_CLOSE


# ═══════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════

def run_daemon(interval=30, once=False, test_mode=False):
    """预警守护主循环"""
    alert_log("START", f"预警守护启动 | 间隔:{interval}s | "
              f"止损:{STOP_LOSS_PCT}% | 止盈:{TAKE_PROFIT_PCT}%")

    holdings = load_positions()
    if not holdings:
        alert_log("ERROR", "无持仓数据，退出")
        print(f"{C.R}❌ 无持仓数据，请先配置 .position.json{C.Z}")
        return

    # 打印初始状态
    codes = []
    for h in holdings:
        raw = h["code"]
        prefix = "sh" if raw.startswith(("6","9")) else "sz"
        codes.append(f"{prefix}{raw}")
    quotes = get_quotes(codes)
    print_status(holdings, quotes)

    scan_count = 0
    last_level = 0

    try:
        while True:
            scan_count += 1
            now = datetime.now()
            in_market = is_market_time()

            if not in_market and not once:
                # 非交易时间，降低检查频率
                if scan_count % 10 == 0:
                    alert_log("INFO", "⏸️ 非交易时间，低频监控中...")
                time.sleep(60)
                continue

            # 重新加载持仓（可能被 paper_trader 修改）
            holdings = load_positions()
            if not holdings:
                alert_log("INFO", "持仓已清空，退出守护")
                break

            level, alerts = check_alerts(holdings, test_mode)

            # 只在级别变化时打印详情
            if level != last_level and alerts:
                for a in alerts:
                    c = {1: C.Y, 2: C.Y, 3: C.R}.get(a["level"], C.D)
                    print(f"\n{c}{a['msg']}{C.Z}")

            # 每10次扫描显示心跳
            if scan_count % 10 == 0 or level > 0:
                status = {0: "⭕正常", 1: "🟡注意", 2: "🟠警戒", 3: "🔴触发"}[level]
                print(f"  [{now.strftime('%H:%M:%S')}] 扫描#{scan_count} {status}")

            last_level = level

            # 保存更新后的持仓（含最高价）
            save_positions(holdings)

            if once:
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        alert_log("STOP", "预警守护手动停止")
        print(f"\n{C.Y}👋 预警守护已停止{C.Z}")
        save_positions(holdings)


# ═══════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════

def main():
    once = "--once" in sys.argv
    test_mode = "--test" in sys.argv
    interval = 30

    for i, arg in enumerate(sys.argv):
        if arg == "--interval" and i+1 < len(sys.argv):
            interval = int(sys.argv[i+1])

    print(f"""
{C.M}╔══════════════════════════════════════════════╗
║   🦀 小秋止损止盈预警守护 v1.0              ║
║   三级预警 | 桌面通知 | 移动止盈            ║
╚══════════════════════════════════════════════╝{C.Z}

  止损: {C.R}{STOP_LOSS_PCT}%{C.Z} | 止盈: {C.G}{TAKE_PROFIT_PCT}%{C.Z} | 移动止盈回撤: {C.Y}{TRAILING_DRAWDOWN}%{C.Z}
  黄警距触发{C.Y}{YELLOW_WARN_PCT}%{C.Z} | 橙警距触发{C.Y}{ORANGE_WARN_PCT}%{C.Z}
  模式: {C.Y if test_mode else ''}{'测试' if test_mode else '单次' if once else '持续监控'}{C.Z}
""")

    run_daemon(interval=interval, once=once, test_mode=test_mode)


if __name__ == "__main__":
    main()
