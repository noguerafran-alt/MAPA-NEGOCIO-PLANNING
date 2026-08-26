@echo off
title Mapa Gasoil ^& Naftas
cd /d "%~dp0"

REM ===========================================================================
REM  Un click y anda. No hace falta Python instalado, ni VS Code, ni internet:
REM  el interprete y los componentes vienen adentro de vendor\.
REM  preparar_entorno.bat los desempaqueta la primera vez y despues no hace nada.
REM ===========================================================================

set "RUNTIME=%USERPROFILE%\venvs\mapa-negocio-planning-runtime"
set "PY=%RUNTIME%\python.exe"

if not exist "%PY%" goto :preparar
REM Entorno ya armado: no perdemos segundos revalidando en cada arranque.
goto :arrancar

:preparar
call "%~dp0preparar_entorno.bat"
if errorlevel 1 exit /b 1
if not exist "%PY%" exit /b 1

:arrancar
REM El navegador se abre 3 segundos despues, ya con el server escuchando.
start "" cmd /c "timeout /t 3 >nul && start http://127.0.0.1:5000"

"%PY%" run_local.py

REM Salida limpia: la ventana se cierra sola. Si murio por un error, se queda
REM abierta para poder leerlo.
if errorlevel 1 goto :murio
exit /b 0

:murio
echo.
echo La app se detuvo por un error. Revisa el mensaje de arriba.
pause
exit /b 1
