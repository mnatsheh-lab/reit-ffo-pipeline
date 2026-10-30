@echo off
REM One-time setup: installs the Python libraries and creates your .env file.
cd /d "%~dp0"
echo.
echo === Installing Python libraries ===
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Library install FAILED. Take a screenshot of this window and send it to Claude.
  pause
  exit /b 1
)
echo.
if exist .env (
  echo .env already exists - leaving it unchanged.
) else (
  echo === Creating .env ===
  > .env echo # Your private settings. Ignored by Git and never uploaded.
  >> .env echo # Paste your Claude API key after the = sign, with no quotes or spaces.
  >> .env echo ANTHROPIC_API_KEY=
  >> .env echo SEC_USER_AGENT="Mohammad Natsheh natshehm@outlook.com"
)
echo.
echo === Setup complete. Notepad will open: paste your API key after ANTHROPIC_API_KEY= and save. ===
start notepad .env
pause
