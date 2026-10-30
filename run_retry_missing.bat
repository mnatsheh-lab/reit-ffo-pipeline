@echo off
REM Retry only the quarters marked missing (free rules first, agent only if needed), then extract them.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m src.collect --retry-missing
python -m src.run_extract
python -m src.build_dashboard
start "" "dashboard\index.html"
pause
