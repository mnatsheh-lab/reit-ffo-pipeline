@echo off
REM Quick test: collect ONE quarter for MAA (a few cents of API usage).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m pip install -q -r requirements.txt
python -m src.collect --tickers MAA --start 2026Q2 --end 2026Q2
echo.
pause
