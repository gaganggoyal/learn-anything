@echo off
rem One-click start for the Learn Anything site (Buddy) on Windows.
rem First run sets up the Python environment; every run makes sure
rem Ollama (Buddy's brain) is awake before starting the site.
setlocal
cd /d "%~dp0"

rem ---- find Python ----------------------------------------------------------
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (where py >nul 2>nul && set "PY=py -3")
if not defined PY (
  echo.
  echo   Python is not installed.
  echo   Get it from https://www.python.org/downloads/
  echo   IMPORTANT: tick "Add Python to PATH" during install, then run me again.
  echo.
  pause
  exit /b 1
)

rem ---- first run: set up the environment ------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo Setting up for the first time - this takes a minute...
  %PY% -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
)

rem ---- make sure Ollama is awake --------------------------------------------
curl -sf http://localhost:11434/api/version >nul 2>nul
if errorlevel 1 (
  where ollama >nul 2>nul
  if errorlevel 1 (
    echo.
    echo   Ollama is not installed. Get it from https://ollama.com then run:
    echo      ollama pull llama3.1:8b
    echo   Starting the site anyway - it will say "Buddy is asleep" until then.
    echo.
  ) else (
    echo Waking up Ollama...
    start "" /min ollama serve
    timeout /t 3 /nobreak >nul
  )
)

echo.
echo   Buddy is starting! Open http://localhost:8000 in your browser.
echo   Keep this window open while teaching. Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" server.py --host 0.0.0.0 %*
pause
