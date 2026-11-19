"""Lanzador de prueba portable V0.2.8: no instala ni compila nada.

Requiere Python >=3.11. Si ya existe pywebview y Microsoft WebView2
Runtime, lanza en ventana nativa. Si no, usa navegador predeterminado,
sin dependencias Python externas adicionales.
La versión estable no se toca: todos los datos están bajo
%LOCALAPPDATA%/Recambios_Pruebas/Datos (en Windows).
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys


def main() -> None:
    if sys.version_info < (3, 11):
        raise SystemExit('Se necesita Python 3.11 o superior.')

    if sys.platform == 'win32':
        app_dir = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'Recambios_Pruebas'
    else:
        app_dir = Path.home() / '.recambios_pruebas'
    os.environ['INVENTARIO_PRO10_DATA_DIR'] = str(app_dir / 'Datos')

    # Nunca instalar paquetes ni modificar Windows durante una prueba.
    if sys.platform == 'win32' and importlib.util.find_spec('webview') is not None:
        try:
            import recambios_windows
            if recambios_windows.webview2_installed():
                print('Iniciando Recambios Pruebas en ventana WebView2...', flush=True)
                recambios_windows.main()
                return
        except (ImportError, OSError) as exc:
            print(f'No se puede utilizar WebView2 con este Python: {exc}', flush=True)

    print('Iniciando Recambios Pruebas en el navegador predeterminado.', flush=True)
    print(f'Datos de PRUEBA: {app_dir / "Datos"}', flush=True)
    import inventario
    sys.argv = ['inventario.py', '--open-browser']
    inventario.main()


if __name__ == '__main__':
    main()
