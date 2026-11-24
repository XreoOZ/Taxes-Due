@echo off
cd /d "%~dp0"
title Taxes-Due - Automated Playtester (Island 10m)
echo ===================================================
echo Starting Taxes-Due Automated Playtester
echo Map: Island - Duration: 10 Minutes
echo Note: Mouse and keyboard are NOT hijacked.
echo You can use your laptop freely.
echo ===================================================

python main.py --playtest %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Mencoba menjalankan dengan py launcher...
    py -3 main.py --playtest %*
)

pause
