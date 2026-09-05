@echo off
:: VenPOS Bridge — Script para compilar el ejecutable con PyInstaller
:: Requisito: tener Python instalado (con "Add Python to PATH" marcado)
:: Ejecutar: doble clic sobre este archivo

echo ============================================
echo  VenPOS Bridge - Generando .exe (v2.0.0)
echo ============================================
echo.

echo [1/3] Instalando dependencias (PyInstaller, PySerial, Pystray, Pillow, pywin32)...
python -m pip install --upgrade pip
python -m pip install pyinstaller pyserial pystray Pillow pywin32
if errorlevel 1 (
  echo.
  echo *** ERROR: no se pudieron instalar las dependencias. ***
  echo Verifica que tienes internet y que Python quedo bien instalado.
  pause
  exit /b 1
)
python -m pip install --force-reinstall pywin32
python -c "import sys, os; import pywin32_postinstall; pywin32_postinstall.install(remove_other=True, silent=True); print('pywin32 postinstall OK')"
echo  OK dependencias instaladas (incluye pywin32).
echo.

set ICON_FLAG=
if exist "icon.ico" set ICON_FLAG=--icon "icon.ico"

echo [2/3] Compilando el ejecutable... (tarda 1-3 minutos)
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
