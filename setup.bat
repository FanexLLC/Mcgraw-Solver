@echo off
echo ====================================
echo  McGraw-Hill SmartBook Solver Setup
echo ====================================
echo.
echo Installing Python dependencies...
pip install -r requirements.txt
echo.
echo Setup complete!
echo.
echo NEXT STEPS:
echo 1. Open .env and paste your OpenAI API key
echo 2. Run: python main.py
echo.
pause
