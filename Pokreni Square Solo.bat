@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0python_for_windows.bat"
if errorlevel 1 goto end
if not defined PYEXE goto end
echo Udji u Square Match Solo i zatvori Memory GUI.
"%PYEXE%" "%~dp0square_solo_gui.py" %*
:end
pause
