@echo off
chcp 65001 >nul
title 🔥 3进4连板擒龙策略

cd /d "%~dp0"

echo.
echo ╔══════════════════════════════════════════╗
echo ║  🔥 3进4连板擒龙 —— 一键分析          ║
echo ╚══════════════════════════════════════════╝
echo.
echo 正在获取今日涨停数据...

:: 自动找Python
set PYTHON=
for %%p in (python python3 py) do (
    where %%p >nul 2>&1 && set PYTHON=%%p && goto :found
)

echo ❌ 没找到Python，请先安装Python3
echo    下载地址: https://www.python.org/downloads/
echo    安装时勾选 "Add Python to PATH"
pause
exit /b 1

:found
echo ✅ Python: %PYTHON%

:: 检查依赖
%PYTHON% -c "import akshare, pandas" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo 📦 首次使用，正在安装必要组件（约1-2分钟）...
    %PYTHON% -m pip install akshare pandas -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
    if %errorlevel% neq 0 (
        echo ❌ 安装失败，请检查网络
        pause
        exit /b 1
    )
    echo ✅ 安装完成！
)

echo.
echo 🚀 正在分析3进4候选...
echo.

%PYTHON% three_to_four.py

echo.
echo ═══════════════════════════════════════════
echo 📄 报告已生成：three_to_four_report.md
echo    用记事本或Typora打开即可查看
echo ═══════════════════════════════════════════
echo.
pause
