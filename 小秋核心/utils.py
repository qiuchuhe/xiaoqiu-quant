# -*- coding: utf-8 -*-
"""小秋核心 · 工具函数（HTTP / 颜色 / 编码 / 代码转换）"""

import sys
import urllib.request

# ─── 编码 ───
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─── HTTP ───
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def http_get(url, timeout=10, decode="gbk"):
    """HTTP GET 请求，自动解码"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode(decode, errors="replace")


def http_json(url, referer=None, timeout=12):
    """HTTP GET → JSON"""
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        import json
        return json.loads(resp.read())


# ─── 颜色 ───
class C:
    R = "\033[1;31m"
    G = "\033[1;32m"
    Y = "\033[1;33m"
    B = "\033[1;36m"
    M = "\033[1;35m"
    W = "\033[1;37m"
    D = "\033[2;37m"
    Z = "\033[0m"


# ─── 代码转换 ───
def to_tx_code(code):
    """'600519' → 'sh600519'"""
    raw = str(code).zfill(6)
    return f"sh{raw}" if raw.startswith(("6", "9")) else f"sz{raw}"


def to_raw_code(code):
    """'sh600519' / 'sz000001' / '600519' → '600519'"""
    return str(code).replace("sh", "").replace("sz", "").zfill(6)


def get_market(code):
    """判断市场: 'sh' or 'sz'"""
    raw = to_raw_code(code)
    return "sh" if raw.startswith(("6", "9")) else "sz"


# ─── 格式化 ───
def pct_fmt(v):
    """涨跌幅彩色格式化"""
    if v is None:
        return f"{C.D}     --{C.Z}"
    if v > 0:
        return f"{C.R}{v:+7.2f}%{C.Z}"
    elif v < 0:
        return f"{C.G}{v:+7.2f}%{C.Z}"
    return f"{C.D}{v:+7.2f}%{C.Z}"


def prc_fmt(v, ref=None):
    """价格格式化"""
    if v is None:
        return f"{C.D}     --{C.Z}"
    s = f"{v:7.2f}"
    if ref is not None and v >= ref:
        return f"{C.R}{s}{C.Z}"
    elif ref is not None and v < ref:
        return f"{C.G}{s}{C.Z}"
    return s
