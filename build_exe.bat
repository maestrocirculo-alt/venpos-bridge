@echo off
:: VenPOS Bridge — Script para compilar el ejecutable con PyInstaller
:: Requisito: tener Python instalado (con "Add Python to PATH" marcado)
:: Ejecutar: doble clic sobre este archivo
:: NO necesita administrador — si se abre como admin, cambia solo a su carpeta.

:: Cambiar al directorio donde esta este .bat (no desde System32)
cd /d "%~dp0"

echo ============================================
echo  VenPOS Bridge - Generando .exe (v3.0.0)
echo ============================================
echo.
echo  Carpeta de trabajo: %CD%
echo.

:: 1) Actualizar pip e instalar dependencias
echo [1/3] Instalando dependencias (PyInstaller, PySerial, Pystray, Pillow, pywin32)...
python -m pip install --upgrade pip
:: pywin32 es OBLIGATORIO: sin el el .exe no puede hablar con el spooler de
:: Windows para imprimir tickets en impresoras termicas USB (ACLAS, Xprinter,
:: Epson, etc.) y siempre cae al dialogo de impresion del navegador.
python -m pip install pyinstaller pyserial pystray Pillow pywin32
if errorlevel 1 (
  echo.
  echo *** ERROR: no se pudieron instalar las dependencias. ***
  echo Verifica que tienes internet y que Python quedo bien instalado.
  pause
  exit /b 1
)

:: pywin32 post-install: registrar las DLL COM/win32print.
:: El modulo pywin32_postinstall vive en Scripts\, no es importable directamente.
:: Lo localizamos via sys.prefix y lo ejecutamos como script.
echo  Ejecutando post-instalacion de pywin32...
for /f "tokens=*" %%i in ('python -c "import sys; print(sys.prefix)"') do set PY_HOME=%%i
if exist "%PY_HOME%\Scripts\pywin32_postinstall.py" (
  python "%PY_HOME%\Scripts\pywin32_postinstall.py" -install -silent
  echo  pywin32 postinstall OK
) else (
  echo  pywin32_postinstall.py no encontrado — continuando igual (win32print funciona sin el).
)
echo  OK dependencias instaladas (incluye pywin32).
echo.

:: 2) Icono opcional
set ICON_FLAG=
if exist "icon.ico" set ICON_FLAG=--icon "icon.ico"

:: 3) Compilar con PyInstaller (usamos python -m para no depender del PATH de Scripts)
echo [2/3] Compilando el ejecutable... (tarda 1-3 minutos)
:: --collect-all pywin32 empaqueta win32print y sus DLLs (pythoncom, pywintypes)
:: para que el .exe pueda imprimir por el spooler de Windows (USB termico).
:: --hidden-import win32print refuerza la inclusion del modulo que abre la impresora.
python -m PyInstaller ^
  --onefile ^
  --noconsole ^
  --name "VenPOS-Bridge" ^
  %ICON_FLAG% ^
  --hidden-import pystray._win32 ^
  --collect-submodules PIL ^
  --collect-all pywin32 ^
  --hidden-import win32print ^
  --hidden-import win32api ^
  --hidden-import win32con ^
  bridge.py
if errorlevel 1 (
  echo.
  echo *** ERROR: PyInstaller fallo al compilar. ***
  echo Revisa los mensajes de arriba.
  pause
  exit /b 1
)

:: 4) Verificar que realmente existe el .exe
if not exist "dist\VenPOS-Bridge.exe" (
  echo.
  echo *** ERROR: no se encontro dist\VenPOS-Bridge.exe ***
  echo La compilacion fallo. Mira los errores arriba.
  pause
  exit /b 1
)

echo.
echo [3/3] Compilacion exitosa.
echo ============================================
echo  LISTO! El ejecutable esta en: dist\VenPOS-Bridge.exe
echo  Copia ese archivo a la PC con la impresora
echo  y ejecutalo (doble clic). Aparecera el icono verde
echo  en la bandeja del sistema.
echo ============================================
pause
