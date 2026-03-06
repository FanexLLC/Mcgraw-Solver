@echo off
echo ====================================
echo  McGraw-Hill SmartBook Solver Setup
echo ====================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Download Python from https://python.org
    echo IMPORTANT: Check "Add Python to PATH" during install!
    echo.
    pause
    exit /b 1
)

echo Installing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to install dependencies.
    echo Try running: pip3 install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo Setup complete!
echo.
echo NEXT STEPS:
echo 1. Run launch_chrome.bat to open Chrome in debug mode
echo 2. Navigate to your SmartBook assignment
echo 3. Run: python main.py
echo.
pause
