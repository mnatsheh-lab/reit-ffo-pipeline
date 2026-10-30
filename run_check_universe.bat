@echo off
REM Free check: confirms every REITs SEC ID (CIK) before any paid run.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m src.universe
echo.
pause
