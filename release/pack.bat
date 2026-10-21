@echo off
setlocal EnableExtensions
rem Do not cd: CMD cannot use UNC paths like \\Mac\Home\... as the current directory.
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if not exist "%ROOT%\release\pack.py" (
  echo Cannot find release\pack.py
  echo ROOT=%ROOT%
  pause
  exit /b 1
)
echo ROOT=%ROOT%

if exist "%ROOT%\.venv\Scripts\python.exe" goto :venv
where python >nul 2>&1
if errorlevel 1 (
  echo Python not found. Install Python 3.10+ on this Windows PC.
  pause
  exit /b 1
)
echo Using: python
python "%ROOT%\release\pack.py"
goto :end

:venv
echo Using: .venv
"%ROOT%\.venv\Scripts\python.exe" "%ROOT%\release\pack.py"
goto :end

:end
pause
