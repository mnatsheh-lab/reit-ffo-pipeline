@echo off
REM Extract every saved reconciliation, apply the Conservative Core FFO definition,
REM and check MAA against the hand-built answer key.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m pip install -q -r requirements.txt
python -m src.recheck
python -m src.run_extract
echo.
pause
