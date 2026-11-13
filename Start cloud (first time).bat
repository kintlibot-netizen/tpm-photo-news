@echo off
rem Run this ONCE, to start the cloud watcher from the laptop's memory.
rem It copies the laptop's memory into state/ (stories already sent, carousels, approvals, the activity log), switches
rem the cloud on (state/CLOUD-ON, after which the laptop never sends news alerts) and checks that nothing secret or
rem personal would be made public. Then it shows the git commands to run.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PYTHON=.venv\Scripts\python.exe") else (set "PYTHON=python")

"%PYTHON%" src\cloud_state.py push --side laptop --first-time || goto failed
echo The cloud watcher is on. While this file exists, the laptop sends no news alerts; the cloud sends them all.> "state\CLOUD-ON"
"%PYTHON%" scripts\check_public_safe.py || goto failed

echo.
echo Ready. Now run:
echo   git add -A
echo   git commit -m "Start the cloud watcher"
echo   git push
echo Then add the SLACK_WEBHOOK_URL secret and turn on GitHub Pages (see README, Cloud 24/7).
pause
exit /b 0

:failed
echo.
echo Not done. Read the message above. Nothing was committed or posted.
pause
exit /b 1
