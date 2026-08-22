@echo off
setlocal
cd /d "%~dp0"
if exist "C:\conda2\python.exe" (
  "C:\conda2\python.exe" run-doctorquant.py
) else (
  py -3 run-doctorquant.py 2>nul || python run-doctorquant.py
)
endlocal
