"""Recambios Windows V0.2.6 (WebView2) - lanzador nativo y servidor local.

Se instala mediante PyInstaller --onedir y utiliza pywebview con el motor
WebView2. No depende de abrir ni tener instalado Microsoft Edge o Chrome.
"""
from __future__ import annotations

import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import threading
import traceback
import winreg

APP_DIR = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local')) / 'Recambios'
DATA_DIR = APP_DIR / 'Datos'
INSTANCE_FILE = APP_DIR / 'instancia.json'
LOG_FILE = APP_DIR / 'errores.log'
STARTUP_LOG = APP_DIR / 'arranque.log'
MUTEX_NAME = r'Local\Recambios_App_84667AE3_E113_4EC1_88FD_174D10CF1820'
WV2_KEY = r'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'


def message(text: str, title: str = 'Recambios') -> None:
    ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)


def setup_logging() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    # La aplicacion no abre consola. Los errores se registran en AppData.
    log = open(LOG_FILE, 'a', encoding='utf-8', buffering=1)
    sys.stderr = log
    if sys.stdout is None:
        sys.stdout = log


def log_startup(stage: str) -> None:
    """Registro acotado para identificar en qué fase se bloquea WebView2."""
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with open(STARTUP_LOG, 'a', encoding='utf-8') as log:
            log.write(f'{datetime.now().isoformat(timespec="seconds")}  {stage}\n')
    except OSError:
        pass


def webview2_installed() -> bool:
    """Detecta WebView2 per-user o per-machine según la guía de Microsoft."""
    for hive, flags in (
        (winreg.HKEY_CURRENT_USER, winreg.KEY_READ),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_READ | winreg.KEY_WOW64_32KEY),
    ):
        try:
            with winreg.OpenKey(hive, WV2_KEY, 0, flags) as key:
                value, _ = winreg.QueryValueEx(key, 'pv')
            if isinstance(value, str) and re.match(r'^\d+(?:\.\d+)+$', value):
                if any(int(x) for x in value.split('.')):
                    return True
        except OSError:
            pass
    return False


def focus_existing_window() -> bool:
    """Si ya se ha iniciado el programa, intenta mostrar la ventana existente."""
    try:
        user32 = ctypes.windll.user32
        user32.FindWindowW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
        user32.FindWindowW.restype = ctypes.c_void_p
        handle = user32.FindWindowW(None, 'Recambios')
        if handle:
            user32.ShowWindow(handle, 9)  # SW_RESTORE
            user32.SetForegroundWindow(handle)
            return True
    except Exception:
        traceback.print_exc()
    return False


def save_instance(port: int) -> None:
    tmp = APP_DIR / 'instancia.tmp'
    tmp.write_text(json.dumps({'puerto': port, 'pid': os.getpid()}), encoding='utf-8')
    tmp.replace(INSTANCE_FILE)


def delete_instance() -> None:
    try:
        info = json.loads(INSTANCE_FILE.read_text(encoding='utf-8'))
        if info.get('pid') == os.getpid():
            INSTANCE_FILE.unlink(missing_ok=True)
    except (OSError, ValueError, KeyError):
        pass


class DesktopBridge:
    """Dos acciones nativas acotadas: guardar copia y cerrar la ventana.

    ADVERTENCIA: el puente pywebview inspecciona recursivamente los atributos
    públicos. NUNCA guardar un objeto Window/WinForms en `self.window` porque
    provoca recursión y bloqueo de WebView2. Debe ser `self._window`.
    """
    __slots__ = ('_window',)

    def __init__(self):
        self._window = None

    def guardar_copia(self):
        import webview
        import inventario
        stamp = datetime.now().strftime('%Y%m%d_%H%M')
        result = self._window.create_file_dialog(
            dialog_type=webview.FileDialog.SAVE,
            save_filename=f'Recambios_{stamp}.zip',
            file_types=('Copia ZIP (*.zip)',),
        )
        if not result:
            return {'cancelado': True}
        destino = Path(result[0])
        if destino.suffix.lower() != '.zip':
            destino = destino.with_suffix('.zip')
        # Prepara la copia completa en memoria antes de escribir el destino.
        content = inventario.archive_backup()
        temp = destino.with_name(destino.name + '.tmp')
        try:
            temp.write_bytes(content)
            os.replace(temp, destino)
        finally:
            temp.unlink(missing_ok=True)
        return {'guardado': True, 'nombre': destino.name}

    def cerrar(self):
        # El metodo se invoca desde el puente JS; destruir tras responder evita
        # interrumpir la respuesta de la promesa al cerrar WebView2.
        threading.Timer(0.15, self._window.destroy).start()
        return {'ok': True}


def main() -> None:
    if sys.platform != 'win32':
        raise RuntimeError('Este lanzador es exclusivo de Windows.')
    setup_logging()
    log_startup("INICIO Recambios V0.2.6")
    if not webview2_installed():
        message('Falta Microsoft Edge WebView2 Runtime.\n\n'
                'Instálalo desde la página oficial de Microsoft y vuelve a abrir Recambios:\n'
                'https://developer.microsoft.com/microsoft-edge/webview2/\n\n'
                'No necesitas instalar el navegador Microsoft Edge.',
                'Falta WebView2 Runtime')
        return

    log_startup("WebView2 Runtime detectado")
    os.environ['INVENTARIO_PRO10_DATA_DIR'] = str(DATA_DIR)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    mutex = kernel.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex:
        message('No se pudo iniciar Recambios. Consulta errores.log en AppData\\Local\\Recambios.')
        return
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        if not focus_existing_window():
            message('Recambios ya se está ejecutando. Comprueba la ventana abierta.')
        kernel.CloseHandle(mutex)
        return

    server = None
    worker = None
    try:
        import inventario
        import webview
        log_startup('Módulos importados')
        inventario.setup()
        log_startup('Base de datos preparada')
        server = inventario.ThreadingHTTPServer(('127.0.0.1', 0), inventario.Handler)
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True)
        worker.start()
        log_startup("Servidor local activo")
        save_instance(server.server_port)
        url = f'http://127.0.0.1:{server.server_port}/'

        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
        # Los ZIP de copia de seguridad y los enlaces externos deben funcionar.
        webview.settings['ALLOW_DOWNLOADS'] = True
        bridge = DesktopBridge()
        bridge._window = webview.create_window(
            'Recambios', url, js_api=bridge,
            width=1290, height=820, min_size=(830, 570),
            background_color='#151b26', text_select=True,
            confirm_close=False,
        )
        # Fallback del botón «Cerrar programa» si el puente JS no está disponible.
        inventario.ON_DESKTOP_EXIT = bridge._window.destroy
        def maximizar_al_mostrar():
            # Maximizada (no pantalla completa): conserva la barra de tareas
            # y los botones normales de minimizar, restaurar y cerrar.
            bridge._window.maximize()
            log_startup('Ventana mostrada y maximizada')
        bridge._window.events.shown += maximizar_al_mostrar
        bridge._window.events.loaded += lambda: log_startup('Contenido cargado')
        # Fuerza WebView2. No se permite pasar a MSHTML ni abrir Chrome.
        # Mantiene los datos de WebView2 fuera de la carpeta instalada.
        log_startup('Entrando en WebView2')
        webview.start(
            gui='edgechromium', private_mode=False,
            storage_path=str(APP_DIR / 'WebView2'),
            debug=False,
        )
        log_startup('WebView2 finalizado')
    except Exception:
        log_startup("ERROR al abrir")
        traceback.print_exc(file=sys.stderr)
        message('No se ha podido abrir Recambios.\n\n'
                'Consulta el registro de errores en:\n'
                '%LOCALAPPDATA%\\Recambios\\errores.log', 'Error al iniciar Recambios')
    finally:
        log_startup("Cerrando servidor")
        if server is not None:
            server.shutdown()
            server.server_close()
        if worker is not None:
            worker.join(timeout=3)
        delete_instance()
        kernel.CloseHandle(mutex)
        log_startup("CIERRE")


if __name__ == '__main__':
    main()
