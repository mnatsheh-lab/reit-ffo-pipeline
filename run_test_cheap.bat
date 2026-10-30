@echo off
REM Test the cheaper pipeline on the 15 answer-key quarters before the big run.
REM Step 1 is free. Step 2 re-extracts 15 documents with the fast model (a few cents) and checks MAA vs the answer key.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m pip install -q -r requirements.txt
echo === Step 1: do the free rules pick the same 15 documents as the agent did? ===
python -m src.collect --tickers MAA CPT IRT NXRT BRT --check-rules
echo.
echo === Step 2: re-extract the 15 with the fast model ===
python -m src.run_extract --tickers MAA CPT IRT NXRT BRT --redo
python -m src.build_dashboard
echo.
pause
