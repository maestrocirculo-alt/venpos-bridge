"""
VenPOS Bridge — Servidor HTTP local para control de impresoras fiscales venezolanas.
Corre en http://127.0.0.1:8765 y recibe solicitudes de impresión desde la app web.

Soporta: HKA, NCR, Bematech, ACLAS, EPSON Fiscal, Datasym
Requisitos: pip install -r requirements.txt
Ejecutar:   python bridge.py
"""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

from printer_manager import PrinterManager
from config import BridgeConfig

VERSION = "1.0.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("venpos_bridge.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("VenPOS-Bridge")

config = BridgeConfig()
printer_mgr = PrinterManager(config)


class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info(f"{self.client_address[0]} - {format % args}")

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/status":
            self._handle_status()
        elif self.path == "/config":
            self._handle_get_config()
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/print/fiscal":
            self._handle_print_fiscal()
        elif self.path == "/print/test":
            self._handle_test_print()
        elif self.path == "/config":
            self._handle_set_config()
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_status(self):
        ready, detail = printer_mgr.check_printer()
        self._send_json({
            "ok": True,
            "version": VERSION,
            "printer_ready": ready,
            "printer_detail": detail,
            "printer_brand": config.brand,
            "printer_model": config.model,
            "port": config.port,
            "timestamp": datetime.now().isoformat(),
        })

    def _handle_get_config(self):
        self._send_json(config.to_dict())

    def _handle_set_config(self):
        try:
            data = self._read_body()
            config.update(data)
            config.save()
            printer_mgr.reload(config)
            self._send_json({"success": True, "config": config.to_dict()})
        except Exception as e:
            log.error(f"Error actualizando config: {e}")
            self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_print_fiscal(self):
        try:
            payload = self._read_body()
            log.info(f"Imprimiendo factura: {payload.get('numero_control')} / {payload.get('numero_factura')}")
            result = printer_mgr.print_fiscal(payload)
            if result["success"]:
                log.info(f"Impresion exitosa N Control: {payload.get('numero_control')}")
                self._send_json(result)
            else:
                log.error(f"Error en impresion: {result.get('error')}")
                self._send_json(result, 500)
        except Exception as e:
            log.error(f"Excepcion en impresion: {e}", exc_info=True)
            self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_test_print(self):
        try:
            result = printer_mgr.print_test()
            self._send_json(result)
        except Exception as e:
            self._send_json({"success": False, "error": str(e)}, 500)


def run_server():
    host = "127.0.0.1"
    port = 8765
    server = HTTPServer((host, port), BridgeHandler)
    log.info(f"VenPOS Bridge v{VERSION} iniciado en http://{host}:{port}")
    log.info(f"Impresora configurada: {config.brand} {config.model} en {config.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Bridge detenido.")
        server.shutdown()


if __name__ == "__main__":
    try:
        from tray import run_tray
        t = threading.Thread(target=run_server, daemon=True)
        t.start()
        run_tray(VERSION)
    except Exception:
        run_server()
