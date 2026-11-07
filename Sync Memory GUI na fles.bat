@echo off
chcp 65001 >nul
title Memory GUI - kopiranje na fles
cd /d "%~dp0"

set "PYEXE="
for /f "delims=" %%i in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
if defined PYEXE if exist "%PYEXE%" goto run

set "PYEXE="
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
if defined PYEXE if exist "%PYEXE%" goto run

set "PYEXE="
for /f "delims=" %%i in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
if defined PYEXE if exist "%PYEXE%" goto run

echo GRESKA: Python nije pronadjen.
echo Instaliraj Python 3.11 ili noviji i pokreni ovaj BAT ponovo.
set "RC=1"
goto end

:run
echo Python: %PYEXE%
echo.
"%PYEXE%" "%~dp0sync_to_flash.py" -y --force-delete %*
set "RC=%ERRORLEVEL%"

:end
echo.
echo ----------------------------------------------------------------
echo Gotovo.
exit /b %RC%

