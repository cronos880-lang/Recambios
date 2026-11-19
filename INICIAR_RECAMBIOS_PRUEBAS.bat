@echo off
setlocal
cd /d "%~dp0"
echo.
echo ================================
echo   RECAMBIOS - MIS LISTAS
 echo   V0.2.8 PRUEBAS (PORTATIL)
echo ================================
echo.
where py >nul 2>nul
if not errorlevel 1 (
    py -3 --version >nul 2>nul
    if not errorlevel 1 goto CON_PY
)
where python >nul 2>nul
if not errorlevel 1 goto CON_PYTHON

echo No se ha encontrado Python 3.11 o superior.
echo Necesitas Python para esta prueba sin EXE.
pause
exit /b 1

:CON_PY
py -3 "%~dp0probar_recambios.py"
goto RESULTADO

:CON_PYTHON
python "%~dp0probar_recambios.py"

:RESULTADO
if errorlevel 1 (
  echo.
  echo Ha ocurrido un error al iniciar Recambios Pruebas.
  pause
  exit /b 1
)
endlocal
