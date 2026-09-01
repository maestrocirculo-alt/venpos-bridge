@echo off
:: VenPOS Bridge — Script para compilar el ejecutable con PyInstaller
echo ============================================
echo  VenPOS Bridge - Generando .exe (v1.1)
echo ============================================
echo.
echo [1/3] Instalando dependencias (PyInstaller, PySerial, Pystray, Pillow)...
python -m pip install --upgrade pip
python -m pip install pyinstaller pyserial pystray Pillow
if errorlevel 1 (
  echo *** ERROR: no se pudieron instalar las dependencias. ***
  pause
  exit /b 1
)
set ICON_FLAG=
if exist "icon.ico" set ICON_FLAG=--icon "icon.ico"
echo [2/3] Compilando el ejecutable... (tarda 1-3 minutos)
python -m PyInstaller --onefile --noconsole --name "VenPOS-Bridge" %ICON_FLAG% --hidden-import pystray._win32 --collect-submodules PIL bridge.py
if errorlevel 1 (
  echo *** ERROR: PyInstaller fallo al compilar. ***
  pause
  exit /b 1
)
if not exist "dist\VenPOS-Bridge.exe" (
  echo *** ERROR: no se encontro dist\VenPOS-Bridge.exe ***
  pause
  exit /b 1
)
echo [3/3] Compilacion exitosa.
echo  LISTO! El ejecutable esta en: dist\VenPOS-Bridge.exe
pause
