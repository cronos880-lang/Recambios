# Recambios — última entrega V0.2.8 (Mis Listas)

Esta rama (`desarrollo-v0.2.8-mis-listas`) contiene la **V0.2.8 más reciente**, con todo lo necesario para **generar el instalador en Windows**. La rama `main` conserva la V0.2.6 estable y recuperable.

**[Descargar V0.2.8 COMPLETA — proyecto para instalador Windows](https://github.com/cronos880-lang/Recambios/blob/desarrollo-v0.2.8-mis-listas/entregas/Recambios_V0_2_8_COMPLETA_Instalador_Windows.zip?raw=true)**

> El ZIP contiene código fuente, interfaz y scripts de compilación. No contiene un EXE precompilado: debes crear el instalador en tu ordenador Windows con `CREAR_INSTALADOR_WINDOWS.bat` (Python 3.11/3.12 x64, Inno Setup 6). El EXE resultante no tendrá firma digital. La compilación y el instalador no están validados todavía en Windows.

## Cambios en V0.2.8

- «Mis Listas»: crear, renombrar y eliminar listas de compra independientes del catálogo.
- Cantidades por lista y fotografía de la pieza.
- Elegir la tienda concreta cuando el artículo tiene varios enlaces de compra; ver foto y URL.
- Una misma pieza puede añadirse desde tiendas diferentes; las listas nunca alteran los artículos del catálogo.
- Copias de seguridad ZIP con catálogos, fotografías, listas y cantidades.
- Ventana nativa WebView2 maximizada, sin abrir una pestaña de Chrome o Edge.
- Inicio sin inventarios precreados si no hay datos previos.

## Migración y desinstalación sin pérdida de datos

**Lee primero `GUIA_CAMBIO_V026_A_V028.txt`.**

La V0.2.8 instalada utiliza la misma ubicación de datos que V0.2.6:

`%LOCALAPPDATA%\Recambios\Datos`

La prueba portátil V0.2.8 guardaba en otra carpeta:

`%LOCALAPPDATA%\Recambios_Pruebas\Datos`

La carpeta de pruebas **no se incorpora automáticamente**: exporta un ZIP desde ella si quieres importar sus listas. Antes de desinstalar la V0.2.6, haz su copia ZIP y guárdala fuera de la carpeta del programa. No borres ninguna carpeta `Datos`.

Se conserva el `AppId` de Inno Setup de V0.2.6, por lo que también puedes instalar la nueva versión encima de la antigua sin desinstalar. El instalador **no borra los datos** del usuario.

## Estado y seguridad

Versión: **V0.2.8 desarrollada y publicada como código instalable**. Pruebas automáticas de Python, JavaScript, SQLite y copias ZIP satisfactorias. **Pendiente de comprobar la compilación real y el funcionamiento del instalador en Windows**; la publicación no equivale a aprobación oficial del usuario.

No hay inventarios personales, fotografías ni bases de datos de usuario incluidos en el repositorio. Ninguna aplicación de la Suite de Programas ha sido modificada.
