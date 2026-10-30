@echo off
REM Pilot: MAA from 2018 to today (about 34 quarters). Asks before spending.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m pip install -q -r requirements.txt
python -m src.collect --tickers MAA
python -m src.run_extract --tickers MAA
python -m src.build_dashboard
start "" "dashboard\index.html"
pause
