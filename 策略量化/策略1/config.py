# -*- coding: utf-8 -*-
"""
策略一：均线多头 + 温和放量 参数配置
"""

# ═══════════════════════════════════════════
# 选股条件
# ═══════════════════════════════════════════

CONDITIONS = {
    # 股价上限（元）
    "price_max": 20,

    # 均线多头排列：MA5 > MA10 > MA20
    "ma_order": ["ma5", "ma10", "ma20"],

    # 换手率区间（%）
    "turnover_min": 5.0,
    "turnover_max": 10.0,

    # 量比区间（今日量 / 5日均量）
    "vol_ratio_min": 1.0,
    "vol_ratio_max": 10.0,

    # 排除板块（代码前缀）
    "exclude_prefix": ["300", "301", "688", "8", "4"],
    # 300/301=创业板  688=科创板  8=北证  4=三板

    # 排除 ST
    "exclude_st": True,

    # 获利盘上限（%，同花顺人工核查）
    "profit_chip_max": 80,
}

# ═══════════════════════════════════════════
# 买入信号
# ═══════════════════════════════════════════

BUY_SIGNALS = {
    # 买点A：回调MA10不破 + 收阳线
    "A_pullback_ma10": {
        "name": "回调MA10不破",
        "description": "收盘价 ≥ MA10 × 0.98（回踩不破）且 收盘 > 开盘（收阳）",
        "confirm": "收盘",
        "action": "次日开盘买入",
    },

    # 买点B：放量站稳MA5
    "B_breakout_ma5": {
        "name": "放量站稳MA5",
        "description": "收盘价 ≥ MA5 且 量比 ≥ 1.5",
        "confirm": "盘中/收盘均可",
        "action": "次日开盘买入",
    },
}

# ═══════════════════════════════════════════
# 卖出信号（按优先级排序）
# ═══════════════════════════════════════════

SELL_SIGNALS = [
    {
        "id": "hard_stop",
        "name": "硬止损",
        "priority": 1,
        "condition": "亏损 ≥ 5%",
        "action": "次日开盘无条件卖出",
    },
    {
        "id": "trailing_stop",
        "name": "跟踪止盈",
        "priority": 2,
        "condition": "盈利>3%激活，从最高点回撤5%卖出",
        "action": "盘中触发即卖",
    },
    {
        "id": "ma5_cross_ma10",
        "name": "短期趋势破坏",
        "priority": 3,
        "condition": "MA5 下穿 MA10",
        "action": "次日开盘卖出",
    },
    {
        "id": "volume_spike_stall",
        "name": "放量滞涨",
        "priority": 4,
        "condition": "当日量比 > 2 且 涨幅 < 1%",
        "action": "当日卖出",
    },
]

# ═══════════════════════════════════════════
# 仓位与资金
# ═══════════════════════════════════════════

POSITION = {
    "init_capital": 3000,      # 初始本金
    "fixed_shares": 100,        # 每笔固定股数
    "max_holdings": 2,          # 最大持仓只数
    "stop_loss_pct": -5.0,      # 硬止损线
    "take_profit_pct": 10.0,    # 固定止盈线（旧，保留兼容）
    "trailing_stop_pct": 5.0,   # 跟踪止盈：从最高点回撤5%就卖
    "trailing_activate_pct": 3.0,  # 盈利超3%后激活跟踪止盈
}

# ═══════════════════════════════════════════
# 数据源
# ═══════════════════════════════════════════

DATA = {
    "kline_days": 60,           # 取多少天K线
    "kline_source": "tencent",  # 腾讯财经（免费/国内直连）
    "quote_source": "tencent",  # 实时行情源
    "stock_list_cache_hours": 720,  # 股票代码变化极慢，30天缓存
}
