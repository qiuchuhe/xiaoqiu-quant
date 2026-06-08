# -*- coding: utf-8 -*-
"""持仓重点监控——2分钟一刷，接近止损/止盈立刻报警"""
import urllib.request, re, time, sys, json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except:
        pass

UA = "Mozilla/5.0"
INTERVAL = 120  # 2分钟刷新

# 持仓规则
HOLDINGS = {
    "sh600179": {"name": "安通控股", "cost": 4.64, "shares": 300,
                  "stop": 4.41, "take": 5.10},
    "sz000725": {"name": "京东方A", "cost": 6.16, "shares": 100,
                  "stop": 6.40, "take": None,  # 移动止盈
                  "key_levels": [6.50, 7.00, 7.50]},
}

def fetch(codes):
    url = f"http://qt.gtimg.cn/q={','.join(codes)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=10).read().decode("gbk", errors="replace")
    results = {}
    for line in raw.strip().split(";\n"):
        m = re.search(r'="(.+)"', line.strip())
        if not m: continue
        f = m.group(1).split("~")
        if len(f) < 40: continue
        results[f[2]] = {"name": f[1], "price": float(f[3]), "preclose": float(f[4]),
                          "high": float(f[33]), "low": float(f[34]), "time": f[30]}
    return results

def check(quotes):
    alerts = []
    for tx, cfg in HOLDINGS.items():
        code = tx[2:]
        q = quotes.get(code)
        if not q: continue
        price = q["price"]
        pct = (price - q["preclose"]) / q["preclose"] * 100
        cost_pct = (price - cfg["cost"]) / cfg["cost"] * 100

        # 止损预警
        dist_stop = (price - cfg["stop"]) / cfg["stop"] * 100
        if dist_stop <= 1.0:
            alerts.append(f"!!! {cfg['name']}({code}) 逼近止损! {price:.2f} 距止损{cfg['stop']}仅{dist_stop:+.1f}%")

        # 止盈预警
        if cfg["take"] and price >= cfg["take"]:
            alerts.append(f">>> {cfg['name']}({code}) 触及止盈! {price:.2f}>={cfg['take']}")

        # 京东方A关键位突破
        if cfg.get("key_levels"):
            for lv in cfg["key_levels"]:
                if q["high"] >= lv and price >= lv * 0.99:
                    alerts.append(f"!!! {cfg['name']}({code}) 突破关键位{lv}! 现价{price:.2f} 检查移动止盈")

        status = "[+]" if cost_pct > 0 else ("[~]" if cost_pct > -3 else "[!]")
        print(f"  {status} {cfg['name']}({code}) {price:.2f} | 今日{pct:+.2f}% | 盈亏{cost_pct:+.2f}% | 距止损{dist_stop:+.1f}%")

    return alerts

def main():
    print("╔══════════════════════════════╗")
    print("║  [!] 持仓重点监控 (2min)     ║")
    print("╚══════════════════════════════╝\n")
    codes = list(HOLDINGS.keys())
    while True:
        try:
            quotes = fetch(codes)
            now = time.strftime("%H:%M:%S")
            print(f"\n[{now}]")
            alerts = check(quotes)
            for a in alerts:
                print(f"\n  ╔════════════════════╗")
                print(f"  ║  {a}")
                print(f"  ╚════════════════════╝\n")
        except Exception as e:
            print(f"  [!] 网络异常: {e}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n监控结束")
