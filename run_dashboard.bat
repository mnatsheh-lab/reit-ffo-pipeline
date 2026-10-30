@echo off
REM Rebuild the dashboard from the latest extraction results and open it.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m src.build_dashboard
start "" "dashboard\index.html"
