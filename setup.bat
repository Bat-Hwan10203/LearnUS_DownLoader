@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto :fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :fail
echo Setup complete. Run run.bat.
pause
exit /b 0
:fail
echo Setup failed. Install Python 3.10 or newer with Tcl/Tk support.
pause
exit /b 1
