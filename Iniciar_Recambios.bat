@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 --version >nul 2>nul
  if not errorlevel 1 goto PY_LAUNCH
)
where python >nul 2>nul
if not errorlevel 1 goto PYTHON_LAUNCH

echo.
echo No se ha encontrado Python en este equipo.
echo Instala Python 3.11 o superior desde https://www.python.org/downloads/
echo Despues vuelve a ejecutar Iniciar_Recambios.bat.
echo.
pause
exit /b 1

:PY_LAUNCH
py -3 "%~dp0inventario.py" --open-browser
if not errorlevel 1 exit /b 0
echo.
echo Ha ocurrido un error al iniciar Recambios. Consulta el mensaje anterior.
pause
exit /b 1

:PYTHON_LAUNCH
python "%~dp0inventario.py" --open-browser
if not errorlevel 1 exit /b 0
echo.
echo Ha ocurrido un error al iniciar Recambios. Consulta el mensaje anterior.
pause
exit /b 1
