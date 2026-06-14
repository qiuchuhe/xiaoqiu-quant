# -*- coding: utf-8 -*-
"""小秋核心 · 技术指标（MA / MACD / 量比）"""


def calc_ma(values, period):
    """简单移动平均"""
    if len(values) < period:
        return [None] * len(values)
    result = [None] * (period - 1)
    for i in range(period - 1, len(values)):
        result.append(sum(values[i - period + 1 : i + 1]) / period)
    return result


def calc_vol_ratio(volumes, period=5):
    """量比 = 当日量 / N日均量"""
    if len(volumes) < period + 1:
        return None
    avg = sum(volumes[-(period + 1) : -1]) / period
    return volumes[-1] / avg if avg > 0 else None


def calc_macd(closes, fast=12, slow=26, signal=9):
    """MACD 指标"""
    def ema(data, p):
        r = [data[0]]
        k = 2 / (p + 1)
        for v in data[1:]:
            r.append(v * k + r[-1] * (1 - k))
        return r

    ef = ema(closes, fast)
    es = ema(closes, slow)
    dif = [f - s for f, s in zip(ef, es)]
    dea = ema(dif, signal)
    macd = [(d - e) * 2 for d, e in zip(dif, dea)]
    return dif, dea, macd
