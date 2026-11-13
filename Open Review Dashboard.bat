@echo off
rem Starts the review server and opens the dashboard at http://127.0.0.1:8765/ in your browser.
rem Keep this window open while you review. Close it to stop the server.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PYTHON=.venv\Scripts\python.exe") else (set "PYTHON=python")
"%PYTHON%" src\review_server.py --open
if errorlevel 1 (
  echo.
  echo The review server could not start. See the message above.
  pause
  exit /b 1
)
