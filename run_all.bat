@echo off
REM Everything: every REIT, every missing quarter since 2020. Asks before each paid step.
REM Safe to stop and restart: finished quarters are skipped.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m pip install -q -r requirements.txt
python -m src.collect
python -m src.recheck
python -m src.run_extract
python -m src.build_dashboard
start "" "dashboard\index.html"
pause
