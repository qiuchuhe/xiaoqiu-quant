# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════╗
║   🦀 小秋量化工具箱 — 统一启动器 v1.0     ║
║   每日报告 | 预警守护 | 模拟交易 | 自选池  ║
╚══════════════════════════════════════════════╝

用法:
  python xiaoqiu_launcher.py          交互菜单
  python xiaoqiu_launcher.py report   直接生成报告
  python xiaoqiu_launcher.py alert    启动预警守护
  python xiaoqiu_launcher.py auto     全自动模式(报告+预警)
"""

import sys, os, subprocess, time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

# ─── 颜色 ───
class C:
    R = "\033[1;31m"; G = "\033[1;32m"; Y = "\033[1;33m"
    B = "\033[1;36m"; M = "\033[1;35m"; D = "\033[2;37m"; Z = "\033[0m"


def run_script(script_name, *args):
    """运行项目内的脚本"""
    path = os.path.join(BASE_DIR, script_name)
    cmd = [PYTHON, path] + list(args)
    print(f"{C.D}  → 运行: {' '.join(cmd)}{C.Z}")
    try:
        result = subprocess.run(cmd, cwd=BASE_DIR)
        return result.returncode
    except KeyboardInterrupt:
        print(f"\n{C.Y}⏸️  已中断{C.Z}")
        return 130


def show_banner():
    """显示启动画面"""
    now = datetime.now()
    weekday = ["周一","周二","周三","周四","周五","周六","周日"][now.weekday()]
    is_market = weekday not in ["周六","周日"]

    print(f"""
{C.M}╔══════════════════════════════════════════════════╗
║                                                  ║
║      🦀  小 秋 量 化 工 具 箱  🦀               ║
║      XiaoQiu Quant Toolbox v1.0                  ║
║                                                  ║
║   {now.strftime('%Y-%m-%d')} {weekday}                              ║
║   市场: {'🟢 交易日' if is_market else '🔴 休市'}                              ║
╚══════════════════════════════════════════════════╝{C.Z}
""")


def menu_report():
    """菜单: 生成信号报告"""
    print(f"\n{C.B}📋 正在生成每日信号报告...{C.Z}")
    run_script("daily_report.py", "--print")

    # 问是否打开报告
    print(f"\n{C.Y}📄 是否在VS Code中打开报告? (y/n){C.Z}")
    choice = input("  > ").strip().lower()
    if choice == "y":
        today = datetime.now().strftime("%Y-%m-%d")
        report_path = os.path.join(BASE_DIR, "reports", f"日报_{today}.md")
        if os.path.exists(report_path):
            # 用 VS Code 或其他关联程序打开
            os.startfile(report_path) if sys.platform == "win32" else None


def menu_alert():
    """菜单: 启动预警守护"""
    print(f"\n{C.B}🛡️  启动止损止盈预警守护...{C.Z}")
    print(f"  模式: 前台持续监控 (Ctrl+C 退出)")
    print(f"  间隔: 30秒")
    run_script("alert_daemon.py")


def menu_paper():
    """菜单: 模拟盘交易台"""
    while True:
        print(f"""
{C.Y}┌──────────────────────────────────────────┐
│  🎮 模拟盘交易台                          │
├──────────────────────────────────────────┤
│  1. 📊 查看持仓状态                       │
│  2. 🔴 模拟买入                           │
│  3. 🟢 模拟卖出                           │
│  4. 📜 交易日志                           │
│  5. 📈 盈亏统计                           │
│  b. 🔙 返回                               │
└──────────────────────────────────────────┘{C.Z}""")

        choice = input("  > ").strip()

        if choice == "1":
            run_script("paper_trader.py", "status")
        elif choice == "2":
            code = input("  代码: ").strip()
            price = input("  价格: ").strip()
            reason = input("  理由(可选): ").strip()
            run_script("paper_trader.py", "buy", code, price, reason)
        elif choice == "3":
            code = input("  代码: ").strip()
            price = input("  价格: ").strip()
            reason = input("  理由(可选): ").strip()
            run_script("paper_trader.py", "sell", code, price, reason)
        elif choice == "4":
            run_script("paper_trader.py", "log")
        elif choice == "5":
            run_script("paper_trader.py", "pnl")
        elif choice.lower() == "b":
            break


def menu_watchlist():
    """菜单: 更新自选池"""
    print(f"\n{C.B}🔄 更新自选池...{C.Z}")
    run_script("update_watchlist.py")


def menu_config():
    """菜单: 生成明日计划"""
    print(f"\n{C.B}📅 生成明日监控计划...{C.Z}")
    run_script("config_tomorrow.py")


def menu_monitor():
    """菜单: 启动完整监控(原有xiaoqiu_monitor)"""
    print(f"\n{C.B}📡 启动双策略实时监控...{C.Z}")
    print(f"  注意: 需要同花顺开着才能做实盘")
    mode = input(f"  模拟盘(y)还是实盘(n)? [y/n]: ").strip().lower()
    if mode == "n":
        print(f"{C.R}⚠️  实盘模式! 将使用真金白银!{C.Z}")
        run_script("xiaoqiu_monitor.py", "--interval", "60")
    else:
        run_script("xiaoqiu_monitor.py", "--dry", "--interval", "60")


def menu_auto():
    """全自动模式"""
    print(f"""
{C.M}╔══════════════════════════════════════════════╗
║   🤖 全自动模式                             ║
║   1. 生成信号报告                            ║
║   2. 启动预警守护                            ║
╚══════════════════════════════════════════════╝{C.Z}
""")

    # Step 1: 生成报告
    print(f"{C.B}[1/2] 生成信号报告...{C.Z}")
    run_script("daily_report.py")

    # Step 2: 预警守护
    print(f"\n{C.B}[2/2] 启动预警守护...{C.Z}")
    run_script("alert_daemon.py")


def interactive_menu():
    """交互式主菜单"""
    while True:
        now = datetime.now()
        in_market = now.weekday() < 5 and "09:30" <= now.strftime("%H:%M") <= "15:00"
        market_status = f"{C.G}🟢 交易中{C.Z}" if in_market else f"{C.D}⏸️ 非交易时间{C.Z}"

        print(f"""
{C.M}╔══════════════════════════════════════════════╗
║  🦀 小秋量化工具箱        {now.strftime('%H:%M')} {market_status}  ║
╠══════════════════════════════════════════════╣
║                                              ║
║  {C.Y}1.{C.Z} 📋 生成每日信号报告                      ║
║  {C.Y}2.{C.Z} 🛡️  启动止损止盈预警守护                 ║
║  {C.Y}3.{C.Z} 🎮 模拟盘交易台                          ║
║  {C.Y}4.{C.Z} 🔄 更新自选池                            ║
║  {C.Y}5.{C.Z} 📅 生成明日监控计划                      ║
║  {C.Y}6.{C.Z} 📡 启动实时监控(xiaoqiu_monitor)         ║
║  {C.Y}7.{C.Z} 🤖 全自动模式(报告+预警)                 ║
║                                              ║
║  {C.D}q.{C.Z} 👋 退出                                  ║
║                                              ║
╚══════════════════════════════════════════════╝{C.Z}

💡 提示: 也可直接命令行运行:
  {C.D}python daily_report.py{C.Z}     生成报告
  {C.D}python alert_daemon.py --once{C.Z}  单次预警检查
  {C.D}python paper_trader.py status{C.Z}  查看模拟持仓
""")

        choice = input("  🦀 > ").strip()

        if choice == "1":
            menu_report()
        elif choice == "2":
            menu_alert()
        elif choice == "3":
            menu_paper()
        elif choice == "4":
            menu_watchlist()
        elif choice == "5":
            menu_config()
        elif choice == "6":
            menu_monitor()
        elif choice == "7":
            menu_auto()
        elif choice.lower() == "q":
            print(f"\n{C.M}🦀 小秋下班了! 拜拜~ 记得看信号报告哦 👋{C.Z}\n")
            break
        else:
            print(f"{C.R}不清楚选什么... 输入 1-7 或 q{C.Z}")

        # 每次操作后短暂停顿
        if choice in ("1","2","3","4","5","6","7"):
            input(f"\n{C.D}按回车继续...{C.Z}")


def main():
    # 命令行直达模式
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "report":
            run_script("daily_report.py", "--print")
        elif cmd == "alert":
            run_script("alert_daemon.py")
        elif cmd == "auto":
            menu_auto()
        elif cmd == "trade":
            run_script("paper_trader.py", *sys.argv[2:])
        elif cmd == "help":
            print(f"""
{C.M}小秋量化工具箱 命令行快捷方式:{C.Z}
  python xiaoqiu_launcher.py report   生成报告
  python xiaoqiu_launcher.py alert    预警守护
  python xiaoqiu_launcher.py auto     全自动模式
  python xiaoqiu_launcher.py trade status  查看模拟盘
  python xiaoqiu_launcher.py          交互菜单
""")
        else:
            print(f"未知命令: {cmd}")
        return

    # 交互菜单模式
    show_banner()
    interactive_menu()


if __name__ == "__main__":
    main()
