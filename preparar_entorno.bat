@echo off
REM ===========================================================================
REM  Prepara lo que la app necesita, SIN INTERNET y SIN que la PC tenga Python
REM  instalado. Todo sale de la carpeta vendor\ de este paquete:
REM
REM    vendor\python-3.12.10-embed-amd64.zip   el interprete (paquete "embeddable"
REM                                            oficial de python.org: no se instala,
REM                                            se desempaqueta y corre)
REM    vendor\wheels\*.whl                     Flask, SQLAlchemy, openpyxl, waitress
REM    vendor\preparar.py                      los pasos de adentro
REM
REM  Es idempotente: si el entorno ya esta, no hace nada. Se puede correr solo,
REM  a mano, para repararlo.
REM ===========================================================================
setlocal
cd /d "%~dp0"

REM El entorno vive FUERA de esta carpeta: si la carpeta esta en OneDrive, tener
REM el interprete adentro haria que se sincronicen ~60 MB a la nube.
set "RUNTIME=%USERPROFILE%\venvs\mapa-negocio-planning-runtime"
set "PY=%RUNTIME%\python.exe"
set "EMBED=%~dp0vendor\python-3.12.10-embed-amd64.zip"
set "PREPARAR=%~dp0vendor\preparar.py"

if not exist "%EMBED%" goto :falta_vendor
if not exist "%PREPARAR%" goto :falta_vendor
if not exist "%~dp0vendor\requirements-lock.txt" goto :falta_vendor

if not exist "%PY%" goto :desempacar

REM Ya hay entorno: si importa lo minimo, no hay nada que hacer.
"%PY%" -c "import flask, waitress, openpyxl, flask_sqlalchemy" >nul 2>nul
if errorlevel 1 goto :reparar
echo Entorno listo: %RUNTIME%
exit /b 0

:reparar
echo El entorno existe pero esta incompleto. Reinstalando.
goto :preparar

:desempacar
echo.
echo Primera vez en esta PC.
echo Desempaquetando el Python que viene adentro de esta carpeta. No instala nada
echo en el sistema ni toca el registro: queda todo en
echo   %RUNTIME%
echo.
if not exist "%RUNTIME%" mkdir "%RUNTIME%"
REM tar.exe de Windows (bsdtar) lee zip y es bastante mas rapido que Expand-Archive.
"%SystemRoot%\System32\tar.exe" -xf "%EMBED%" -C "%RUNTIME%" 2>nul
if exist "%PY%" goto :preparar
echo    (tar no estaba disponible, usando PowerShell)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%EMBED%' -DestinationPath '%RUNTIME%' -Force"
if not exist "%PY%" goto :error_desempacar

:preparar
"%PY%" "%PREPARAR%"
if errorlevel 1 goto :error_preparar
exit /b 0

:falta_vendor
echo.
echo FALTA LA CARPETA vendor\
echo.
echo Este paquete trae adentro el interprete de Python y todos los componentes,
echo para arrancar sin internet. Si vendor\ no esta, el zip se descomprimio a
echo medias o se copio incompleto.
echo.
echo Tiene que existir:
echo   vendor\python-3.12.10-embed-amd64.zip
echo   vendor\wheels\   (26 archivos .whl, unos 7 MB)
echo   vendor\requirements-lock.txt
echo   vendor\preparar.py
echo.
pause
exit /b 1

:error_desempacar
echo.
echo NO SE PUDO DESEMPAQUETAR EL INTERPRETE
echo.
echo Lo mas comun es que el zip se haya copiado incompleto. Borra la carpeta
echo   %RUNTIME%
echo y volve a descomprimir el zip original.
echo.
pause
exit /b 1

:error_preparar
echo.
echo NO SE PUDO PREPARAR EL ENTORNO
echo.
echo Revisa el mensaje de arriba. Si quedo a medias, borra
echo   %RUNTIME%
echo y volve a correr este archivo.
echo.
pause
exit /b 1
