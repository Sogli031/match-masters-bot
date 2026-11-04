@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0python_for_windows.bat"
if errorlevel 1 goto end
if not defined PYEXE goto end
echo Udji u partiju, zatvori Memory GUI i sacekaj da tabla miruje.
"%PYEXE%" "%~dp0tools\capture_match.py" %*
:end
pause
