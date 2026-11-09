# Recambios V0.2.6 — código fuente para Windows

Versión principal V0.2.6, instalada y probada en Windows por el propietario. Proyecto en desarrollo activo; pueden existir actualizaciones posteriores.

Este repositorio contiene **solo el código fuente, la interfaz y los scripts necesarios para preparar el instalador**. No contiene inventarios personales, fotografías de piezas ni copias ZIP de datos.

## Estructura

- `inventario.py`: lógica del catálogo, servidor local y persistencia SQLite.
- `recambios_windows.py`: ejecución independiente de Windows mediante pywebview / WebView2.
- `web/`: interfaz HTML, CSS y JavaScript.
- `CREAR_INSTALADOR_WINDOWS.bat`: compilación y creación del instalador para Windows.
- `Recambios_Instalador.iss`: configuración de Inno Setup.
- `LEEME_INSTALADOR_WINDOWS.txt`: instrucciones completas de construcción.

## Instalación y conservación de datos

El programa instalado separa sus inventarios del ejecutable y documenta la ruta de datos `%LOCALAPPDATA%\Recambios\Datos`. **Antes de actualizar, exporta una copia de seguridad ZIP desde el programa**. No compartas esa copia en el repositorio.

La aplicación debe iniciar sin inventarios precreados cuando no existen datos del usuario. Si ya los hay, debe conservarlos.

Para compilar una distribución de Windows, consulta `LEEME_INSTALADOR_WINDOWS.txt` y ejecuta el BAT de construcción en un PC Windows con los requisitos indicados. Este repositorio **no incluye el instalador EXE compilado**. Cuando se conserve y pruebe el instalador correspondiente, podrá adjuntarse por separado a una GitHub Release.

## Seguridad y privacidad

La publicación excluye bases de datos, fotografías, archivos de usuario y copias de seguridad. `.gitignore` ayuda a impedir subidas accidentales desde Git, pero **no protege frente a una carga manual desde el navegador**: comprueba siempre los archivos antes de confirmar una subida.

No se ha modificado el programa original para preparar esta copia de código.
