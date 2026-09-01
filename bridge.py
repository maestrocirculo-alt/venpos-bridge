"""
VenPOS Bridge — Servidor HTTP local para control de impresoras fiscales venezolanas.
Corre en http://127.0.0.1:8765 y recibe solicitudes de impresión desde la app web.

Endpoints:
  GET  /status         — versión del bridge + estado físico + estado fiscal
  GET  /config         — leer configuración
  POST /config         — actualizar configuración
  POST /print/fiscal   — emitir factura / nota de entrega / ticket fiscal
  POST /print/ticket   — imprimir ticket no fiscal (texto plano, automático, sin botón)
  POST /print/test     — imprimir línea de prueba
  POST /report/x       — Reporte X (lectura parcial, no cierra jornada)
  POST /report/z       — Cierre Z (cierre de jornada — irreversible)
  POST /cancel-doc     — Cancelar/abortar documento fiscal abierto

Soporta: HKA, NCR, Bematech, ACLAS, EPSON Fiscal, Datasym
Requisitos: pip install -r requirements.txt
Ejecutar:   python bridge.py
"""

import json
import logging
import threading
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

from printer_manager import PrinterManager
from config import BridgeConfig, _base_dir

VERSION = "1.1.0"
LOG_FILE = os.path.join(_base_dir(), "venpos_bridge.log")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()])
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
        if length == 0: return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/status": self._handle_status()
        elif self.path == "/config": self._handle_get_config()
        else: self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/print/fiscal": self._handle_print_fiscal()
        elif self.path == "/print/test": self._handle_test_print()
        elif self.path == "/print/ticket": self._handle_print_ticket()
        elif self.path == "/report/x": self._handle_report_x()
        elif self.path == "/report/z": self._handle_report_z()
        elif self.path == "/cancel-doc": self._handle_cancel_doc()
        elif self.path == "/config": self._handle_set_config()
        else: self._send_json({"error": "Not found"}, 404)

    def _handle_status(self):
        ready, detail = printer_mgr.check_printer()
        fstatus = printer_mgr.get_fiscal_status()
        self._send_json({"ok": True, "version": VERSION, "printer_ready": ready, "printer_detail": detail,
            "printer_brand": config.brand, "printer_model": config.model, "port": config.port,
            "timestamp": datetime.now().isoformat(), "fiscal": fstatus})

    def _handle_get_config(self): self._send_json(config.to_dict())

    def _handle_set_config(self):
        try:
            data = self._read_body(); config.update(data); config.save(); printer_mgr.reload(config)
            self._send_json({"success": True, "config": config.to_dict()})
        except Exception as e: self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_print_fiscal(self):
        try:
            payload = self._read_body()
            result = printer_mgr.print_fiscal(payload)
            self._send_json(result, 200 if result["success"] else 500)
        except Exception as e: self._send_json({"success": False, "error": str(e), "code": "E501"}, 500)

    def _handle_test_print(self):
        try: self._send_json(printer_mgr.print_test())
        except Exception as e: self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_print_ticket(self):
        try:
            payload = self._read_body(); text = payload.get("text", "")
            if not text: return self._send_json({"success": False, "error": "Texto vacío"}, 400)
            result = printer_mgr.print_text(text)
            self._send_json(result, 200 if result.get("success") else 500)
        except Exception as e: self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_report_x(self):
        try: r = printer_mgr.print_report_x(); self._send_json(r, 200 if r.get("success") else 500)
        except Exception as e: self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_report_z(self):
        try: r = printer_mgr.print_report_z(); self._send_json(r, 200 if r.get("success") else 500)
        except Exception as e: self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_cancel_doc(self):
        try: r = printer_mgr.cancel_document(); self._send_json(r, 200 if r.get("success") else 500)
        except Exception as e: self._send_json({"success": False, "error": str(e)}, 500)


def run_server():
    host = "127.0.0.1"; port = 8765
    server = HTTPServer((host, port), BridgeHandler)
    log.info(f"VenPOS Bridge v{VERSION} iniciado en http://{host}:{port}")
    log.info(f"Impresora configurada: {config.brand} {config.model} en {config.port}")
    try: server.serve_forever()
    except KeyboardInterrupt: log.info("Bridge detenido."); server.shutdown()


if __name__ == "__main__":
    try:
        from tray import run_tray
        t = threading.Thread(target=run_server, daemon=True); t.start(); run_tray(VERSION)
    except Exception: run_server()
