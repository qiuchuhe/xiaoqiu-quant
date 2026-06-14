# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
=========================================================================
 A股量化工具集 v3.0 (精简版 · 共享核心库)
 数据源: 同花顺 + 腾讯双引擎

 选股策略 → D:\AI小秋\策略量化\策略1\scanner.py
 持仓监控 → D:\AI小秋\量化\monitor.py
=========================================================================
 用法:
   python stock_quant.py                       实时行情看板
   python stock_quant.py watch                 自选股
   python stock_quant.py top 20                涨幅前20
   python stock_quant.py ths 600519            同花顺深度数据
   python stock_quant.py ma 600519             均线分析
   python stock_quant.py search 茅台            搜索股票
   python stock_quant.py import /path/to/file  导入同花顺自选股
=========================================================================
"""

import sys, time, re, os, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from 小秋核心.utils import C, to_tx_code, to_raw_code, get_market, pct_fmt, prc_fmt
from 小秋核心.data import get_stock_list, get_quotes, get_index, get_kline, get_ths_stock, get_money_flow
from 小秋核心.indicators import calc_ma


# ═══════════════════════════════════════════
# 自选股管理
# ═══════════════════════════════════════════

SELF_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".my_watchlist.json")
DEFAULT_WL = {
    "sh600519": "贵州茅台", "sz000858": "五粮液", "sz300750": "宁德时代",
    "sz002594": "比亚迪", "sh600036": "招商银行", "sz300059": "东方财富",
    "sh600030": "中信证券", "sh601012": "隆基绿能", "sz000001": "平安银行",
}


def load_watchlist():
    if os.path.exists(SELF_FILE):
        with open(SELF_FILE, encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_WL.copy()


def save_watchlist(wl):
    with open(SELF_FILE, "w", encoding="utf-8") as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)
    print(f"\n  {C.B}已保存 {len(wl)} 只自选股{C.Z}\n")


def import_from_ths_file(filepath):
    imported = {}
    try:
        with open(filepath, "r", encoding="gbk") as f:
            content = f.read()
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r'[\t,;]+', line)
            if len(parts) >= 1:
                code = parts[0].strip().zfill(6)
                name = parts[1].strip() if len(parts) > 1 else ""
                prefix = "sh" if code.startswith(("6", "9")) else "sz"
                imported[f"{prefix}{code}"] = name
        save_watchlist(imported)
        return imported
    except Exception as e:
        print(f"  {C.R}导入失败: {e}{C.Z}")
        return {}


# ═══════════════════════════════════════════
# 显示
# ═══════════════════════════════════════════

def bar(v, width=10):
    v = max(-width, min(width, v))
    n = int(abs(v))
    s = "█" * n + " " * (width - n)
    return f"{C.R}{s}{C.Z}" if v > 0 else f"{C.G}{s}{C.Z}"


def show_header(indices):
    parts = []
    for idx in indices:
        n = idx["name"]; p = idx.get("pct") or 0; pr = idx.get("price")
        c = C.R if p > 0 else (C.G if p < 0 else C.W)
        a = "▲" if p > 0 else ("▼" if p < 0 else "—")
        parts.append(f"{C.B}{n}{C.Z} {c}{pr:.2f}  {a} {p:+.2f}%{C.Z}" if pr else f"{C.B}{n}{C.Z}")
    print(f"\n  {'  │  '.join(parts)}\n")


def show_table(stocks, title="实时行情"):
    print(f"  {C.B}{title}{C.Z}  ({len(stocks)} 只)")
    print(f"  {'─'*92}")
    print(f"  {'代码':<8s} {'名称':<10s} {'最新价':>7s}  {'涨跌幅':>9s}  {'成交量(手)':>9s}  {'成交额(万)':>9s}  {'最高':>7s}  {'最低':>7s}")
    print(f"  {'─'*92}")
    for s in stocks:
        print(f"  {C.B}{s['code']:<8s}{C.Z} {s['name']:<10s}  {prc_fmt(s.get('price'), s.get('preclose'))}  "
              f"{pct_fmt(s.get('pct'))}  {s.get('volume',0):>9,.0f}  {s.get('amount',0):>9,.0f}  "
              f"{(s.get('high')or 0):>7.2f}  {(s.get('low')or 0):>7.2f}")
    print(f"  {'─'*92}")
    up_n = sum(1 for s in stocks if (s.get("pct") or 0) > 0)
    dn_n = sum(1 for s in stocks if (s.get("pct") or 0) < 0)
    print(f"  {C.D}{datetime.now().strftime('%H:%M:%S')}  |  涨 {C.R}{up_n}{C.D}  跌 {C.G}{dn_n}{C.D}  |  Ctrl+C 退出{C.Z}\n")


def show_money_flow_display(code, name=""):
    """显示资金流向面板"""
    ths = get_ths_stock(code)
    if not ths:
        print(f"  {C.R}无法获取同花顺数据{C.Z}")
        return
    name = name or ths["name"]
    raw_code = to_raw_code(code)

    print(f"\n  {C.M}═══ 同花顺深度: {name} ({raw_code}) ═══{C.Z}\n")
    print(f"  {'─'*60}")
    print(f"  │  {C.B}实时行情{C.Z}")
    print(f"  │  最新: {prc_fmt(ths['price'], ths['preclose'])}      涨跌: {pct_fmt(ths['pct'])}")
    print(f"  │  涨跌: {bar(ths['pct'] or 0, 20)}")
    print(f"  │  今开: {ths['open']:>7.2f}  最高: {ths['high']:>7.2f}  最低: {ths['low']:>7.2f}")
    print(f"  │  涨停: {C.R}{ths['limit_up']:.2f}{C.Z}  跌停: {C.G}{ths['limit_down']:.2f}{C.Z}")
    print(f"  │  换手: {ths['turnover']:.2f}%  振幅: {ths['amplitude']:.2f}%")
    print(f"  ├{'─'*59}")
    print(f"  │  {C.B}基本面{C.Z}")
    print(f"  │  总市值: {ths['total_mv']/1e8:>8,.0f}亿  流通: {ths['float_mv']/1e8:>8,.0f}亿")
    print(f"  │  PE动态: {ths['pe_dynamic']:>6.1f}  PE静态: {ths['pe_static']:>6.1f}  PB: {ths['pb']:.2f}")

    # 资金流向
    flow = get_money_flow(code)
    if flow and "data" in flow:
        fd = flow["data"]
        print(f"  ├{'─'*59}")
        print(f"  │  {C.B}资金流向 (万元){C.Z}")

        def ff(v):
            return f"{C.R}{v:>10,.0f}{C.Z}" if v > 0 else (f"{C.G}{v:>10,.0f}{C.Z}" if v < 0 else f"{v:>10,.0f}")

        for label, key in [("主力净流入", "main_net"), ("超大单", "big_net"),
                           ("中单", "mid_net"), ("小单", "small_net")]:
            v = float(fd.get(key, 0))
            print(f"  │  {label}: {ff(v)}  {bar(v / max(abs(v),1) * 10 if max(abs(v),1)>0 else 0, 10)}")

    print(f"  {'─'*60}")
    print(f"  │  {C.D}来源: 同花顺 | 更新: {ths['time']}{C.Z}")
    print(f"  {'─'*60}\n")


def show_kline_analysis(code, name=""):
    """均线分析"""
    kl = get_kline(code, 120)
    if not kl:
        print(f"  {C.R}无K线数据{C.Z}")
        return
    closes = [k["close"] for k in kl]
    ma5 = calc_ma(closes, 5); ma20 = calc_ma(closes, 20); ma60 = calc_ma(closes, 60)

    print(f"\n  {C.M}═══ 均线分析: {name or code} ═══{C.Z}\n")
    print(f"  {'日期':<12s} {'收盘':>7s}  {'MA5':>7s}  {'MA20':>7s}  {'MA60':>7s}  {'趋势'}")
    print(f"  {'─'*62}")
    for i in range(max(0, len(kl) - 20), len(kl)):
        m5, m20, m60 = ma5[i], ma20[i], ma60[i]
        trend = "多头" if (m5 and m20 and m5 > m20) else ("空头" if (m5 and m20) else "观望")
        tc = C.R if trend == "多头" else (C.G if trend == "空头" else C.D)
        print(f"  {kl[i]['date']:<12s} {prc_fmt(closes[i])}  "
              f"{f'{m5:7.2f}' if m5 else '     --'}  {f'{m20:7.2f}' if m20 else '     --'}  "
              f"{f'{m60:7.2f}' if m60 else '     --'}  {tc}{trend}{C.Z}")

    if ma5[-1] and ma20[-1] and ma5[-2] and ma20[-2]:
        if ma5[-2] <= ma20[-2] and ma5[-1] > ma20[-1]:
            print(f"\n  {C.R}>>> MA5金叉MA20 (买入信号) <<<{C.Z}")
        elif ma5[-2] >= ma20[-2] and ma5[-1] < ma20[-1]:
            print(f"\n  {C.G}>>> MA5死叉MA20 (卖出信号) <<<{C.Z}")
    print()


# ═══════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════

def usage():
    print(f"""
  {C.M}╔══════════════════════════════════════════╗
  ║     A股量化工具集 v3.0 (精简版)           ║
  ║     同花顺 + 腾讯 双引擎                  ║
  ╚══════════════════════════════════════════╝{C.Z}

  {C.B}行情:{C.Z}
    python stock_quant.py                   全市场涨跌榜
    python stock_quant.py watch             自选股
    python stock_quant.py top 20            涨幅前20

  {C.B}深度:{C.Z}
    python stock_quant.py ths 600519        同花顺深度(PE/PB/资金流向)

  {C.B}分析:{C.Z}
    python stock_quant.py ma 600519         均线分析(金叉/死叉)

  {C.B}管理:{C.Z}
    python stock_quant.py search 茅台        搜索股票
    python stock_quant.py import FILE       从文件导入自选股

  {C.M}选股策略:{C.Z} 策略量化/策略1/scanner.py
  {C.M}持仓监控:{C.Z} 量化/monitor.py
  """)


def main():
    if len(sys.argv) < 2:
        cmd = "board"
    else:
        cmd = sys.argv[1]

    # ── 行情看板 ──
    if cmd in ("board", "b"):
        stocks = get_stock_list()
        if stocks:
            tx_codes = [to_tx_code(c) for c in stocks]
            quotes = get_quotes(tx_codes)
        else:
            quotes = get_quotes(list(load_watchlist().keys()))
        show_header(get_index())
        valid = [s for s in quotes if s.get("pct") is not None]
        valid.sort(key=lambda s: s["pct"], reverse=True)
        top15 = valid[:15]; bot15 = valid[-15:]
        seen = set(); merged = []
        for s in top15 + list(reversed(bot15)):
            if s["code"] not in seen:
                seen.add(s["code"]); merged.append(s)
        show_table(merged, "涨幅前15 + 跌幅前15")

    elif cmd in ("watch", "w"):
        wl = load_watchlist()
        show_header(get_index())
        show_table(get_quotes(list(wl.keys())), "自选股")

    elif cmd in ("top", "up"):
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        stocks = get_stock_list()
        codes = [to_tx_code(c) for c in stocks] if stocks else list(load_watchlist().keys())
        show_header(get_index())
        valid = [s for s in get_quotes(codes) if s.get("pct") is not None]
        valid.sort(key=lambda s: s["pct"], reverse=True)
        show_table(valid[:n], f"涨幅 Top {n}")

    elif cmd in ("live", "refresh"):
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        wl = load_watchlist()
        print(f"\n  {C.Y}每 {interval}s 刷新, Ctrl+C 退出{C.Z}")
        try:
            while True:
                os.system("cls" if sys.platform == "win32" else "clear")
                show_header(get_index())
                show_table(get_quotes(list(wl.keys())), "自选股")
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n  {C.B}拜拜!{C.Z}\n")

    # ── 同花顺深度 ──
    elif cmd in ("ths", "flow"):
        code = sys.argv[2].zfill(6) if len(sys.argv) > 2 else "600519"
        show_money_flow_display(code)

    # ── 均线分析 ──
    elif cmd == "ma":
        code = sys.argv[2].zfill(6) if len(sys.argv) > 2 else "600519"
        all_codes = get_stock_list()
        show_kline_analysis(code, all_codes.get(code, ""))

    # ── 自选股管理 ──
    elif cmd == "search":
        keyword = sys.argv[2] if len(sys.argv) > 2 else ""
        all_codes = get_stock_list()
        matches = [(c, n) for c, n in all_codes.items() if keyword in n or keyword in c]
        if matches:
            print(f"\n  {C.B}搜索 '{keyword}': {len(matches)} 结果{C.Z}\n")
            for code, name in matches[:30]:
                print(f"  {C.B}{code}{C.Z}  {name}")
            top = matches[:8]
            codes = [to_tx_code(c) for c, _ in top]
            show_table(get_quotes(codes), f"'{keyword}' 行情")
        else:
            print(f"  {C.Y}未找到 '{keyword}'{C.Z}")

    elif cmd in ("import", "load"):
        path = sys.argv[2] if len(sys.argv) > 2 else ""
        if path:
            imported = import_from_ths_file(path)
            print(f"  {C.B}导入 {len(imported)} 只{C.Z}")
        else:
            print(f"  {C.Y}用法: python stock_quant.py import 文件路径{C.Z}")

    elif cmd in ("list", "ls"):
        wl = load_watchlist()
        print(f"\n  {C.B}自选股 ({len(wl)} 只):{C.Z}\n")
        for code, name in wl.items():
            print(f"  {C.B}{code}{C.Z}  {name}")
        print()

    elif cmd in ("add",):
        if len(sys.argv) < 3:
            print(f"  {C.Y}用法: python stock_quant.py add 600519{C.Z}")
        else:
            wl = load_watchlist()
            code = sys.argv[2].zfill(6)
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            stock = get_quotes([f"{prefix}{code}"])
            name = stock[0]["name"] if stock else ""
            wl[f"{prefix}{code}"] = name
            save_watchlist(wl)

    elif cmd in ("del", "remove", "rm"):
        if len(sys.argv) < 3:
            print(f"  {C.Y}用法: python stock_quant.py del 600519{C.Z}")
        else:
            wl = load_watchlist()
            key = "sh" + sys.argv[2].zfill(6) if sys.argv[2].zfill(6).startswith(("6", "9")) else "sz" + sys.argv[2].zfill(6)
            if key in wl:
                del wl[key]
                save_watchlist(wl)

    else:
        usage()


if __name__ == "__main__":
    main()
