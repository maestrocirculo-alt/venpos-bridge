@echo off
cd /d "%~dp0"
echo ============================================
echo  VenPOS Bridge - Generando .exe (v5.0.0)
echo ============================================
echo  Carpeta: %CD%
echo.

echo [1/3] Instalando dependencias...
python -m pip install --upgrade pip
python -m pip install pyinstaller pyserial pystray Pillow pywin32
if errorlevel 1 goto :error_deps
echo  OK dependencias instaladas.
echo.

echo [2/3] Compilando el ejecutable... (1-3 minutos)
set ICON_FLAG=
if exist "icon.ico" set ICON_FLAG=--icon "icon.ico"
python -m PyInstaller --onefile --noconsole --name "VenPOS-Bridge" %ICON_FLAG% --hidden-import pystray._win32 --collect-submodules PIL --collect-all pywin32 --hidden-import win32print --hidden-import win32api --hidden-import win32con --hidden-import serial.tools.list_ports --hidden-import serial.tools.list_ports_windows bridge.py
if errorlevel 1 goto :error_build

if not exist "dist\VenPOS-Bridge.exe" goto :error_noexe

echo.
echo [3/3] Compilacion exitosa.
echo ============================================
echo  LISTO! El ejecutable esta en: dist\VenPOS-Bridge.exe
echo  Copialo a la PC con la impresora y ejecutalo (doble clic).
echo ============================================
goto :end

:error_deps
echo.
echo *** ERROR: no se pudieron instalar las dependencias. ***
echo Verifica que tienes internet y Python instalado (con "Add Python to PATH").
goto :end

:error_build
echo.
echo *** ERROR: PyInstaller fallo al compilar. ***
echo Revisa los mensajes de arriba.
goto :end

:error_noexe
echo.
echo *** ERROR: no se encontro dist\VenPOS-Bridge.exe ***
echo La compilacion fallo. Mira los errores arriba.

:end
echo.
pause