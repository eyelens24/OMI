@echo off
setlocal
cd /d "%~dp0"
if exist "C:\conda2\python.exe" (
  "C:\conda2\python.exe" run-omi.py
) else (
  py -3 run-omi.py 2>nul || python run-omi.py
)
endlocal
