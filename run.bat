@echo off
setlocal

REM ====================================================================
REM  Emision Plan Familia VAVI - lanzador
REM
REM  Si este .bat esta en una carpeta de red (\\servidor\... o unidad
REM  mapeada), copia el programa a un disco local, lo ejecuta desde ahi
REM  y devuelve logs y output a la carpeta de red.
REM  Motivo: el .exe ejecutado desde la red no resuelve DNS (error 11003).
REM
REM  Si esta en un disco local, ejecuta el .exe en el lugar.
REM
REM  EMISION_LOCAL_DIR (opcional): carpeta local donde copiar el programa.
REM  Por defecto: %LOCALAPPDATA%. El programa queda en
REM  <carpeta>\EmisionPlanFamiliaVAVI\<nombre de la carpeta de este .bat>
REM ====================================================================

set "BASE=%~dp0"
set "SRC=%~dp0dist\EmisionPlanFamiliaVAVI"
set "EXE_NAME=EmisionPlanFamiliaVAVI.exe"

if exist "%SRC%\%EXE_NAME%" goto :detectar
echo No se encontro el .exe en "%SRC%".
echo Generarlo con: .venv\Scripts\python.exe -m PyInstaller --clean -y main.spec
exit /b 1

:detectar
set "EN_RED=0"
if "%BASE:~0,2%"=="\\" set "EN_RED=1"
if "%EN_RED%"=="1" goto :preparar_local
net use %~d0 >nul 2>&1
if not errorlevel 1 set "EN_RED=1"
if "%EN_RED%"=="1" goto :preparar_local

REM --- Disco local: se ejecuta en el lugar ---
set "RUN_DIR=%SRC%"
cd /d "%~dp0"
goto :armar_args

:preparar_local
set "LOCAL_ROOT=%EMISION_LOCAL_DIR%"
if not defined LOCAL_ROOT set "LOCAL_ROOT=%LOCALAPPDATA%"
if not defined LOCAL_ROOT set "LOCAL_ROOT=%TEMP%"
if defined LOCAL_ROOT goto :nombre_local
echo ERROR: no hay carpeta local donde copiar el programa. Definir EMISION_LOCAL_DIR.
exit /b 1

:nombre_local
REM Una subcarpeta por origen (TST, PRO...) para que no se mezclen.
set "NOMBRE=raiz"
if not "%BASE:~3%"=="" for %%I in ("%BASE:~0,-1%") do set "NOMBRE=%%~nxI"
if not defined NOMBRE set "NOMBRE=raiz"
set "RUN_DIR=%LOCAL_ROOT%\EmisionPlanFamiliaVAVI\%NOMBRE%"

REM No pisar una carpeta que no sea una copia de este programa.
if not exist "%RUN_DIR%\" goto :copiar
if exist "%RUN_DIR%\%EXE_NAME%" goto :copiar
dir /b "%RUN_DIR%" 2>nul | findstr . >nul
if errorlevel 1 goto :copiar
echo ERROR: "%RUN_DIR%" ya existe y no es una copia de este programa. No se toca.
echo Definir EMISION_LOCAL_DIR con otra carpeta local.
exit /b 1

:copiar
echo Carpeta de red detectada: "%BASE%"
echo Copiando el programa a disco local: "%RUN_DIR%"
robocopy "%SRC%" "%RUN_DIR%" /MIR /R:2 /W:5 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :error_copia
if exist "%RUN_DIR%\%EXE_NAME%" goto :copia_ok

:error_copia
echo ERROR: no se pudo copiar el programa a "%RUN_DIR%". No se ejecuta.
exit /b 1

:copia_ok
echo Ejecutando desde disco local.
cd /d "%RUN_DIR%"

:armar_args
set "EXE=%RUN_DIR%\%EXE_NAME%"

REM --env: EMISION_ENV o pro, salvo que el caller ya pase --env
set "ENV=pro"
if defined EMISION_ENV set "ENV=%EMISION_ENV%"
set "PASS_ENV=1"
echo(%*| findstr /i /c:"--env" >nul
if not errorlevel 1 set "PASS_ENV=0"

REM --repo apaga Graph. No se agrega si GRAPH_ENABLED=true o si ya viene --repo.
REM EMISION_REPO o el set de prueba junto a este bat: smoke local.
set "REPO="
if /i "%GRAPH_ENABLED%"=="true" goto :run
if defined EMISION_REPO (
  set "REPO=%EMISION_REPO%"
) else if exist "%~dp0SOLICITUDES SALUD VAVI-RETIRO\" (
  set "REPO=%~dp0SOLICITUDES SALUD VAVI-RETIRO"
)
echo(%*| findstr /i /c:"--repo" >nul
if not errorlevel 1 set "REPO="

:run
if "%PASS_ENV%"=="1" (
  if defined REPO (
    "%EXE%" --env %ENV% --repo "%REPO%" %*
  ) else (
    "%EXE%" --env %ENV% %*
  )
) else (
  if defined REPO (
    "%EXE%" --repo "%REPO%" %*
  ) else (
    "%EXE%" %*
  )
)
set "RC=%ERRORLEVEL%"

if "%EN_RED%"=="0" exit /b %RC%

REM --- Devolver logs y output a la carpeta de red ---
set "AVISO=0"
if not exist "%RUN_DIR%\logs\" goto :devolver_output
robocopy "%RUN_DIR%\logs" "%SRC%\logs" /E /R:2 /W:5 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 set "AVISO=1"

:devolver_output
if not exist "%RUN_DIR%\output\" goto :fin
robocopy "%RUN_DIR%\output" "%SRC%\output" /E /R:2 /W:5 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 set "AVISO=1"

:fin
if "%AVISO%"=="1" echo AVISO: no se pudieron devolver logs/output a "%SRC%". Quedan en "%RUN_DIR%".
exit /b %RC%
