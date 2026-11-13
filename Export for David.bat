@echo off
rem Builds the read only copy of the dashboard for David in output\share, as a folder and a zip.
rem Send the zip to David. He unzips it and double-clicks index.html. Nothing is posted anywhere.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PYTHON=.venv\Scripts\python.exe") else (set "PYTHON=python")
"%PYTHON%" scripts\export_share_pack.py
if errorlevel 1 (
  echo.
  echo The copy for David was not made. See the message above.
  pause
  exit /b 1
)
echo.
echo Opening the share folder. Send the .zip file to David.
start "" "%~dp0output\share"
pause
