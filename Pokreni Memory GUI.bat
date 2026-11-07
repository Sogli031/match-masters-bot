@echo off
chcp 65001 >nul
title Match Masters Toolkit
cd /d "%~dp0"

call "%~dp0python_for_windows.bat"
if errorlevel 1 goto end
if not defined PYEXE goto end

:run
echo Python: %PYEXE%
echo.
"%PYEXE%" "%~dp0memory_gui.py" %*
goto end

:end
echo.
echo ----------------------------------------------------------------
echo Done. Press any key to close...
pause >nul
