# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
自动交易引擎 v0.1 — 基于 easytrader + 同花顺
券商: 国信证券 (通过同花顺下单端)
⚠️  请先用模拟盘/小资金测试 !!!
"""

import easytrader
import time, os, sys

# ==================== 配置 ====================
XIADAN_PATH = r"D:\下载\同花顺\同花顺\xiadan.exe"  # 同花顺下单程序

# 监控列表（今日筹码峰过关的3只）
WATCH_LIST = [
    {"code": "002351", "name": "漫步者", "max_price": 11.60, "stop_loss": -5.0},
    {"code": "002568", "name": "百润股份", "max_price": 20.50, "stop_loss": -5.0},
    {"code": "600020", "name": "中原高速", "max_price": 4.20, "stop_loss": -5.0},
]

# ==================== 连接同花顺 ====================

def connect_ths():
    """连接同花顺下单端（国信证券）"""
    print("正在连接同花顺下单端...")
    user = easytrader.use('ths')  # 通用同花顺客户端

    # 连接已运行的同花顺
    user.connect(XIADAN_PATH)

    print("✅ 连接成功！")
    return user


# ==================== 查询 ====================

def show_status(user):
    """显示当前账户状态"""
    print("\n" + "=" * 50)
    print("📊 账户状态")
    print("=" * 50)

    try:
        # 查余额
        balance = user.balance
        if balance:
            print(f"💰 可用资金: {balance.get('enable_balance', '--')}")

        # 查持仓
        positions = user.position
        if positions:
            print(f"\n📦 当前持仓 ({len(positions)} 只):")
            for p in positions:
                print(f"  {p.get('stock_code', '?')} {p.get('stock_name', '?')} "
                      f"数量:{p.get('current_amount', 0)} 成本:{p.get('cost_price', 0)} "
                      f"现价:{p.get('current_price', 0)} "
                      f"盈亏:{p.get('profit', 0):+.2f}%")
        else:
            print("  (空仓)")
    except Exception as e:
        print(f"⚠️ 查询异常: {e}")

    print("=" * 50)


# ==================== 交易 ====================

def buy_stock(user, code, price, amount=100):
    """买入股票（默认100股）"""
    print(f"\n🔴 买入 {code} 价格≈{price} 数量={amount}股")
    try:
        result = user.buy(code, price=price, amount=amount)
        print(f"✅ 买入委托已提交: {result}")
        return result
    except Exception as e:
        print(f"❌ 买入失败: {e}")
        return None


def sell_stock(user, code, price, amount=100):
    """卖出股票"""
    print(f"\n🟢 卖出 {code} 价格≈{price} 数量={amount}股")
    try:
        result = user.sell(code, price=price, amount=amount)
        print(f"✅ 卖出委托已提交: {result}")
        return result
    except Exception as e:
        print(f"❌ 卖出失败: {e}")
        return None


# ==================== 主菜单 ====================

def main():
    print("""
╔══════════════════════════════════════╗
║   🦀 小秋自动交易引擎 v0.1          ║
║   国信证券 → 同花顺下单端            ║
╚══════════════════════════════════════╝
""")

    user = connect_ths()
    show_status(user)

    while True:
        print("""
┌──────────────────────────────────────┐
│ 1. 📊 刷新持仓/余额                  │
│ 2. 🔴 手动买入                       │
│ 3. 🟢 手动卖出                       │
│ 4. 🧪 测试买入100股（模拟盘先试！）  │
│ q. 退出                              │
└──────────────────────────────────────┘""")
        cmd = input("> ").strip()

        if cmd == "1":
            show_status(user)
        elif cmd == "2":
            code = input("股票代码: ").strip()
            price = float(input("价格: "))
            amount = int(input("数量(股): "))
            buy_stock(user, code, price, amount)
        elif cmd == "3":
            code = input("股票代码: ").strip()
            price = float(input("价格: "))
            amount = int(input("数量(股): "))
            sell_stock(user, code, price, amount)
        elif cmd == "4":
            print("\n🧪 测试模式: 买入100股 中原高速")
            print("⚠️ 请确认同花顺下单窗口已打开并登录!")
            input("按回车继续...")
            buy_stock(user, "600020", 4.10, 100)
        elif cmd.lower() == "q":
            print("拜拜! 👋")
            break


if __name__ == "__main__":
    main()
