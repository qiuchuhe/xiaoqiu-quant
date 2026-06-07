# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
=========================================================================
 A股量化工具集 v2.1 (精简版)
 数据源: 同花顺 + 腾讯双引擎 (HTTP协议, 无需梯子)

 选股策略 → 请用 D:\AI小秋\策略量化\策略1\scanner.py
=========================================================================
 用法:
   python stock_quant.py                       实时行情看板
   python stock_quant.py watch                 自选股
   python stock_quant.py top 20                涨幅前20
   python stock_quant.py live 5                每5秒自动刷新
   python stock_quant.py search 茅台            搜索股票
   python stock_quant.py ths 600519            同花顺深度数据(市值/PE/涨跌停)
   python stock_quant.py ma 600519             均线分析(日K)
   python stock_quant.py backtest 600519       双均线策略回测
   python stock_quant.py bt2 600519            多头排列策略回测
   python stock_quant.py cmp 600519            双回测对比
   python stock_quant.py flow 600519           资金流向(同花顺源)
   python stock_quant.py import /path/to/file  导入同花顺自选股
=========================================================================
"""

import sys, time, re, os, json
from datetime import datetime, timedelta
from collections import OrderedDict

if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass

# ==================== HTTP请求 ====================
import urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

def http_get(url, timeout=10, decode="gbk"):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(decode)


# ==================== 颜色 ====================
class C:
    R="\033[1;31m"; G="\033[1;32m"; Y="\033[1;33m"; B="\033[1;36m"
    W="\033[1;37m"; D="\033[2;37m"; M="\033[1;35m"; Z="\033[0m"

def pct_fmt(v):
    if v is None: return f"{C.D}     --{C.Z}"
    return f"{C.R}{v:+7.2f}%{C.Z}" if v>0 else (f"{C.G}{v:+7.2f}%{C.Z}" if v<0 else f"{C.D}{v:+7.2f}%{C.Z}")

def prc_fmt(v, ref=None):
    if v is None: return f"{C.D}     --{C.Z}"
    s = f"{v:7.2f}"
    return f"{C.R}{s}{C.Z}" if (ref and v>=ref) else (f"{C.G}{s}{C.Z}" if (ref and v<ref) else s)

def bar(v, width=10):
    """画简易柱状图"""
    v = max(-width, min(width, v))
    n = int(abs(v))
    bar_str = "█" * n + " " * (width - n)
    if v > 0: return f"{C.R}{bar_str}{C.Z}"
    return f"{C.G}{bar_str}{C.Z}"


# ==================== 自选股管理 ====================
SELF_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".my_watchlist.json")

def load_watchlist():
    """加载自选股列表"""
    if os.path.exists(SELF_FILE):
        with open(SELF_FILE, encoding="utf-8") as f:
            return json.load(f)
    # 默认
    return {
        "sh600519": "贵州茅台", "sz000858": "五粮液",   "sz300750": "宁德时代",
        "sz002594": "比亚迪",   "sh600036": "招商银行", "sz300059": "东方财富",
        "sh600030": "中信证券", "sh601012": "隆基绿能", "sz000001": "平安银行",
        "sz002415": "海康威视", "sz000333": "美的集团",
    }

def save_watchlist(wl):
    with open(SELF_FILE, "w", encoding="utf-8") as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)
    print(f"\n  {C.B}已保存 {len(wl)} 只自选股到 {SELF_FILE}{C.Z}\n")

def import_from_ths_file(filepath):
    """从同花顺导出的文件导入自选股"""
    imported = {}
    try:
        with open(filepath, "r", encoding="gbk") as f:
            content = f.read()
        # 同花顺导出格式: 代码\t名称\n 或 代码,名称\n
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"): continue
            parts = re.split(r'[\t,;]+', line)
            if len(parts) >= 1:
                code = parts[0].strip().zfill(6)
                name = parts[1].strip() if len(parts) > 1 else ""
                prefix = "sh" if code.startswith(("6","9")) else "sz"
                imported[f"{prefix}{code}"] = name
        save_watchlist(imported)
        return imported
    except Exception as e:
        print(f"  {C.R}导入失败: {e}{C.Z}")
        return {}


def find_ths_self_stocks():
    """自动查找同花顺本地自选股文件"""
    # 同花顺常见存储路径
    paths = [
        os.path.expandvars(r"%APPDATA%\Hexin\self_stock.txt"),
        os.path.expandvars(r"%LOCALAPPDATA%\Hexin\self_stock.txt"),
        r"C:\Hexin\userdata\self_stock.txt",
        r"D:\Hexin\userdata\self_stock.txt",
        r"C:\同花顺\userdata\self_stock.txt",
        r"D:\同花顺\userdata\self_stock.txt",
        r"C:\Program Files\同花顺\userdata\self_stock.txt",
        os.path.expandvars(r"%USERPROFILE%\Documents\同花顺\*.txt"),
    ]
    for p in paths:
        if "*" in p:
            import glob
            matches = glob.glob(p)
            for m in matches:
                if os.path.exists(m):
                    return m
        elif os.path.exists(p):
            return p
    return None


# ==================== 同花顺数据源 ====================

def parse_ths_jsonp(raw, code=""):
    """解析同花顺 JSONP 数据"""
    # 格式: quotebridge_v2_realhead_hs_XXXXXX_last({...})
    m = re.search(r'\((\{.*\})\)', raw, re.DOTALL)
    if not m: return None
    data = json.loads(m.group(1))  # group(1) 去掉了外层括号
    items = data.get("items", {})
    if not items: return None

    # 同花顺字段映射
    def f(key): return float(items.get(key) or 0)
    price = f("10")
    preclose = f("6")
    pct = f("199112")
    high = f("8")
    low = f("9")
    open_p = f("7")
    volume = f("25")
    amount = f("19")
    pe_dynamic = f("69")
    pe_static = f("70")
    try: pb = f("74")
    except: pb = 0
    total_mv = f("3541450")
    float_mv = f("3475914")
    limit_up = f("30")
    limit_down = f("31")
    turnover = f("1968584")
    amplitude = f("526792")

    return {
        "code": str(items.get("5", code)),
        "name": items.get("name", ""),
        "price": price,
        "preclose": preclose,
        "pct": pct,
        "high": high,
        "low": low,
        "open": open_p,
        "volume": volume,
        "amount": amount / 10000,  # 转万
        "pe_dynamic": pe_dynamic,
        "pe_static": pe_static,
        "pb": pb,
        "total_mv": total_mv,
        "float_mv": float_mv,
        "limit_up": limit_up,
        "limit_down": limit_down,
        "turnover": turnover,
        "amplitude": amplitude,
        "time": items.get("time", ""),
        "_source": "同花顺",
    }


def get_ths_stock(code):
    """从同花顺获取单只股票深度数据"""
    # code 可以是 "600519" 或 "sh600519"
    raw_code = code.replace("sh","").replace("sz","").zfill(6)
    url = f"http://d.10jqka.com.cn/v2/realhead/hs_{raw_code}/last.js"
    try:
        raw = http_get(url, timeout=8, decode="gbk")
        return parse_ths_jsonp(raw, raw_code)
    except Exception as e:
        return None


def get_ths_batch(codes, show_progress=False):
    """批量获取同花顺数据（并发请求）"""
    # 同花顺不支持批量，需要逐个请求
    # 用线程池加速
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    raw_codes = []
    for c in codes:
        raw = c.replace("sh","").replace("sz","").zfill(6)
        if raw not in raw_codes:
            raw_codes.append(raw)

    if show_progress and len(raw_codes) > 5:
        print(f"  {C.D}从同花顺获取 {len(raw_codes)} 只股票深度数据...{C.Z}")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(get_ths_stock, c): c for c in raw_codes}
        for f in as_completed(futures):
            r = f.result()
            if r:
                results.append(r)

    return results


# ==================== 资金流向(同花顺) ====================

def get_money_flow(code):
    """获取个股资金流向 — 同花顺源"""
    raw_code = code.replace("sh","").replace("sz","").zfill(6)
    try:
        url = f"http://ff.10jqka.com.cn/ff/stockdetail/code/{raw_code}"
        raw = http_get(url, timeout=10, decode="gbk")
        # 解析JSON
        data = json.loads(raw)
        return data
    except:
        return None


def show_money_flow(code, name=""):
    """显示资金流向"""
    raw_code = code.replace("sh","").replace("sz","").zfill(6)
    # 先拿行情
    ths = get_ths_stock(code)
    if not ths:
        print(f"  {C.R}无法获取同花顺数据{C.Z}")
        return
    name = name or ths["name"]

    print(f"\n  {C.M}═══ 同花顺深度数据: {name} ({raw_code}) ═══{C.Z}\n")
    print(f"  {'─' * 60}")
    print(f"  │  {C.B}实时行情{C.Z}")
    print(f"  │  最新价: {prc_fmt(ths['price'], ths['preclose'])}      "
          f"涨跌幅: {pct_fmt(ths['pct'])}")

    # 涨跌幅柱状图
    pct = ths['pct'] or 0
    print(f"  │  涨跌: {bar(pct, 20)}")

    print(f"  │  今开: {ths['open']:>7.2f}  最高: {ths['high']:>7.2f}  最低: {ths['low']:>7.2f}")
    print(f"  │  涨停价: {C.R}{ths['limit_up']:.2f}{C.Z}  跌停价: {C.G}{ths['limit_down']:.2f}{C.Z}")
    print(f"  │  成交量: {ths['volume']:>10,.0f}手  成交额: {ths['amount']:>10,.0f}万")
    print(f"  │  换手率: {ths['turnover']:.2f}%  振幅: {ths['amplitude']:.2f}%")
    print(f"  ├{'─' * 59}")
    print(f"  │  {C.B}基本面{C.Z}")
    total_mv_yi = ths['total_mv'] / 1e8
    float_mv_yi = ths['float_mv'] / 1e8
    print(f"  │  总市值: {total_mv_yi:>8,.0f}亿  流通市值: {float_mv_yi:>8,.0f}亿")
    print(f"  │  动态PE: {ths['pe_dynamic']:>6.1f}  静态PE: {ths['pe_static']:>6.1f}  市净率: {ths['pb']:.2f}")
    print(f"  ├{'─' * 59}")

    # 资金流向
    flow = get_money_flow(code)
    if flow and "data" in flow:
        fd = flow["data"]
        print(f"  │  {C.B}资金流向 (万元){C.Z}")
        main_in = float(fd.get("main_net", 0))
        big_in = float(fd.get("big_net", 0))
        mid_in = float(fd.get("mid_net", 0))
        small_in = float(fd.get("small_net", 0))

        def flow_fmt(v):
            if v > 0: return f"{C.R}{v:>10,.0f}{C.Z}"
            elif v < 0: return f"{C.G}{v:>10,.0f}{C.Z}"
            return f"{v:>10,.0f}"

        print(f"  │  主力净流入: {flow_fmt(main_in)}  超大单: {flow_fmt(big_in)}")
        print(f"  │  中单净流入: {flow_fmt(mid_in)}  小单: {flow_fmt(small_in)}")

        # 资金柱状图
        max_flow = max(abs(main_in), abs(big_in), abs(mid_in), abs(small_in), 1)
        def flow_bar(v, label):
            b = bar(v / max_flow * 10 if max_flow > 0 else 0, 10)
            return f"  │  {label:6s} {b} {flow_fmt(v)}"
        print(flow_bar(main_in, "主力"))
        print(flow_bar(big_in, "超大单"))
        print(flow_bar(mid_in, "中单"))
        print(flow_bar(small_in, "小单"))

    print(f"  {'─' * 60}")
    print(f"  │  {C.D}数据来源: 同花顺 (d.10jqka.com.cn)  更新时间: {ths['time']}{C.Z}")
    print(f"  {'─' * 60}")
    print()


# ==================== 腾讯数据源(批量) ====================

def parse_tx(raw):
    """解析腾讯 v_xx="1~name~code~price~..." 格式"""
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
                "open": float(f[5]) if f[5] else None,
                "volume": float(f[6]) if f[6] else 0,
                "high": float(f[33]) if len(f)>33 and f[33] else None,
                "low": float(f[34]) if len(f)>34 and f[34] else None,
                "amount": float(f[37]) if len(f)>37 and f[37] else 0,
                "turnover": float(f[38]) if len(f)>38 and f[38] else None,
                "time": f[30] if len(f)>30 else "",
                "_source": "腾讯",
            })
        except: continue
    return results


def get_tx_stocks(codes):
    """腾讯批量行情"""
    all_r = []
    for i in range(0, len(codes), 50):
        batch = codes[i:i+50]
        url = "http://qt.gtimg.cn/q=" + ",".join(batch)
        raw = http_get(url)
        all_r.extend(parse_tx(raw))
    return all_r


def get_tx_index():
    """三大指数"""
    idx_map = {"sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指"}
    return get_tx_stocks(list(idx_map.keys()))


def get_stock_codes():
    """获取全A股代码列表（东方财富 → 新浪 双源自动切换）"""
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".stock_codes.json")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 86400:
        with open(cache, encoding="utf-8") as f:
            return json.load(f)

    codes = {}

    # 数据源1: 东方财富 (快) — 分页拉取全量
    try:
        page = 1
        while True:
            url = ("http://80.push2.eastmoney.com/api/qt/clist/get?"
                   f"pn={page}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f12"
                   "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14")
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
    except:
        pass

    # 数据源2: 新浪财经 (备胎)
    if not codes:
        try:
            codes = _get_codes_from_sina()
        except:
            pass

    if codes:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(codes, f, ensure_ascii=False)
    return codes


def _get_codes_from_sina():
    """从新浪财经获取全A股列表（分页获取）"""
    codes = {}
    for node, label in [("sh_a", "沪A"), ("sz_a", "深A")]:
        page = 1
        while True:
            url = (f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                   f"Market_Center.getHQNodeData?page={page}&num=100&sort=symbol&asc=1&node={node}")
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Referer": "https://finance.sina.com.cn",
            })
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read().decode("gbk" if "gbk" in str(resp.headers) else "utf-8")
                data = json.loads(raw)
                if not data:
                    break
                for r in data:
                    c = r.get("code", "")
                    n = r.get("name", "")
                    if c and n:
                        codes[c] = n
                if len(data) < 100:
                    break
                page += 1
            except:
                break
    return codes


# ==================== K线 & 技术指标 ====================

def get_kline(code, days=120):
    m = "sh" if code.replace("sh","").replace("sz","").startswith(("6","9")) else "sz"
    raw_code = code.replace("sh","").replace("sz","").zfill(6)
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={m}{raw_code},day,,,{days},qfq"
    try:
        raw = http_get(url, decode="utf-8")
        data = json.loads(raw)
        kl = data["data"][f"{m}{raw_code}"].get("day",[]) or \
             data["data"][f"{m}{raw_code}"].get("qfqday",[])
        if not kl: return None
        return [{"date": it[0], "open": float(it[1]), "close": float(it[2]),
                 "high": float(it[3]), "low": float(it[4]), "volume": float(it[5])}
                for it in kl]
    except: return None


def calc_ma(closes, n):
    if len(closes) < n: return [None]*len(closes)
    r = [None]*(n-1)
    for i in range(n-1, len(closes)):
        r.append(sum(closes[i-n+1:i+1])/n)
    return r


def calc_macd(closes, fast=12, slow=26, signal=9):
    def ema(data, p):
        r = [data[0]]
        k = 2/(p+1)
        for v in data[1:]: r.append(v*k + r[-1]*(1-k))
        return r
    ef = ema(closes, fast); es = ema(closes, slow)
    dif = [f-s for f,s in zip(ef,es)]
    dea = ema(dif, signal)
    macd = [(d-e)*2 for d,e in zip(dif,dea)]
    return dif, dea, macd


# ==================== 回测 ====================

def backtest(code, name=""):
    """双均线策略回测"""
    print(f"\n  {C.M}═══ 回测: {name or code} ═══{C.Z}\n")
    kl = get_kline(code, 500)
    if not kl: print(f"  {C.R}无K线数据{C.Z}"); return

    closes = [k["close"] for k in kl]
    ma5 = calc_ma(closes, 5)
    ma20 = calc_ma(closes, 20)

    trades = []; pos = 0; cash = 100000; init = cash; bp = 0
    for i in range(20, len(closes)):
        if None in (ma5[i], ma20[i], ma5[i-1], ma20[i-1]): continue
        if pos==0 and ma5[i-1]<=ma20[i-1] and ma5[i]>ma20[i]:
            shares = int(cash/closes[i]/100)*100
            if shares>0:
                bp=closes[i]; cash-=shares*closes[i]*1.0003; pos=shares
                trades.append(f"  {C.R}[买入]{C.Z} {kl[i]['date']}  {closes[i]:.2f}  {shares}股")
        elif pos>0 and ma5[i-1]>=ma20[i-1] and ma5[i]<ma20[i]:
            cash+=pos*closes[i]*0.997
            pnl=(closes[i]-bp)/bp*100
            col=C.R if pnl>0 else C.G
            trades.append(f"  {C.G}[卖出]{C.Z} {kl[i]['date']}  {closes[i]:.2f}  {pos}股  {col}{pnl:+.2f}%{C.Z}")
            pos=0

    if pos>0: cash+=pos*closes[-1]*0.997
    total=(cash-init)/init*100
    print(f"  初始: {init:,.0f}  →  最终: {cash:,.0f}  收益率: {pct_fmt(total)}")
    print(f"  交易: {len(trades)//2} 次\n")
    if trades:
        print(f"  {C.B}最近交易:{C.Z}")
        for t in trades[-10:]: print(t)
    print()


def backtest_v2(code, name="", hold_days_list=None):
    """策略v2.0 回测: 均线多头+温和放量 → 次日买入，持有N天卖出
    对比不同持有天数的胜率和收益"""
    if hold_days_list is None:
        hold_days_list = [1, 3, 5, 10, 20]

    kl = get_kline(code, 500)
    if not kl or len(kl) < 40:
        print(f"  {C.R}无足够K线数据{C.Z}")
        return

    closes = [k['close'] for k in kl]
    opens = [k['open'] for k in kl]
    highs = [k['high'] for k in kl]
    lows = [k['low'] for k in kl]
    volumes = [k['volume'] for k in kl]
    dates = [k['date'] for k in kl]

    # 预计算均线
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma15 = calc_ma(closes, 15)
    ma30 = calc_ma(closes, 30)

    print(f"\n  {C.M}═══ 回测v2: {name or code} ═══{C.Z}\n")
    print(f"  {C.D}策略: 多头排列+温和放量 → 次日开盘买入 → 持有N天收盘卖出{C.Z}")
    print(f"  {C.D}条件: MA5>10>15>30 | 涨幅1-5% | 量比1.2-3x | 股价<25{C.Z}\n")

    # 扫描信号日
    signals = []
    for i in range(32, len(closes)):
        # 均线多头排列
        if None in (ma5[i], ma10[i], ma15[i], ma30[i]):
            continue
        if not (ma5[i] > ma10[i] > ma15[i] > ma30[i]):
            continue

        # 当日涨幅 1%~5%
        if closes[i] <= 0 or closes[i-1] <= 0:
            continue
        pct = (closes[i] - closes[i-1]) / closes[i-1] * 100
        if pct < 1 or pct > 5:
            continue

        # 股价 < 25
        if closes[i] >= 25:
            continue

        # 温和放量: 量比 1.2x ~ 3x
        if i < 6:
            continue
        avg_vol_5 = sum(volumes[i-5:i]) / 5
        if avg_vol_5 <= 0:
            continue
        vol_ratio = volumes[i] / avg_vol_5
        if vol_ratio < 1.2 or vol_ratio > 3:
            continue

        signals.append(i)

    if not signals:
        print(f"  {C.Y}历史数据中无满足条件的信号日{C.Z}\n")
        return

    print(f"  {C.B}信号统计{C.Z}: {len(signals)} 个信号日 / {len(closes)} 个交易日 "
          f"({len(signals)/len(closes)*100:.1f}%)\n")

    # 对不同持有天数分别回测
    print(f"  {'─'*75}")
    print(f"  {'持有天数':<8s} {'交易次数':<8s} {'胜率':<10s} {'平均收益':<10s} "
          f"{'总收益':<10s} {'最大盈利':<10s} {'最大亏损':<10s}")
    print(f"  {'─'*75}")

    for hold in hold_days_list:
        wins = 0
        total_trades = 0
        returns = []

        for sig_i in signals:
            buy_i = sig_i + 1  # 次日开盘买入
            sell_i = buy_i + hold  # 持有hold天后卖出

            if sell_i >= len(closes):
                continue

            buy_price = opens[buy_i] if buy_i < len(opens) else closes[buy_i]
            sell_price = closes[sell_i]

            if buy_price <= 0 or sell_price <= 0:
                continue

            # 检查是否涨停买不到 (A股涨停=+10%)
            if buy_i > 0 and closes[buy_i-1] > 0:
                if (opens[buy_i] - closes[buy_i-1]) / closes[buy_i-1] >= 0.098:
                    continue  # 涨停开盘，买不到

            ret = (sell_price - buy_price) / buy_price * 100
            returns.append(ret)
            total_trades += 1
            if ret > 0:
                wins += 1

        if total_trades == 0:
            print(f"  {hold:<8d} {'--':<8s} {'--':<10s} {'--':<10s} {'--':<10s} {'--':<10s} {'--':<10s}")
            continue

        win_rate = wins / total_trades * 100
        avg_ret = sum(returns) / len(returns)
        total_ret = sum(returns)
        max_win = max(returns)
        max_loss = min(returns)

        def rfmt(v):
            if v > 0: return f"{C.R}{v:+.2f}%{C.Z}"
            elif v < 0: return f"{C.G}{v:+.2f}%{C.Z}"
            return f"{v:+.2f}%"

        print(f"  {hold:<8d} {total_trades:<8d} "
              f"{C.R if win_rate>=50 else C.G}{win_rate:.1f}%{C.Z}       "
              f"{rfmt(avg_ret)}     {rfmt(total_ret)}     "
              f"{C.R}{max_win:+.2f}%{C.Z}     {C.G}{max_loss:+.2f}%{C.Z}")

    print(f"  {'─'*75}")

    # 推荐最佳持有天数
    print(f"\n  {C.Y}📌 说明{C.Z}")
    print(f"  {C.D}· 以上统计不含换手率过滤（历史数据无法获取每日换手率）{C.Z}")
    print(f"  {C.D}· 实盘时筹码峰过滤会进一步提高胜率{C.Z}")
    print(f"  {C.D}· 信号密度: 平均 {len(closes)//max(len(signals),1)} 天出现一次信号{C.Z}")
    print()


# ==================== 显示 ====================

def show_header(indices):
    parts = []
    for idx in indices:
        n=idx["name"]; p=idx.get("pct") or 0; pr=idx.get("price")
        c=C.R if p>0 else (C.G if p<0 else C.W)
        a="▲" if p>0 else ("▼" if p<0 else "—")
        parts.append(f"{C.B}{n}{C.Z} {c}{pr:.2f}  {a} {p:+.2f}%{C.Z}" if pr else f"{C.B}{n}{C.Z} {pr}")
    print(f"\n  {'  │  '.join(parts)}\n")


def show_table(stocks, title="实时行情"):
    print(f"  {C.B}{title}{C.Z}  ({len(stocks)} 只)")
    print(f"  {'─'*92}")
    print(f"  {'代码':<8s} {'名称':<10s} {'最新价':>7s}  {'涨跌幅':>9s}  {'成交量(手)':>9s}  {'成交额(万)':>9s}  {'最高':>7s}  {'最低':>7s}")
    print(f"  {'─'*92}")
    for s in stocks:
        print(f"  {C.B}{s['code']:<8s}{C.Z} {s['name']:<10s}  {prc_fmt(s.get('price'),s.get('preclose'))}  "
              f"{pct_fmt(s.get('pct'))}  {s.get('volume',0):>9,.0f}  {s.get('amount',0):>9,.0f}  "
              f"{(s.get('high')or 0):>7.2f}  {(s.get('low')or 0):>7.2f}")
    print(f"  {'─'*92}")
    up_n=sum(1 for s in stocks if (s.get("pct")or 0)>0)
    dn_n=sum(1 for s in stocks if (s.get("pct")or 0)<0)
    now=datetime.now().strftime("%H:%M:%S")
    print(f"  {C.D}{now}  |  涨 {C.R}{up_n}{C.D}  跌 {C.G}{dn_n}{C.D}  |  Ctrl+C 退出{C.Z}\n")


def show_kline(code, name=""):
    kl = get_kline(code, 120)
    if not kl: print(f"  {C.R}无K线数据{C.Z}"); return
    closes=[k["close"] for k in kl]
    ma5=calc_ma(closes,5); ma20=calc_ma(closes,20); ma60=calc_ma(closes,60)

    print(f"\n  {C.M}═══ 均线分析: {name or code} ═══{C.Z}\n")
    print(f"  {'日期':<12s} {'收盘':>7s}  {'MA5':>7s}  {'MA20':>7s}  {'MA60':>7s}  {'趋势'}")
    print(f"  {'─'*62}")
    for i in range(max(0,len(kl)-20), len(kl)):
        m5=ma5[i]; m20=ma20[i]; m60=ma60[i]
        trend="多头" if (m5 and m20 and m5>m20) else ("空头" if (m5 and m20) else "观望")
        tc=C.R if trend=="多头" else (C.G if trend=="空头" else C.D)
        print(f"  {kl[i]['date']:<12s} {prc_fmt(closes[i])}  "
              f"{f'{m5:7.2f}' if m5 else '     --'}  {f'{m20:7.2f}' if m20 else '     --'}  "
              f"{f'{m60:7.2f}' if m60 else '     --'}  {tc}{trend}{C.Z}")

    if ma5[-1] and ma20[-1] and ma5[-2] and ma20[-2]:
        if ma5[-2]<=ma20[-2] and ma5[-1]>ma20[-1]:
            print(f"\n  {C.R}>>> MA5金叉MA20 (买入信号) <<<{C.Z}")
        elif ma5[-2]>=ma20[-2] and ma5[-1]<ma20[-1]:
            print(f"\n  {C.G}>>> MA5死叉MA20 (卖出信号) <<<{C.Z}")
    print()


# ==================== 入口 ====================

def usage():
    print(f"""
  {C.M}╔══════════════════════════════════════════╗
  ║     A股量化工具集 v2.1 (精简版)           ║
  ║     同花顺 + 腾讯 双引擎                  ║
  ╚══════════════════════════════════════════╝{C.Z}

  {C.B}行情看板:{C.Z}
    python stock_quant.py                   全市场涨跌榜
    python stock_quant.py watch             自选股
    python stock_quant.py top 20            涨幅前20
    python stock_quant.py live 5            每5秒刷新

  {C.B}同花顺深度数据:{C.Z}
    python stock_quant.py ths 600519        个股深度(市值/PE/资金流向)

  {C.B}量化分析:{C.Z}
    python stock_quant.py ma 600519         均线分析(金叉/死叉)
    python stock_quant.py backtest 600519   双均线策略回测
    python stock_quant.py bt2 600519        多头排列策略回测
    python stock_quant.py cmp 600519        双回测对比

  {C.B}自选股管理:{C.Z}
    python stock_quant.py search 茅台        搜索股票
    python stock_quant.py import FILE       从文件导入自选股
    python stock_quant.py autoload          自动检测同花顺自选股

  {C.M}📊 选股策略 → 策略目录:{C.Z}
    D:\\AI小秋\\策略量化\\策略1\\scanner.py
  """)


def main():
    if len(sys.argv) < 2:
        cmd = "board"
    else:
        cmd = sys.argv[1]

    # ========== 看板/行情 ==========

    if cmd in ("board", "b"):
        wl = load_watchlist()
        # 全市场用腾讯批量
        all_codes = get_stock_codes()
        if all_codes:
            tx_codes = [f"sh{c}" if c.startswith(("6","9")) else f"sz{c}" for c in all_codes]
            stocks = get_tx_stocks(tx_codes)
        else:
            stocks = get_tx_stocks(list(wl.keys()))

        show_header(get_tx_index())
        valid = [s for s in stocks if s.get("pct") is not None]
        valid.sort(key=lambda s: s["pct"], reverse=True)
        top15 = valid[:15]; bot15 = valid[-15:]
        seen = set(); merged = []
        for s in top15 + list(reversed(bot15)):
            if s["code"] not in seen: seen.add(s["code"]); merged.append(s)
        show_table(merged, "涨幅前15 + 跌幅前15（全市场）")

    elif cmd in ("watch", "w"):
        wl = load_watchlist()
        stocks = get_tx_stocks(list(wl.keys()))
        show_header(get_tx_index())
        show_table(stocks, "自选股")

    elif cmd in ("top", "up"):
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        all_codes = get_stock_codes()
        if all_codes:
            tx_codes = [f"sh{c}" if c.startswith(("6","9")) else f"sz{c}" for c in all_codes]
            stocks = get_tx_stocks(tx_codes)
        else:
            stocks = get_tx_stocks(list(load_watchlist().keys()))
        show_header(get_tx_index())
        valid = [s for s in stocks if s.get("pct") is not None]
        valid.sort(key=lambda s: s["pct"], reverse=True)
        show_table(valid[:n], f"涨幅 Top {n}")

    elif cmd in ("down", "drop"):
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        all_codes = get_stock_codes()
        if all_codes:
            tx_codes = [f"sh{c}" if c.startswith(("6","9")) else f"sz{c}" for c in all_codes]
            stocks = get_tx_stocks(tx_codes)
        else:
            stocks = get_tx_stocks(list(load_watchlist().keys()))
        show_header(get_tx_index())
        valid = [s for s in stocks if s.get("pct") is not None]
        valid.sort(key=lambda s: s["pct"])
        show_table(valid[:n], f"跌幅 Top {n}")

    elif cmd in ("live", "refresh"):
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        wl = load_watchlist()
        print(f"\n  {C.Y}每 {interval}s 刷新, Ctrl+C 退出{C.Z}")
        try:
            while True:
                os.system("cls" if sys.platform=="win32" else "clear")
                show_header(get_tx_index())
                show_table(get_tx_stocks(list(wl.keys())), "自选股")
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n  {C.B}拜拜!{C.Z}\n")

    # ========== 同花顺深度数据 ==========

    elif cmd == "ths":
        code = sys.argv[2].zfill(6) if len(sys.argv) > 2 else "600519"
        show_money_flow(code)

    elif cmd == "flow":
        code = sys.argv[2].zfill(6) if len(sys.argv) > 2 else "600519"
        show_money_flow(code)

    # ========== 量化分析 ==========

    elif cmd == "ma":
        code = sys.argv[2].zfill(6) if len(sys.argv) > 2 else "600519"
        all_codes = get_stock_codes()
        name = all_codes.get(code, "")
        show_kline(code, name)

    elif cmd == "backtest":
        code = sys.argv[2] if len(sys.argv) > 2 else "600519"
        all_codes = get_stock_codes()
        name = all_codes.get(code, "")
        backtest(code, name)

    elif cmd == "bt2":
        code = sys.argv[2] if len(sys.argv) > 2 else "600519"
        all_codes = get_stock_codes()
        name = all_codes.get(code, "")
        backtest_v2(code, name)

    elif cmd == "cmp":
        code = sys.argv[2] if len(sys.argv) > 2 else "600519"
        all_codes = get_stock_codes()
        name = all_codes.get(code, "")
        backtest(code, name)
        backtest_v2(code, name)

    # ========== 自选股管理 ==========

    elif cmd == "search":
        keyword = sys.argv[2] if len(sys.argv) > 2 else ""
        all_codes = get_stock_codes()
        matches = [(c,n) for c,n in all_codes.items() if keyword in n or keyword in c]
        if matches:
            print(f"\n  {C.B}搜索 '{keyword}': {len(matches)} 结果{C.Z}\n")
            for code, name in matches[:30]:
                print(f"  {C.B}{code}{C.Z}  {name}")
            # 行情预览
            top_matches = matches[:8]
            tx_codes = [f"sh{c}" if c.startswith(("6","9")) else f"sz{c}" for c,_ in top_matches]
            show_table(get_tx_stocks(tx_codes), f"'{keyword}' 行情")
        else:
            print(f"  {C.Y}未找到 '{keyword}'{C.Z}")

    elif cmd in ("import", "load"):
        path = sys.argv[2] if len(sys.argv) > 2 else ""
        if not path:
            print(f"  {C.Y}用法: python stock_quant.py import 文件路径{C.Z}")
            print(f"  {C.D}支持: 同花顺导出的自选股文件(代码\\t名称 格式){C.Z}")
        else:
            imported = import_from_ths_file(path)
            print(f"  {C.B}导入 {len(imported)} 只自选股{C.Z}")

    elif cmd == "autoload":
        path = find_ths_self_stocks()
        if path:
            print(f"\n  {C.B}找到同花顺自选股文件: {path}{C.Z}")
            imported = import_from_ths_file(path)
            print(f"  {C.B}导入 {len(imported)} 只自选股{C.Z}")
        else:
            print(f"\n  {C.Y}未找到同花顺自选股文件{C.Z}")
            print(f"  {C.D}请手动指定: python stock_quant.py import 文件路径{C.Z}")
            print(f"  {C.D}同花顺 → 工具 → 自选股导出 可导出为txt文件{C.Z}")

    elif cmd in ("list", "ls"):
        wl = load_watchlist()
        print(f"\n  {C.B}当前自选股 ({len(wl)} 只):{C.Z}\n")
        for code, name in wl.items():
            print(f"  {C.B}{code}{C.Z}  {name}")
        print()

    elif cmd in ("add",):
        if len(sys.argv) < 3:
            print(f"  {C.Y}用法: python stock_quant.py add 600519{C.Z}")
        else:
            wl = load_watchlist()
            code = sys.argv[2].zfill(6)
            prefix = "sh" if code.startswith(("6","9")) else "sz"
            # 获取名称
            stock = get_tx_stocks([f"{prefix}{code}"])
            name = stock[0]["name"] if stock else ""
            wl[f"{prefix}{code}"] = name
            save_watchlist(wl)

    elif cmd in ("del", "remove", "rm"):
        if len(sys.argv) < 3:
            print(f"  {C.Y}用法: python stock_quant.py del 600519{C.Z}")
        else:
            wl = load_watchlist()
            code = sys.argv[2].zfill(6)
            prefix = "sh" if code.startswith(("6","9")) else "sz"
            key = f"{prefix}{code}"
            if key in wl:
                del wl[key]
                save_watchlist(wl)

    else:
        usage()


if __name__ == "__main__":
    main()
