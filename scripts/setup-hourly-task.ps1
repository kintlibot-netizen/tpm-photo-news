# Creates the Windows task that runs the laptop backup every hour: run.py --nudge-cloud starts the cloud watcher
# only when GitHub has skipped its hourly runs (it checks no news and sends no Slack message). Needs gh signed in.
# Run this only after a real Slack test alert has worked.
# Running it again replaces the task (-Force) and keeps these settings:
#   run on battery, keep running on battery, run as soon as possible after a missed start,
#   wake the PC to run, and stop a run that takes longer than 45 minutes.
# Remove it later with: Unregister-ScheduledTask -TaskName "TPM Photo News Watcher"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$script = Join-Path $root "src\run.py"

$action = New-ScheduledTaskAction -Execute $python -Argument "`"$script`" --nudge-cloud" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 45)

Register-ScheduledTask -TaskName "TPM Photo News Watcher" -Action $action -Trigger $trigger -Settings $settings -Description "Checks photo news hourly and alerts Slack. Never posts to social media." -Force
