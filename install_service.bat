@echo off
:: Instala VenPOS Bridge como servicio de Windows para que arranque automáticamente
:: Requisito: NSSM (Non-Sucking Service Manager) en PATH o en la misma carpeta
:: Descargar NSSM: https://nssm.cc/download

echo Instalando VenPOS Bridge como servicio de Windows...

set EXE_PATH=%~dp0dist\VenPOS-Bridge.exe
set SERVICE_NAME=VenPosBridge

nssm install %SERVICE_NAME% "%EXE_PATH%"
nssm set %SERVICE_NAME% DisplayName "VenPOS Bridge - Impresora Fiscal"
nssm set %SERVICE_NAME% Description "Servidor local de VenPOS para control de impresoras fiscales venezolanas"
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm start %SERVICE_NAME%

echo.
echo Servicio "%SERVICE_NAME%" instalado y arrancado.
echo Para desinstalar: nssm remove %SERVICE_NAME%
pause