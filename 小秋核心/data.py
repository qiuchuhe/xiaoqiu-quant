# -*- coding: utf-8 -*-
"""小秋核心 · 数据层（腾讯行情 / K线 / 股票列表 / 同花顺深度）"""

import os, time, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from .utils import http_get, http_json, to_tx_code, to_raw_code, get_market

# ═══════════════════════════════════════════
# 股票列表（东方财富 → 缓存24h）
# ═══════════════════════════════════════════

def get_stock_list(cache_dir=None, cache_hours=24):
    """获取全A股代码→名称映射，24h缓存"""
    if cache_dir is None:
        cache_dir = os.path.dirname(os.path.abspath(__file__))
    cache_path = os.path.join(cache_dir, ".stock_list_cache.json")

    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < cache_hours * 3600:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

    codes = {}
    fetch_ok = False
    try:
        page = 1
        while True:
            url = (
                "https://push2.eastmoney.com/api/qt/clist/get?"
                f"pn={page}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f12"
                "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14"
            )
            raw = http_get(url, decode="utf-8", timeout=10)
            data = json.loads(raw)
            items = data["data"].get("diff", [])
            if not items:
                break
            for r in items:
                codes[r["f12"]] = r["f14"]
            if page * 100 >= data["data"].get("total", 0):
                break
            page += 1
        fetch_ok = True
    except Exception:
        pass

    if codes and fetch_ok:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(codes, f, ensure_ascii=False)
    elif not codes and os.path.exists(cache_path):
        # 网络失败时回退到旧缓存（股票代码列表变化极慢，旧数据完全可用）
        with open(cache_path, encoding="utf-8") as f:
            codes = json.load(f)
    return codes


# ═══════════════════════════════════════════
# 腾讯行情（实时行情 + K线）
# ═══════════════════════════════════════════

def _parse_tencent(raw):
    """解析腾讯 v_xx="1~name~code~price~..." 格式"""
    results = []
    for line in raw.strip().split(";\n"):
        m = re.search(r'="(.+)"$', line.strip())
        if not m:
            continue
        f = m.group(1).split("~")
        if len(f) < 40:
            continue
        try:
            price = float(f[3]) if f[3] else 0
            preclose = float(f[4]) if f[4] else 0
            pct = ((price - preclose) / preclose * 100) if (price and preclose) else 0
            results.append({
                "code": f[2], "name": f[1], "price": price,
                "pct": round(pct, 2), "preclose": preclose,
                "open": float(f[5]) if f[5] else 0,
                "volume": float(f[6]) if f[6] else 0,
                "high": float(f[33]) if len(f) > 33 and f[33] else 0,
                "low": float(f[34]) if len(f) > 34 and f[34] else 0,
                "amount": float(f[37]) if len(f) > 37 and f[37] else 0,
                "turnover": float(f[38]) if len(f) > 38 and f[38] else 0,
                "time": f[30] if len(f) > 30 else "",
            })
        except Exception:
            continue
    return results


def get_quotes(codes, workers=10):
    """腾讯批量实时行情 → list[dict]（并发）"""
    if isinstance(codes, str):
        codes = [codes]
    tx_codes = [to_tx_code(c) for c in codes]
    results = []

    batches = [tx_codes[i:i + 50] for i in range(0, len(tx_codes), 50)]

    def _fetch(batch):
        url = "http://qt.gtimg.cn/q=" + ",".join(batch)
        try:
            return _parse_tencent(http_get(url, timeout=10))
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=min(workers, len(batches))) as ex:
        futures = {ex.submit(_fetch, b): i for i, b in enumerate(batches)}
        for fut in as_completed(futures):
            try:
                results.extend(fut.result())
            except Exception:
                continue
    return results


def get_index():
    """获取三大指数"""
    idx_map = {"sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指"}
    codes = list(idx_map.keys())
    url = "http://qt.gtimg.cn/q=" + ",".join(codes)
    raw = http_get(url)
    results = _parse_tencent(raw)
    for r in results:
        r["name"] = idx_map.get(r.get("code", ""), r["name"])
    return results


def get_kline(code, days=60):
    """获取个股日K线（腾讯前复权）"""
    raw = to_raw_code(code)
    m = get_market(code)
    url = (
        f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
        f"param={m}{raw},day,,,{days},qfq"
    )
    try:
        data = json.loads(http_get(url, decode="utf-8"))
        kl = (
            data["data"][f"{m}{raw}"].get("day", [])
            or data["data"][f"{m}{raw}"].get("qfqday", [])
        )
        if not kl:
            return None
        return [
            {
                "date": it[0], "open": float(it[1]), "close": float(it[2]),
                "high": float(it[3]), "low": float(it[4]), "volume": float(it[5]),
            }
            for it in kl
        ]
    except Exception:
        return None


# ═══════════════════════════════════════════
# 同花顺深度数据
# ═══════════════════════════════════════════

def get_ths_stock(code):
    """获取单只股票同花顺深度数据（PE/PB/市值/涨跌停/资金流向）"""
    raw = to_raw_code(code)
    url = f"http://d.10jqka.com.cn/v2/realhead/hs_{raw}/last.js"
    try:
        raw_data = http_get(url, timeout=8, decode="gbk")
        m = re.search(r'\((\{.*\})\)', raw_data, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(1))
        items = data.get("items", {})
        if not items:
            return None

        def f(key):
            return float(items.get(key) or 0)

        return {
            "code": str(items.get("5", code)),
            "name": items.get("name", ""),
            "price": f("10"), "preclose": f("6"), "pct": f("199112"),
            "high": f("8"), "low": f("9"), "open": f("7"),
            "volume": f("25"), "amount": f("19") / 10000,
            "pe_dynamic": f("69"), "pe_static": f("70"), "pb": f("74"),
            "total_mv": f("3541450"), "float_mv": f("3475914"),
            "limit_up": f("30"), "limit_down": f("31"),
            "turnover": f("1968584"), "amplitude": f("526792"),
            "time": items.get("time", ""), "_source": "同花顺",
        }
    except Exception:
        return None


def get_money_flow(code):
    """获取个股资金流向"""
    raw = to_raw_code(code)
    try:
        url = f"http://ff.10jqka.com.cn/ff/stockdetail/code/{raw}"
        return json.loads(http_get(url, timeout=10, decode="gbk"))
    except Exception:
        return None
