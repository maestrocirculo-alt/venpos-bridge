import os, sys, subprocess, threading
try:
    import pystray
    from pystray import MenuItem as Item
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

def _create_icon():
    img = Image.new('RGBA', (64, 64), (0,0,0,0))
    d = ImageDraw.Draw(img)
    d.ellipse([4,4,60,60], fill='#047857')
    d.polygon([(16,18),(24,18),(32,44),(40,18),(48,18),(32,54)], fill='white')
    return img

def run_tray(version='1.0.0'):
    if not TRAY_AVAILABLE:
        threading.Event().wait()
        return
    def on_log(icon, item):
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venpos_bridge.log')
        if sys.platform == 'win32': os.startfile(f)
        else: subprocess.Popen(['xdg-open', f])
    def on_quit(icon, item):
        icon.stop(); os._exit(0)
    menu = pystray.Menu(
        Item(f'VenPOS Bridge v{version}', lambda i,it: None, enabled=False),
        Item('Estado: Corriendo', on_quit),
        pystray.Menu.SEPARATOR,
        Item('Ver log', on_log),
        pystray.Menu.SEPARATOR,
        Item('Detener', on_quit),
    )
    icon = pystray.Icon('VenPOS Bridge', _create_icon(), f'VenPOS Bridge v{version}', menu)
    icon.run()