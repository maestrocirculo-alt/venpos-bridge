@echo off
pip install pyinstaller pyserial pystray Pillow --quiet
pyinstaller --onefile --noconsole --name "VenPOS-Bridge" bridge.py
echo Listo! dist\VenPOS-Bridge.exe
pause
