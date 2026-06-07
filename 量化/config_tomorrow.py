# -*- coding: utf-8 -*-
"""明日(6月3日)监控配置生成器"""
import sys, io, json, os
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 明日监控池（合并来源）
# ============================================================
MONITOR_LIST = [
    # ── 今日信号触发（用户策略）──
    {"code": "600222", "name": "太龙药业", "strategy": "B", "max_price": 8.50,  "hold_days": 1,
     "reason": "自选股信号⭐ MA多头+放量 8.17元"},
    {"code": "601699", "name": "潞安环能", "strategy": "B", "max_price": 18.50, "hold_days": 1,
     "reason": "全市场信号 MA多头+量比2.32x 17.80元"},

    # ── 原监控池（延续观察）──
    {"code": "002351", "name": "漫步者",   "strategy": "B", "max_price": 11.60, "hold_days": 1,
     "reason": "原监控池 多头排列"},
    {"code": "002568", "name": "百润股份", "strategy": "A", "max_price": 20.50, "hold_days": 0,
     "reason": "原监控池 均线交叉"},
    {"code": "600020", "name": "中原高速", "strategy": "B", "max_price": 4.20,  "hold_days": 5,
     "reason": "原监控池 低价波段"},

    # ── 热点板块新增（涨停次日观察，不追高）──
    {"code": "000586", "name": "汇源通信", "strategy": "A", "max_price": 17.50, "hold_days": 0,
     "reason": "通信涨停16.74 等回调金叉"},
    {"code": "000700", "name": "模塑科技", "strategy": "A", "max_price": 16.00, "hold_days": 0,
     "reason": "机器人涨停15.07 等回调金叉"},
    {"code": "002031", "name": "巨轮智能", "strategy": "B", "max_price": 6.80,  "hold_days": 2,
     "reason": "机器人低位6.25 等放量突破"},
    {"code": "002369", "name": "卓翼科技", "strategy": "B", "max_price": 7.00,  "hold_days": 2,
     "reason": "5G物联网6.52 低位待涨"},
]

# ============================================================
# 保存明日计划
# ============================================================
plan = {
    "date": "2026-06-03",
    "monitor_list": MONITOR_LIST,
    "strategy_params": {
        "stop_loss_pct": -5.0,
        "take_profit_pct": 10.0,
        "max_position": 1,
        "fixed_shares": 100,
        "init_capital": 3000,
        "price_max": 20,
    },
    "watchlist_total": 107,
    "market_notes": [
        "今日CPO/光纤/通信设备领涨，但核心标的均超20元",
        "涨停股(汇源/模塑)明天如高开不追，等回调",
        "太龙药业、潞安环能今日触发用户策略信号",
        "重点观察太龙药业(自选股+信号)明天开盘",
    ]
}

plan_file = os.path.join(BASE, ".tomorrow_plan.json")
with open(plan_file, "w", encoding="utf-8") as f:
    json.dump(plan, f, ensure_ascii=False, indent=2)

print("=" * 60)
print("  📋 明日(6/3)监控计划已生成")
print("=" * 60)
print(f"\n  监控标的: {len(MONITOR_LIST)} 只\n")
for i, s in enumerate(MONITOR_LIST):
    tag = "[SIG]" if "信号" in s.get("reason","") else ("[HOT]" if "涨停" in s.get("reason","") else "[WATCH]")
    print(f"  {tag} {s['code']} {s['name']:<6} 上限{s['max_price']:.2f} | 策略{s['strategy']} | {s['reason']}")

print(f"\n  策略: A=均线交叉 B=多头排列+放量")
print(f"  风控: 止损-5% | 止盈+10% | 单票100股 | 最多持仓1只")
print(f"  计划文件: {plan_file}")

# ============================================================
# 更新 monitor 状态文件（重置持仓）
# ============================================================
state_file = os.path.join(BASE, ".monitor_state.json")
new_state = {
    "positions": {},
    "trades": [],
    "capital": 3000,
    "last_signal": {}
}
with open(state_file, "w", encoding="utf-8") as f:
    json.dump(new_state, f, ensure_ascii=False, indent=2)
print(f"\n  ✅ 持仓状态已重置 (本金3000, 空仓)")
print(f"\n{'='*60}")
print("  明天开盘运行: python xiaoqiu_monitor.py --dry")
print(f"{'='*60}")
