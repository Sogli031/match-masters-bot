@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0python_for_windows.bat"
if errorlevel 1 goto end
if not defined PYEXE goto end
echo Udji u partiju (bilo koji mod) i zatvori Memory GUI.
"%PYEXE%" "%~dp0verify_refill_gui.py" %*
:end
pause
