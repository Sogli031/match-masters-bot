@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0python_for_windows.bat"
if errorlevel 1 goto end
if not defined PYEXE goto end
echo Udji u partiju i zatvori Memory GUI.
echo Pritisni Enter na pocetku i posle svakog poteza, kad tabla miruje.
"%PYEXE%" "%~dp0tools\capture_session.py" %*
:end
pause
