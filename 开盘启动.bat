@echo off
chcp 65001 >nul
title 🦀 小秋量化 — 开盘作战系统

echo.
echo ╔══════════════════════════════════════════════╗
echo ║  🦀 小秋量化 开盘作战系统                     ║
echo ║  交易日 9:25 自动启动                         ║
echo ╚══════════════════════════════════════════════╝
echo.

cd /d "D:\AI小秋\量化"

echo 🚀 启动 窗口1：双策略联合侦察...
start "🦀 双策略侦察" cmd /k "python xiaoqiu_launcher.py scout-combined"

echo 📡 启动 窗口2：持仓监控（2分钟扫描）
timeout /t 5 /nobreak >nul
start "📡 持仓监控" cmd /k "python xiaoqiu_monitor.py --interval 120"

echo.
echo ✅ 两个窗口已启动
echo    🟢 窗口1: 策略一+策略二 实时扫描
echo    🟢 窗口2: 持仓止损止盈监控
echo.
echo 收盘后关掉这两个窗口即可。
echo ═══════════════════════════════════════════════

timeout /t 3 /nobreak >nul
exit
