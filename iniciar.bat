@echo off
title Mapa Gasoil ^& Naftas
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo Primera vez en esta PC: preparando el entorno, un momento...
    where python >nul 2>nul
    if errorlevel 1 (
        echo.
        echo No se encontro Python instalado.
        echo Instala desde https://www.python.org/downloads/
        echo ^(version 3.11 o 3.12, tildando "Add python.exe to PATH"^) y volve a intentar.
        echo.
        pause
        exit /b 1
    )
    python -m venv venv
    if errorlevel 1 (
        echo No se pudo crear el entorno virtual. Revisa el mensaje de arriba.
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
    echo Instalando componentes necesarios...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Fallo la instalacion de dependencias. Revisa el mensaje de arriba.
        pause
        exit /b 1
    )
    echo.
    echo Listo, entorno preparado.
    echo.
) else (
    call venv\Scripts\activate.bat
)

REM Si no hay usuarios, avisar que hay que crear el primero
if not exist "local_dev.db" (
    echo.
    echo ============================================================
    echo  PRIMERA VEZ: necesitas crear un usuario admin.
    echo  En otra ventana de comandos, desde esta carpeta, corre:
    echo.
    echo    crear_usuario.bat
    echo.
    echo  O manualmente:
    echo    venv\Scripts\activate
    echo    flask --app app autorizar-usuario --email vos@empresa.com --nombre "Tu Nombre" --nivel 3
    echo ============================================================
    echo.
)

start "" cmd /c "timeout /t 3 >nul && start http://127.0.0.1:5000"

python run_local.py

echo.
echo La app se detuvo. Si no era intencional, revisa el mensaje de arriba.
pause
