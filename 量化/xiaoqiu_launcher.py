# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════╗
║   🦀 小秋量化工具箱 — 统一启动器 v2.0     ║
║   策略扫描 | 预警守护 | 行情看板 | 回测   ║
╚══════════════════════════════════════════════╝

用法:
  python xiaoqiu_launcher.py          交互菜单
  python xiaoqiu_launcher.py scan     策略一扫描
  python xiaoqiu_launcher.py alert    启动预警守护
"""

import sys, os, subprocess, time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGY1_DIR = os.path.join(os.path.dirname(BASE_DIR), "策略量化", "策略1")
STRATEGY2_DIR = os.path.join(os.path.dirname(BASE_DIR), "策略量化", "策略2")
PYTHON = sys.executable

# ─── 颜色 ───
class C:
    R = "\033[1;31m"; G = "\033[1;32m"; Y = "\033[1;33m"
    B = "\033[1;36m"; M = "\033[1;35m"; D = "\033[2;37m"; Z = "\033[0m"


def run_script(script_name, *args, cwd=None):
    """运行脚本"""
    if cwd is None:
        cwd = BASE_DIR
    path = os.path.join(cwd, script_name)
    cmd = [PYTHON, path] + list(args)
    print(f"{C.D}  → {' '.join(cmd)}{C.Z}")
    try:
        result = subprocess.run(cmd, cwd=cwd)
        return result.returncode
    except KeyboardInterrupt:
        print(f"\n{C.Y}⏸️  已中断{C.Z}")
        return 130


def show_banner():
    now = datetime.now()
    weekday = ["周一","周二","周三","周四","周五","周六","周日"][now.weekday()]
    is_market = weekday not in ["周六","周日"]

    print(f"""
{C.M}╔══════════════════════════════════════════════════╗
║                                                  ║
║      🦀  小 秋 量 化 工 具 箱  🦀               ║
║      XiaoQiu Quant Toolbox v2.0                  ║
║                                                  ║
║   {now.strftime('%Y-%m-%d')} {weekday}                              ║
║   市场: {'🟢 交易日' if is_market else '🔴 休市'}                              ║
╚══════════════════════════════════════════════════╝{C.Z}
""")


def menu_strategy1():
    """策略一扫描"""
    print(f"\n{C.M}📊 策略一：均线多头+温和放量{C.Z}")
    print(f"  1. 盘后全量扫描")
    print(f"  2. 盘中实时监控（5分钟）")
    print(f"  3. 单次快扫")
    choice = input("  > ").strip()

    if choice == "1":
        run_script("scanner.py", cwd=STRATEGY1_DIR)
    elif choice == "2":
        run_script("scanner.py", "--live", "300", cwd=STRATEGY1_DIR)
    elif choice == "3":
        run_script("scanner.py", "--once", cwd=STRATEGY1_DIR)


def menu_strategy2():
    """策略二扫描"""
    print(f"\n{C.M}🔥 策略二：3进4连板擒龙{C.Z}")
    print(f"  1. 今日分析（生成报告）")
    print(f"  2. 盘中实时监控（10秒刷新）")
    print(f"  3. 回测近30天成功率")
    choice = input("  > ").strip()

    if choice == "1":
        run_script("three_to_four.py", cwd=STRATEGY2_DIR)
    elif choice == "2":
        run_script("three_to_four.py", "--watch", cwd=STRATEGY2_DIR)
    elif choice == "3":
        run_script("three_to_four.py", "--backtest", "30", cwd=STRATEGY2_DIR)


def menu_combined_scout():
    """策略一+策略二 同时侦察"""
    print(f"\n{C.R}🔥 双策略联合实时侦察{C.Z}")
    print(f"  策略一：均线多头+温和放量 → 盘中5分钟扫描")
    print(f"  策略二：3进4连板擒龙 → 盘中10秒扫描")
    print(f"  {C.D}两个进程同时运行，Ctrl+C 退出{C.Z}")
    print()

    try:
        proc1 = subprocess.Popen(
            [PYTHON, "scanner.py", "--live", "300"],
            cwd=STRATEGY1_DIR,
        )
        proc2 = subprocess.Popen(
            [PYTHON, "three_to_four.py", "--watch"],
            cwd=STRATEGY2_DIR,
        )
        print(f"  {C.G}✅ 策略一 PID:{proc1.pid} | 策略二 PID:{proc2.pid}{C.Z}")
        print(f"  {C.D}按 Ctrl+C 停止全部...{C.Z}\n")

        # 等任意一个退出
        proc1.wait()
        proc2.wait()
    except KeyboardInterrupt:
        proc1.terminate()
        proc2.terminate()
        print(f"\n{C.Y}⏸️  双策略侦察已停止{C.Z}")


def menu_alert():
    """预警守护"""
    print(f"\n{C.B}🛡️  启动止损止盈预警守护...{C.Z}")
    print(f"  模式: 前台持续监控 (Ctrl+C 退出)")
    run_script("alert_daemon.py")


def menu_monitor():
    """双策略实时监控"""
    print(f"\n{C.B}📡 启动实时监控...{C.Z}")
    print(f"  注意: 需要同花顺开着才能做实盘")
    mode = input(f"  模拟盘(y)还是实盘(n)? [y/n]: ").strip().lower()
    if mode == "n":
        print(f"{C.R}⚠️  实盘模式! 将使用真金白银!{C.Z}")
        run_script("xiaoqiu_monitor.py", "--interval", "60")
    else:
        run_script("xiaoqiu_monitor.py", "--dry", "--interval", "60")


def menu_backtest():
    """回测"""
    code = input("  输入股票代码: ").strip()
    if code:
        run_script("stock_quant.py", "bt2", code)


def menu_quote():
    """行情"""
    print(f"\n{C.B}📈 行情看板{C.Z}")
    print(f"  1. 全市场涨跌榜")
    print(f"  2. 自选股")
    print(f"  3. 涨幅Top20")
    print(f"  4. 个股深度(同花顺)")
    choice = input("  > ").strip()

    if choice == "1":
        run_script("stock_quant.py")
    elif choice == "2":
        run_script("stock_quant.py", "watch")
    elif choice == "3":
        run_script("stock_quant.py", "top", "20")
    elif choice == "4":
        code = input("  代码: ").strip()
        if code:
            run_script("stock_quant.py", "ths", code)


def interactive_menu():
    while True:
        now = datetime.now()
        in_market = now.weekday() < 5 and "09:30" <= now.strftime("%H:%M") <= "15:00"
        market_status = f"{C.G}🟢 交易中{C.Z}" if in_market else f"{C.D}⏸️ 非交易时间{C.Z}"

        print(f"""
{C.M}╔══════════════════════════════════════════════╗
║  🦀 小秋量化工具箱 v2.0  {now.strftime('%H:%M')} {market_status}  ║
╠══════════════════════════════════════════════╣
║                                              ║
║  {C.Y}1.{C.Z} 📊 策略一：均线多头+温和放量              ║
║  {C.Y}2.{C.Z} 🔥 策略二：3进4连板擒龙                   ║
║  {C.Y}3.{C.Z} 🚀 双策略联合实时侦察                     ║
║  {C.Y}4.{C.Z} 📡 持仓监控（xiaoqiu_monitor）           ║
║  {C.Y}5.{C.Z} 🛡️  止损止盈预警守护                      ║
║  {C.Y}6.{C.Z} 📈 行情看板                                ║
║  {C.Y}7.{C.Z} ⏪ 策略回测                                  ║
║                                              ║
║  {C.D}q.{C.Z} 👋 退出                                      ║
║                                              ║
╚══════════════════════════════════════════════╝{C.Z}

💡 建议: 交易时段选 {C.R}3{C.Z} 双策略同时侦察 + 另开窗口选 {C.Y}4{C.Z} 持仓监控
""")

        choice = input("  🦀 > ").strip()

        if choice == "1":
            menu_strategy1()
        elif choice == "2":
            menu_strategy2()
        elif choice == "3":
            menu_combined_scout()
        elif choice == "4":
            menu_monitor()
        elif choice == "5":
            menu_alert()
        elif choice == "6":
            menu_quote()
        elif choice == "7":
            menu_backtest()
        elif choice.lower() == "q":
            print(f"\n{C.M}🦀 小秋下班了! 拜拜~ 👋{C.Z}\n")
            break
        else:
            print(f"{C.R}不清楚选什么... 输入 1-7 或 q{C.Z}")

        if choice in ("1","2","3","4","5","6","7"):
            input(f"\n{C.D}按回车继续...{C.Z}")


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "scan":
            run_script("scanner.py", cwd=STRATEGY1_DIR)
        elif cmd == "alert":
            run_script("alert_daemon.py")
        elif cmd == "help":
            print(f"""
{C.M}小秋量化工具箱 v2.0 快捷方式:{C.Z}
  python xiaoqiu_launcher.py scan     策略一扫描
  python xiaoqiu_launcher.py alert    预警守护
  python xiaoqiu_launcher.py          交互菜单
""")
        else:
            print(f"未知命令: {cmd}")
        return

    show_banner()
    interactive_menu()


if __name__ == "__main__":
    main()
