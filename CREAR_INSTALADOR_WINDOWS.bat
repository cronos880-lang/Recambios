@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Crear instalador Recambios V0.2.6 WebView2

echo.
echo ==================================================
echo         RECAMBIOS V0.2.6 - WEBVIEW2
echo       CREAR INSTALADOR EN TU WINDOWS
echo ==================================================
echo.
if not exist "recambios_windows.py" goto sin_archivos
if not exist "inventario.py" goto sin_archivos
if not exist "web\index.html" goto sin_archivos
if not exist "recambios.ico" goto sin_archivos
if not exist "descargar_webview2.py" goto sin_archivos

set "PYTHON=python"
where py >nul 2>nul
if not errorlevel 1 set "PYTHON=py -3"

if exist ".build_venv\Scripts\python.exe" goto entorno_listo
echo [1/5] Creando entorno de compilacion...
%PYTHON% -m venv ".build_venv"
if errorlevel 1 goto error_python

:entorno_listo
echo [2/5] Instalando PyInstaller y pywebview en el entorno aislado...
".build_venv\Scripts\python.exe" -m pip install --disable-pip-version-check "pyinstaller>=6.10,<7" "pywebview>=6.1,<7"
if errorlevel 1 goto error_build

echo [3/5] Compilando EXE con ventana WebView2, sin consola...
".build_venv\Scripts\python.exe" -m PyInstaller ^
 --noconfirm --clean --noupx --windowed --onedir ^
 --name Recambios --icon "recambios.ico" ^
 --add-data "web;web" --hidden-import clr --collect-all webview ^
 recambios_windows.py
if errorlevel 1 goto error_build
if not exist "dist\Recambios\Recambios.exe" goto error_build

echo [4/5] Descargando el instalador firmado de WebView2 desde Microsoft...
".build_venv\Scripts\python.exe" "descargar_webview2.py"
if errorlevel 1 goto error_webview2
if not exist "prerequisitos\MicrosoftEdgeWebView2Setup.exe" goto error_webview2

set "ISCC="
where ISCC.exe >nul 2>nul
if not errorlevel 1 set "ISCC=ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC goto sin_inno

echo [5/5] Creando instalador con comprobacion de WebView2...
"%ISCC%" "Recambios_Instalador.iss"
if errorlevel 1 goto error_build
if not exist "salida_instalador\Recambios_Instalador_V0_2_6_WebView2_Maximizado_Restauracion_Windows.exe" goto error_build

echo.
echo ================================================
echo  INSTALADOR CREADO CORRECTAMENTE
echo ================================================
echo.
echo  salida_instalador\Recambios_Instalador_V0_2_6_WebView2_Maximizado_Restauracion_Windows.exe
echo.
echo  No requiere Python para usar el programa instalado.
echo  No requiere tener Edge ni Chrome instalados.
echo  El instalador comprueba WebView2 y lo instala si falta.
echo.
echo  AVISO: el instalador NO esta firmado digitalmente.
echo  SmartScreen podria mostrar una advertencia.
echo.
pause
exit /b 0

:sin_inno
echo.
echo ERROR: No se ha encontrado Inno Setup 6.
echo Instala Inno Setup 6 desde https://jrsoftware.org/isinfo.php
echo El EXE esta compilado en dist\Recambios\Recambios.exe
pause
exit /b 2

:error_webview2
echo.
echo ERROR: falta el bootstrapper oficial de WebView2 firmado.
echo Descargalo desde la pagina oficial Microsoft WebView2.
echo Guarda el EXE como prerequisitos\MicrosoftEdgeWebView2Setup.exe
echo Vuelve a ejecutar este BAT.
pause
exit /b 3

:sin_archivos
echo ERROR: descomprime TODO el ZIP antes de ejecutar el BAT.
pause
exit /b 1

:error_python
echo ERROR: se necesita Python 3.11 o superior, 64 bits, para compilar.
echo Consulta https://www.python.org/downloads/windows/
pause
exit /b 1

:error_build
echo.
echo ERROR durante la compilacion. Consulta los mensajes anteriores.
echo Los datos de tus inventarios NO se han modificado.
pause
exit /b 1
