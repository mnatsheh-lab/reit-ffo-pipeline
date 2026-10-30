@echo off
REM Re-run checks on saved documents, then compare them with the hand-collected answer key.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m src.recheck
echo.
python -m src.verify_collection
echo.
pause
