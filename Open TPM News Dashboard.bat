@echo off
rem Rebuilds the TPM Photo News dashboard from the watcher's data and opens it in the default browser.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PYTHON=.venv\Scripts\python.exe") else (set "PYTHON=python")
"%PYTHON%" src\dashboard.py
if errorlevel 1 (
  echo.
  echo The dashboard could not be built. See the message above.
  pause
  exit /b 1
)
start "" "%~dp0dashboard\index.html"
