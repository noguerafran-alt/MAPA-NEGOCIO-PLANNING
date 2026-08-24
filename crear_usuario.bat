@echo off
title Crear usuario - Mapa Gasoil ^& Naftas
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo Primero corre iniciar.bat una vez para instalar el entorno.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

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
flask --app app autorizar-usuario --email %EMAIL% --nombre "%NOMBRE%" --nivel %NIVEL%

echo.
echo Listo. Ya podes entrar en http://127.0.0.1:5000 con ese email y la contraseña que elegiste.
pause
