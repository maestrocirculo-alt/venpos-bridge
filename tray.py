"""
Ícono en la bandeja del sistema (System Tray) para VenPOS Bridge.
Requiere: pystray, Pillow
"""
import os, sys, subprocess, threading
try:
    import pystray
    from pystray import MenuItem as Item
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError: TRAY_AVAILABLE = False

def _create_icon_image(color="#047857"):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=color)
    draw.polygon([(16,18),(24,18),(32,44),(40,18),(48,18),(32,54)], fill="white")
    return img

def run_tray(version="1.0.0"):
    if not TRAY_AVAILABLE: threading.Event().wait(); return
    icon_image = _create_icon_image()
    def on_open_log(icon, item):
        log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venpos_bridge.log")
        if sys.platform == "win32": os.startfile(log_file)
        else: subprocess.Popen(["xdg-open", log_file])
    def on_quit(icon, item): icon.stop(); os._exit(0)
    def on_status(icon, item):
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast("VenPOS Bridge", f"Corriendo en http://127.0.0.1:8765\nVersión {version}", duration=4, threaded=True)
        except Exception: pass
    menu = pystray.Menu(Item(f"VenPOS Bridge v{version}", lambda i, it: None, enabled=False),
        Item("Estado: Corriendo ✓", on_status), pystray.Menu.SEPARATOR,
        Item("Ver registro (log)", on_open_log), pystray.Menu.SEPARATOR, Item("Detener Bridge", on_quit))
    icon = pystray.Icon(name="VenPOS Bridge", icon=icon_image, title=f"VenPOS Bridge v{version} — Activo", menu=menu)
    icon.run()
