@echo off
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
  py -3 setup_env.py
) else (
  python setup_env.py
)
if errorlevel 1 pause
