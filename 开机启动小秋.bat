@echo off
chcp 65001 >nul

:: ============================================
:: 小秋手动启动脚本（备份）
:: 使用 Windows Terminal 启动，不弹 CMD 黑窗 🦀
:: 路径: D:\AI小秋\开机启动小秋.bat
:: ============================================

:: 检查 Claude Code 是否可用
where claude >nul 2>&1
if %errorlevel% neq 0 (
    mshta vbscript:Execute("msgbox ""❌ 找不到 claude 命令，请检查安装"" ,0,""小秋启动失败""")
    exit /b 1
)

:: 用 Windows Terminal 启动小秋，CMD 窗口自动关闭
start "" wt.exe -d "C:\Users\ASUS" --title "🌅 小秋 - AI 助手" cmd /k "echo. && echo   ╔══════════════════════════════════════╗ && echo   ║   🌅 早上好！小秋来啦～              ║ && echo   ║   今天也是元气满满的一天！           ║ && echo   ╚══════════════════════════════════════╝ && echo. && echo   📁 工作目录: D:\AI小秋 && echo. && echo   🚀 正在启动小秋... && echo. && claude && echo. && echo   👋 小秋已退出，下次见！"

exit

