Unregister-ScheduledTask -TaskName "XiaoQiuMarketOpen" -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "D:\AI小秋\开盘启动.bat" -WorkingDirectory "D:\AI小秋"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At "09:25"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName "XiaoQiuMarketOpen" -Description "交易日9:25自动启动双策略侦察+持仓监控" -Action $action -Trigger $trigger -Settings $settings -Force

Write-Host "Done - task XiaoQiuMarketOpen created"
Get-ScheduledTask -TaskName "XiaoQiuMarketOpen" | Format-List TaskName, State, Description
