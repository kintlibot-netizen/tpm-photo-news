# Registers the Windows task "TPM Carousel Bot": the bot that makes every carousel by itself (src/carousel_bot.py).
# Run it once in PowerShell from the project folder:
#   powershell -ExecutionPolicy Bypass -File scripts\setup-carousel-bot-task.ps1
# Running it again replaces the task and keeps these settings:
#   every hour (at minute 25, after the cloud run at minute 7), and at logon
#   hidden (wscript runs the bot with no window), on battery too, catches up after a missed start,
#   never two at once, and a run is stopped after 55 minutes
# Remove it with: Unregister-ScheduledTask -TaskName "TPM Carousel Bot" -Confirm:$false
# Run it now by hand: Start-ScheduledTask -TaskName "TPM Carousel Bot"
# Nothing it does ever posts to Facebook or Instagram.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $root "scripts\carousel_bot_hidden.vbs"
if (-not (Test-Path $launcher)) { throw "Not found: scripts\carousel_bot_hidden.vbs. Run this from the project." }

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//B //Nologo `"$launcher`"" -WorkingDirectory $root

$now = Get-Date
$start = $now.Date.AddHours($now.Hour).AddMinutes(25)
if ($start -le $now) { $start = $start.AddHours(1) }
$hourly = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours 1)
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet `
    -Hidden `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 55)

# Runs as Kint, while she is signed in, so git can push with her saved GitHub sign-in and Claude Code is signed in.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "TPM Carousel Bot" -Action $action -Trigger @($hourly, $atLogon) `
    -Settings $settings -Principal $principal `
    -Description "Makes TPM carousels by itself every hour (fact check and official images on this laptop). Kint and David only approve. Never posts to social media." `
    -Force | Out-Null

Write-Output "Registered: TPM Carousel Bot (hourly at minute 25 and at logon, hidden). Log: logs\carousel-bot.log"
