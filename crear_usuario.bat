@echo off
title Crear usuario - Mapa Gasoil ^& Naftas
cd /d "%~dp0"

REM Solo hace falta para agregar mas usuarios o cambiar una contrasena: el
REM primero lo crea solo iniciar.bat en el primer arranque.

set "RUNTIME=%USERPROFILE%\venvs\mapa-negocio-planning-runtime"
set "PY=%RUNTIME%\python.exe"

if not exist "%PY%" (
    echo Primero corre iniciar.bat una vez, que prepara el entorno.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Crear / actualizar usuario autorizado
echo ============================================================
echo.
set /p EMAIL=Email:
set /p NOMBRE=Nombre (opcional):
set /p NIVEL=Nivel [1=mapa, 2=admin, 3=usuarios] (default 3):

if "%NIVEL%"=="" set NIVEL=3
if "%NOMBRE%"=="" set NOMBRE=%EMAIL%

echo.
set "FLASK_APP=app"
set "DATABASE_URL=sqlite:///local_dev.db"
"%PY%" -m flask autorizar-usuario --email %EMAIL% --nombre "%NOMBRE%" --nivel %NIVEL%

echo.
echo Listo. Entra en http://127.0.0.1:5000 con ese email.
pause
