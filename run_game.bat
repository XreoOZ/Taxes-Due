@echo off
cd /d "%~dp0"
title Taxes-Due - Village Building Prototype
echo ===================================================
echo Starting Taxes-Due (Village Building Prototype)
echo ===================================================

python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Mencoba menjalankan dengan py launcher...
    py -3 main.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ===================================================
    echo Game keluar atau terjadi error (Code: %ERRORLEVEL%)
    echo ===================================================
    pause
)
