@echo off
echo Launching Chrome with debug mode...
echo Close ALL Chrome windows first, then run this.
echo.
echo Killing any remaining Chrome processes...
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo Starting Chrome...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug"
echo.
echo Chrome launched! Navigate to your SmartBook assignment, then run the solver.
echo You can verify debug mode at: http://127.0.0.1:9222/json
