"""Descarga el bootstrapper firmado de WebView2 desde Microsoft para Inno Setup.

Ejecutar SOLO en el PC Windows de compilación. No ejecuta el instalador.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
DESTINO = HERE / 'prerequisitos' / 'MicrosoftEdgeWebView2Setup.exe'
URL_MICROSOFT = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'


def signature_ok(path: Path) -> bool:
    # Comprueba que Windows valida la firma Authenticode y que el editor es Microsoft.
    safe_path = str(path.resolve()).replace("'", "''")
    script = (
        "$s=Get-AuthenticodeSignature -LiteralPath '" + safe_path + "'; "
        'if ($s.Status -eq "Valid" -and $s.SignerCertificate.Subject -match "O=Microsoft Corporation")'
        '{ exit 0 } else { Write-Host "Firma no valida o editor no es Microsoft"; exit 1 }'
    )
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
            capture_output=True, text=True, timeout=40,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main() -> int:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    if DESTINO.is_file() and DESTINO.stat().st_size > 200_000 and signature_ok(DESTINO):
        print('Bootstrapper oficial de Microsoft ya descargado y firmado.')
        return 0
    print('Descargando WebView2 Runtime bootstrapper desde Microsoft...')
    temporal = DESTINO.with_name('MicrosoftEdgeWebView2Setup.tmp.exe')
    temporal.unlink(missing_ok=True)
    try:
        req = urllib.request.Request(URL_MICROSOFT, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=45) as res, temporal.open('wb') as output:
            total = 0
            while True:
                chunk = res.read(128 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 20 * 1024 * 1024:
                    raise RuntimeError('Descarga inesperadamente grande.')
                output.write(chunk)
        if temporal.stat().st_size < 200_000 or not signature_ok(temporal):
            raise RuntimeError('El archivo descargado no supera la validación de firma digital de Microsoft.')
        os.replace(temporal, DESTINO)
        print('Bootstrapper WebView2 verificado y listo para incluir en el instalador.')
        return 0
    except Exception as exc:
        print('ERROR: No se ha podido preparar el WebView2 Runtime:', exc)
        print('Descárgalo manualmente desde:')
        print('  https://developer.microsoft.com/microsoft-edge/webview2/')
        print('  Evergreen Bootstrapper -> Download')
        print('Guárdalo en:', DESTINO)
        print('Después ejecuta otra vez el BAT de compilación.')
        return 1
    finally:
        temporal.unlink(missing_ok=True)


if __name__ == '__main__':
    sys.exit(main())
