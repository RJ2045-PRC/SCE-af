@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run.py
  goto :end
)
echo Packed .venv is missing or not for Windows. Running setup_env.py ...
where py >nul 2>&1
if not errorlevel 1 (
  py -3 setup_env.py
) else (
  python setup_env.py
)
if errorlevel 1 (
  echo Failed to create .venv. Install Python 3.10+.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
:end
pause
