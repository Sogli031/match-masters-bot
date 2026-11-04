@echo off
rem Zajednicki Python bootstrap. Ne pokretati direktno; pozivaju ga glavni BAT fajlovi.

set "PYEXE="
set "MMBOT_WIN7="
ver | findstr /C:"6.1." >nul
if not errorlevel 1 set "MMBOT_WIN7=1"

if defined MMBOT_WIN7 goto find_win7
goto find_modern

:find_win7
if /I "%PROCESSOR_ARCHITECTURE%"=="x86" if not defined PROCESSOR_ARCHITEW6432 goto win7_32bit
set "WIN7_SP="
for /f "tokens=2 delims==" %%i in ('wmic os get ServicePackMajorVersion /value 2^>nul ^| find "="') do set "WIN7_SP=%%i"
if not "%WIN7_SP%"=="1" goto win7_no_sp1

for /f "delims=" %%i in ('py -3.8-64 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
if defined PYEXE if exist "%PYEXE%" goto found
set "PYEXE=%LocalAppData%\Programs\Python\Python38\python.exe"
if exist "%PYEXE%" goto found
set "PYEXE="

echo Detektovan je Windows 7 64-bit.
echo Za Windows 7 bot koristi Python 3.8.10.
echo.
choice /C DN /N /M "Zelis li da preuzmem i instaliram Python 3.8.10? [D/N]: "
if errorlevel 2 goto cancelled

set "PYINSTALLER=%TEMP%\python-3.8.10-amd64.exe"
echo.
echo Preuzimam Python 3.8.10 sa zvanicnog python.org sajta...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=3072; (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.8.10/python-3.8.10-amd64.exe','%PYINSTALLER%'); $s=Get-AuthenticodeSignature -FilePath '%PYINSTALLER%'; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Python Software Foundation'){throw 'Digitalni potpis Python installera nije prihvacen'}"
if errorlevel 1 goto python38_download_failed

echo Digitalni potpis je validan. Instaliram Python 3.8.10...
start /wait "" "%PYINSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
set "PYINSTALL_CODE=%ERRORLEVEL%"
del /q "%PYINSTALLER%" >nul 2>&1
if not "%PYINSTALL_CODE%"=="0" goto python38_install_failed

for /f "delims=" %%i in ('py -3.8-64 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
if defined PYEXE if exist "%PYEXE%" goto found
set "PYEXE=%LocalAppData%\Programs\Python\Python38\python.exe"
if exist "%PYEXE%" goto found
set "PYEXE="
goto python38_install_failed

:python38_download_failed
del /q "%PYINSTALLER%" >nul 2>&1
echo.
echo GRESKA: Python 3.8.10 nije bezbedno preuzet.
echo Windows 7 mora imati Service Pack 1, azurirane root sertifikate i TLS 1.2.
exit /b 1

:python38_install_failed
echo.
echo GRESKA: Python 3.8.10 instalacija nije uspela.
exit /b 1

:win7_32bit
echo GRESKA: detektovan je Windows 7 32-bit.
echo Bot koristi BlueStacks Pie64 i moze da radi samo na 64-bitnom Windows-u.
exit /b 1

:win7_no_sp1
echo GRESKA: Windows 7 nema Service Pack 1 ili ga nije moguce potvrditi.
echo Instaliraj Windows 7 Service Pack 1 pre Python-a, dependencies i BlueStacks-a.
exit /b 1

:find_modern
for /f "delims=" %%i in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
if defined PYEXE if exist "%PYEXE%" goto found
set "PYEXE=%LocalAppData%\Programs\Python\Python311\python.exe"
if exist "%PYEXE%" goto found
set "PYEXE="

echo Detektovan je Windows 10/11 ili noviji podrzani sistem.
echo Za ovaj sistem bot koristi Python 3.11.
echo.
choice /C DN /N /M "Zelis li da instaliram Python 3.11? [D/N]: "
if errorlevel 2 goto cancelled

where winget >nul 2>&1
if errorlevel 1 goto no_winget
echo.
echo Instaliram Python 3.11 preko winget-a...
winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements
for /f "delims=" %%i in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
if defined PYEXE if exist "%PYEXE%" goto found
set "PYEXE=%LocalAppData%\Programs\Python\Python311\python.exe"
if exist "%PYEXE%" goto found
set "PYEXE="
echo.
echo GRESKA: Python 3.11 instalacija nije uspela.
exit /b 1

:no_winget
echo.
echo GRESKA: winget nije dostupan.
echo Instaliraj Python 3.11 sa https://www.python.org/downloads/ i pokreni BAT ponovo.
exit /b 1

:cancelled
echo.
echo Otkazano. Nista nije instalirano.
exit /b 1

:found
echo Detektovan Python: %PYEXE%

rem Python postoji -- ostaje pitanje da li su biblioteke tu i u pravoj verziji.
rem Pozivalac moze da izabere fajl preko MMBOT_REQUIREMENTS, ili da preskoci
rem celu proveru preko MMBOT_SKIP_DEPS (npr. za brzo ponovno pokretanje).
if defined MMBOT_SKIP_DEPS goto deps_ok

set "DEPSCRIPT=%~dp0tools\check_requirements.py"
if not exist "%DEPSCRIPT%" goto deps_ok

set "REQFILE=%MMBOT_REQUIREMENTS%"
if not defined REQFILE if exist "%~dp0requirements.txt" set "REQFILE=%~dp0requirements.txt"
if not defined REQFILE if exist "%~dp0requirements-runtime.txt" set "REQFILE=%~dp0requirements-runtime.txt"
if not defined REQFILE goto deps_ok

"%PYEXE%" "%DEPSCRIPT%" "%REQFILE%"
if not errorlevel 1 goto deps_ok

echo.
echo Projekat radi na tacno ovim verzijama, pa gde treba ide i vracanje unazad.
choice /C DN /N /M "Zelis li da uskladim biblioteke sa projektom? [D/N]: "
if errorlevel 2 goto deps_cancelled

echo.
"%PYEXE%" "%DEPSCRIPT%" "%REQFILE%" --install --verify-imports
if errorlevel 1 goto deps_failed
goto deps_ok

:deps_failed
echo.
echo GRESKA: instalacija biblioteka nije uspela.
echo Probaj rucno: "%PYEXE%" -m pip install -r "%REQFILE%"
exit /b 1

:deps_cancelled
echo.
echo Otkazano. Bez ovih biblioteka program ne moze da se pokrene.
exit /b 1

:deps_ok
exit /b 0
