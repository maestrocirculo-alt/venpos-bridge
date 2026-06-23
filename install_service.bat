@echo off
set EXE_PATH=%~dp0dist\VenPOS-Bridge.exe
set SERVICE_NAME=VenPosBridge
nssm install %SERVICE_NAME% "%EXE_PATH%"
nssm set %SERVICE_NAME% DisplayName "VenPOS Bridge - Impresora Fiscal"
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm start %SERVICE_NAME%
echo Servicio instalado.
pause