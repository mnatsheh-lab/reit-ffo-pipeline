@echo off
REM Full run: all five answer-key REITs, Q4 2025 to Q2 2026 (15 documents).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m pip install -q -r requirements.txt
python -m src.collect --tickers MAA CPT IRT NXRT BRT --start 2025Q4 --end 2026Q2
echo.
pause
