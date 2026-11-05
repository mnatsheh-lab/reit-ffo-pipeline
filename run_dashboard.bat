@echo off
REM Refresh GAAP figures from SEC (free), rebuild the dashboard from the latest extraction results and open it.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
REM GAAP figures (EPS, revenue, dividends, debt) from SEC XBRL data: free, a few seconds
python -m src.gaap
python -m src.build_dashboard
start "" "dashboard\index.html"
