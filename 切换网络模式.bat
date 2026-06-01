@echo off
chcp 65001 >nul
title 🌐 网络模式切换 - 小秋

:: ============================================
:: 一键切换网络模式
:: 校园网直连 ⇄ 热点 + 梯子代理
:: ============================================

:: 检查当前代理状态
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable 2>nul | findstr "0x1" >nul
if %errorlevel% equ 0 (
    set "CURRENT_MODE=代理模式"
    set "ACTION=关闭代理，切到校园网"
    set "TARGET_ENABLE=0"
    set "NEW_MODE=🏫 校园网直连"
) else (
    set "CURRENT_MODE=校园网直连"
    set "ACTION=开启代理，切到梯子"
    set "TARGET_ENABLE=1"
    set "NEW_MODE=🔮 热点 + 梯子"
)

echo.
echo   ╔══════════════════════════════════════╗
echo   ║        🌐 网络模式切换               ║
echo   ╚══════════════════════════════════════╝
echo.
echo   当前模式: %CURRENT_MODE%
echo   即将: %ACTION%
echo.
echo   按任意键继续，或直接关窗取消...
pause >nul

if "%TARGET_ENABLE%"=="1" (
    :: ========== 开启代理模式 ==========
    echo.
    echo   🔮 正在切换到: 热点 + 梯子模式...

    :: 1. 系统代理
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f >nul
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /t REG_SZ /d "127.0.0.1:7890" /f >nul
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyOverride /t REG_SZ /d "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;192.168.*;<local>" /f >nul
    echo   ✅ 系统代理: 127.0.0.1:7890

    :: 2. Git 代理
    git config --global http.proxy http://127.0.0.1:7890
    git config --global https.proxy http://127.0.0.1:7890
    echo   ✅ Git 代理: 已开启

    :: 3. npm 代理
    npm config set proxy http://127.0.0.1:7890
    npm config set https-proxy http://127.0.0.1:7890
    echo   ✅ npm 代理: 已开启

) else (
    :: ========== 关闭代理模式 ==========
    echo.
    echo   🏫 正在切换到: 校园网直连...

    :: 1. 系统代理
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul
    echo   ✅ 系统代理: 已关闭

    :: 2. Git 代理
    git config --global --unset http.proxy 2>nul
    git config --global --unset https.proxy 2>nul
    echo   ✅ Git 代理: 已清除

    :: 3. npm 代理
    npm config delete proxy 2>nul
    npm config delete https-proxy 2>nul
    echo   ✅ npm 代理: 已清除
)

echo.
echo   ╔══════════════════════════════════════╗
echo   ║   ✅ 已切换到: %NEW_MODE%           ║
echo   ╚══════════════════════════════════════╝
echo.
echo   提示: 浏览器可能需要刷新页面才能生效
echo.
pause
