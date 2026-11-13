@echo off
rem Sync with cloud: Kint's laptop part when the cloud watcher is on.
rem 1. gets the latest news, alerts and "needs Kint" marks from the cloud (git pull, then state/ into data/ and output/)
rem 2. builds the carousels the cloud marked "needs Kint" (the fact check and the official image check need Claude)
rem 3. opens the review dashboard in its own window, so you can approve, reject or log posts
rem 4. when you press a key here, saves your carousels and reviews to state/ and pushes them (after a safety check)
rem The laptop never sends news alerts while the cloud is on, so no alert is ever sent twice. Nothing is posted.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PYTHON=.venv\Scripts\python.exe") else (set "PYTHON=python")

echo 1. Getting the latest from the cloud...
git pull --rebase || goto failed
"%PYTHON%" src\cloud_state.py pull --side laptop || goto failed

echo.
echo 2. Building the carousels the cloud marked "needs Kint". This can take a while...
"%PYTHON%" src\run.py --carousels-only

echo.
echo 3. Opening the review dashboard in its own window.
start "TPM review server" "%PYTHON%" src\review_server.py --open
echo Review the carousels there. When you are done, come back to this window.
pause

echo.
echo 4. Saving your carousels and reviews to the cloud...
"%PYTHON%" src\cloud_state.py push --side laptop || goto failed
"%PYTHON%" scripts\check_public_safe.py || goto failed
git add -A state || goto failed
git diff --cached --quiet && goto nothing
git commit -m "Laptop: carousels and reviews" || goto failed
git pull --rebase || goto failed
git push || goto failed
echo.
echo Saved. The web link for David updates at the next hourly cloud run (or run it now in the Actions tab).
pause
exit /b 0

:nothing
echo Nothing new to save.
pause
exit /b 0

:failed
echo.
echo Something did not work. Nothing was posted anywhere. Read the message above, or ask for help.
pause
exit /b 1
