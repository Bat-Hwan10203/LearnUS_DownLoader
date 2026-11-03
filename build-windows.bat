@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m pip install pyinstaller==6.16.0
if errorlevel 1 goto :fail
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name LearnUSDownloader --collect-all Crypto --copy-metadata requests --paths . launcher.py
if errorlevel 1 goto :fail
copy THIRD_PARTY_LICENSE.txt dist\LearnUSDownloader\THIRD_PARTY_LICENSE.txt
copy README.md dist\LearnUSDownloader\README.md
echo Output: dist\LearnUSDownloader\LearnUSDownloader.exe
pause
exit /b 0
:fail
pause
exit /b 1
