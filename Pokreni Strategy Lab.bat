@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0python_for_windows.bat"
if errorlevel 1 exit /b 1
if not defined PYEXE exit /b 1
"%PYEXE%" -m strategy_lab gui
