@echo off
echo Launching Chrome with debug mode (rperez1121@sdsu.edu)...
echo Close ALL Chrome windows first, then run this.
echo.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data" --profile-directory="Profile 1"
