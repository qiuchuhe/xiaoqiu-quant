# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
A股实时行情看板  --  数据源：东方财富 (curl 后端)
==================================================
用法:
    python stock_watch.py                涨跌前15
    python stock_watch.py -w             自选股
    python stock_watch.py -t 20          涨幅前20
    python stock_watch.py -d 15          跌幅前15
    python stock_watch.py -r 5           每5秒自动刷新
    python stock_watch.py -c 600519      查单个股票
"""

import argparse, sys, time, json, subprocess, os
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ==================== 颜色 ====================
class C:
    R = "\033[1;31m"    # 红（涨）
    G = "\033[1;32m"    # 绿（跌）
    Y = "\033[1;33m"    # 黄
    B = "\033[1;36m"    # 青
    W = "\033[1;37m"    # 白
    D = "\033[2;37m"    # 灰
    Z = "\033[0m"       # 重置

def up(s):   return f"{C.R}{s}{C.Z}"
def dn(s):   return f"{C.G}{s}{C.Z}"
def bd(s):   return f"{C.B}{s}{C.Z}"
def gr(s):   return f"{C.D}{s}{C.Z}"

# ==================== 自选股 ====================
WATCHLIST = {
    "000001": "平安银行",   "600519": "贵州茅台",   "300750": "宁德时代",
    "000858": "五粮液",     "601012": "隆基绿能",   "002594": "比亚迪",
    "600036": "招商银行",   "300059": "东方财富",
}


# ==================== 数据获取 (curl) ====================

def curl(url, timeout=8):
    """通过 curl 发请求，避开 Python HTTP 库的防火墙问题"""
    try:
        result = subprocess.run([
            "curl", "-s", "--connect-timeout", str(timeout),
            "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "-H", "Referer: https://quote.eastmoney.com/",
            url
        ], capture_output=True, text=True, encoding="utf-8", timeout=timeout+3,
           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        return json.loads(result.stdout)
    except Exception as e:
        raise ConnectionError(f"curl 请求失败: {e}")


def fetch_stocks():
    """全A股实时行情"""
    fields = "f2,f3,f4,f5,f6,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f124"
    url = (
        f"https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz=5000&po=1&np=1&fltt=2&invt=2&fid=f3"
        f"&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
        f"&fields={fields}"
    )
    data = curl(url)
    stocks = []
    for r in data["data"]["diff"]:
        stocks.append({
            "code": r.get("f12", ""),
            "name": r.get("f14", ""),
            "price": r.get("f2") or 0,
            "pct": r.get("f3") or 0,
            "chg": r.get("f4") or 0,
            "vol": r.get("f5") or 0,
            "amt": r.get("f6") or 0,
            "turn": r.get("f8") or 0,
            "pe": r.get("f9") or 0,
            "high": r.get("f15") or 0,
            "low": r.get("f16") or 0,
            "open": r.get("f17") or 0,
            "preclose": r.get("f18") or 0,
        })
    return stocks


def fetch_index():
    """三大指数"""
    url = (
        f"https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz=10&po=1&np=1&fltt=2&invt=2&fid=f3"
        f"&fs=b:MK0010,b:MK0004,b:MK0007"
        f"&fields=f2,f3,f4,f12,f14"
    )
    data = curl(url)
    indices = {}
    for r in data["data"]["diff"]:
        indices[r["f14"]] = {"price": r.get("f2"), "pct": r.get("f3"), "chg": r.get("f4")}
    return indices


# ==================== 显示 ====================

def color_price(v, ref):
    if v >= ref: return f"{C.R}{v:>7.2f}{C.Z}"
    else:        return f"{C.G}{v:>7.2f}{C.Z}"

def color_pct(v):
    if v > 0:    return f"{C.R}{v:>+7.2f}%{C.Z}"
    elif v < 0:  return f"{C.G}{v:>+7.2f}%{C.Z}"
    else:        return f"{C.D}{v:>+7.2f}%{C.Z}"


def show():
    try:
        indices = fetch_index()
        stocks = fetch_stocks()
    except Exception as e:
        print(f"\n  {C.R}[!] {e}{C.Z}")
        return

    os.system("cls" if sys.platform == "win32" else "clear")

    # ----- 大盘指数 -----
    parts = []
    for name in ["上证指数", "深证成指", "创业板指"]:
        v = indices.get(name)
        if not v: continue
        p = v["pct"] or 0
        c = C.R if p > 0 else (C.G if p < 0 else C.W)
        a = "▲" if p > 0 else ("▼" if p < 0 else "—")
        parts.append(f"{bd(name)} {c}{v['price']:.2f}  {a} {p:+.2f}%{C.Z}")
    print(f"\n  {'  │  '.join(parts)}\n")

    # ----- 筛选 -----
    if ARGS.code:
        code = ARGS.code.zfill(6)
        stocks = [s for s in stocks if s["code"] == code]
        title = f"查询: {code}"
    elif ARGS.watch:
        stocks = [s for s in stocks if s["code"] in WATCHLIST]
        title = "自选股"
    elif ARGS.top:
        valid = [s for s in stocks if s["pct"] is not None]
        valid.sort(key=lambda x: x["pct"], reverse=True)
        stocks = valid[:ARGS.top]
        title = f"涨幅 Top {ARGS.top}"
    elif ARGS.drop:
        valid = [s for s in stocks if s["pct"] is not None]
        valid.sort(key=lambda x: x["pct"])
        stocks = valid[:ARGS.drop]
        title = f"跌幅 Top {ARGS.drop}"
    else:
        valid = [s for s in stocks if s["pct"] is not None]
        valid.sort(key=lambda x: x["pct"], reverse=True)
        top = valid[:15]
        bot = valid[-15:]
        seen = set()
        stocks = []
        for s in top + reversed(bot):
            if s["code"] not in seen:
                seen.add(s["code"])
                stocks.append(s)
        title = "涨幅前15  +  跌幅前15"

    # ----- 表格 -----
    print(f"  {C.B}{title}{C.Z}  ({len(stocks)} 只)")
    print(f"  {'─' * 92}")
    hdr = f"  {'代码':<8s} {'名称':<10s} {'最新价':>7s}  {'涨跌幅':>9s}  {'换手%':>6s}  {'PE':>6s}  {'成交额(亿)':>9s}"
    print(hdr)
    print(f"  {'─' * 92}")

    for s in stocks:
        p = s["price"]; pc = s["preclose"]
        print(
            f"  {bd(s['code']):>16s}  "
            f"{s['name']:<10s}  "
            f"{color_price(p, pc)}  "
            f"{color_pct(s['pct'])}  "
            f"{s['turn']:>5.2f}%  "
            f"{s['pe']:>5.1f}  "
            f"{s['amt']/1e8:>8.1f}"
        )
    print(f"  {'─' * 92}")

    # 统计
    up_n = len([s for s in stocks if s["pct"] > 0])
    dn_n = len([s for s in stocks if s["pct"] < 0])
    t = datetime.now().strftime("%H:%M:%S")
    print(f"  {gr(f'{t}  |  涨 {up_n}  跌 {dn_n}  |  Ctrl+C 退出')}")
    print()


# ==================== 入口 ====================

parser = argparse.ArgumentParser(description="A股实时行情看板")
parser.add_argument("-w", "--watch", action="store_true")
parser.add_argument("-t", "--top", type=int, default=0)
parser.add_argument("-d", "--drop", type=int, default=0)
parser.add_argument("-r", "--refresh", type=int, default=0)
parser.add_argument("-c", "--code", type=str, default="")
ARGS = parser.parse_args()

if __name__ == "__main__":
    if ARGS.refresh > 0:
        print(f"\n  {C.Y}每 {ARGS.refresh}s 自动刷新, Ctrl+C 退出{C.Z}")
        try:
            while True:
                show()
                time.sleep(ARGS.refresh)
        except KeyboardInterrupt:
            print(f"\n  {C.B}拜拜, 祝你赚钱!{C.Z}\n")
    else:
        show()
