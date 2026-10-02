"""
VenPOS Bridge — Servidor HTTP local para control de impresoras fiscales venezolanas.
Corre en http://127.0.0.1:8765 y recibe solicitudes de impresión desde la app web.

Endpoints:
  GET  /status         — versión + estado de la impresora fiscal (handshake real ENQ) + térmica de tickets
  GET  /diagnose       — informe de diagnóstico (?scan=1 prueba también los demás puertos COM)
  GET  /config         — leer configuración (perfiles fiscal y ticket)
  POST /config         — actualizar configuración ({"profile": "fiscal"|"ticket", ...})
  POST /print/fiscal   — emitir factura fiscal
  POST /print/ticket   — imprimir ticket no fiscal (texto plano) en la térmica
  POST /print/test     — comprobar comunicación con la impresora fiscal
  POST /report/x       — Reporte X (lectura parcial, no cierra jornada)
  POST /report/z       — Cierre Z (cierre de jornada — irreversible)
  POST /cancel-doc     — Anular documento fiscal abierto

Impresoras HKA / ACLAS (PP9-PLUS, PP9A...): protocolo directo del fabricante
(Manual de Protocolos y Comandos V8.5.0) — ver drivers/hka_protocol.py.
Requisitos: pip install -r requirements.txt
Ejecutar:   python bridge.py
"""

import json
import logging
import logging.handlers
import os
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from printer_manager import PrinterManager
from config import BridgeConfig, _base_dir
from diagnostics import run_diagnostics

VERSION = "5.0.0"

# Log junto al ejecutable (persistente aunque esté compilado con PyInstaller)
LOG_FILE = os.path.join(_base_dir(), "venpos_bridge.log")

_handlers = [logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")]
if sys.stderr is not None:
    _handlers.append(logging.StreamHandler())
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_handlers,
)
log = logging.getLogger("VenPOS-Bridge")

config = BridgeConfig()
printer_mgr = PrinterManager(config)


class BridgeServer(ThreadingHTTPServer):
    # IMPORTANTE: en Windows SO_REUSEADDR permite que DOS copias del Bridge escuchen el
    # mismo puerto y la app termina hablando con la copia vieja. Se desactiva para que
    # la segunda copia falle al arrancar y avise.
    allow_reuse_address = False
    daemon_threads = True


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
        # Imprescindible para que Chrome/Edge permitan llamadas desde la página
        # web HTTPS a este servidor HTTP local (Private Network Access).
        self.send_header("Access-Control-Allow-Private-Network", "true")
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
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/status":
            self._handle_status()
        elif url.path == "/config":
            self._send_json(config.to_dict())
        elif url.path == "/diagnose":
            self._handle_diagnose(parse_qs(url.query).get("scan", ["0"])[0] in ("1", "true"))
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/print/fiscal":
            self._handle_print_fiscal()
        elif path == "/print/test":
            self._handle_test_print()
        elif path == "/print/ticket":
            self._handle_print_ticket()
        elif path == "/report/x":
            self._run_op("Reporte X (lectura parcial)", printer_mgr.print_report_x)
        elif path == "/report/z":
            self._run_op("⚠ Cierre Z (jornada fiscal — irreversible)", printer_mgr.print_report_z)
        elif path == "/cancel-doc":
            self._run_op("Anular documento fiscal abierto", printer_mgr.cancel_document)
        elif path == "/diagnose":
            try:
                self._handle_diagnose(bool(self._read_body().get("scan")))
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
        elif path == "/config":
            self._handle_set_config()
        else:
            self._send_json({"error": "Not found"}, 404)

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _handle_status(self):
        # Handshake real con la impresora fiscal (ENQ) y estado de la térmica de tickets.
        ready, detail, fstatus = printer_mgr.fiscal_snapshot()
        self._send_json({
            "ok": True,
            "version": VERSION,
            "printer_ready": ready,
            "printer_detail": detail,
            "printer_brand": config.brand,
            "printer_model": config.model,
            "port": config.port,
            "timestamp": datetime.now().isoformat(),
            "fiscal": fstatus,
            "ticket": printer_mgr.ticket_status(),
        })

    def _handle_diagnose(self, scan: bool):
        try:
            log.info(f"Diagnóstico solicitado (scan={scan})")
            result = run_diagnostics(config, VERSION, scan=scan)
            log.info("Diagnóstico:\n" + result["report_text"])
            self._send_json(result)
        except Exception as e:
            log.error(f"Error en diagnóstico: {e}", exc_info=True)
            self._send_json({"ok": False, "error": str(e)}, 500)

    def _handle_set_config(self):
        try:
            data = self._read_body()
            profile = "ticket" if data.pop("profile", "fiscal") == "ticket" else "fiscal"
            config.update(data, profile)
            config.save()
            printer_mgr.reload(config)
            log.info(f"Config actualizada (perfil {profile}): {json.dumps(config.to_dict(), ensure_ascii=False)}")
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
                log.info(f"✓ Impresión exitosa — N° Control: {payload.get('numero_control')} — código: {result.get('code','?')}")
                self._send_json(result)
            else:
                log.error(f"✗ Error en impresión: {result.get('error')} — código: {result.get('code','?')}")
                self._send_json(result, 500)
        except Exception as e:
            log.error(f"Excepción en impresión: {e}", exc_info=True)
            self._send_json({"success": False, "error": str(e), "code": "E501"}, 500)

    def _handle_test_print(self):
        try:
            self._send_json(printer_mgr.print_test())
        except Exception as e:
            self._send_json({"success": False, "error": str(e)}, 500)

    def _handle_print_ticket(self):
        # Ticket no fiscal automático (texto plano + logo opcional)
        try:
            payload = self._read_body()
            text = payload.get("text", "")
            logo_url = payload.get("logo_url", "")
            if not text:
                return self._send_json({"success": False, "error": "Texto vacío"}, 400)
            log.info(f"Imprimiendo ticket no fiscal ({len(text)} chars)" + (" + logo" if logo_url else ""))
            result = printer_mgr.print_text(text, logo_url)
            if result.get("success"):
                log.info("✓ Ticket no fiscal impreso")
                self._send_json(result)
            else:
                log.error(f"✗ Ticket no fiscal falló: {result.get('error')}")
                self._send_json(result, 409 if result.get("code") == "NO_TICKET_PRINTER" else 500)
        except Exception as e:
            log.error(f"Excepción en ticket no fiscal: {e}", exc_info=True)
            self._send_json({"success": False, "error": str(e)}, 500)

    def _run_op(self, label: str, fn):
        try:
            log.info(f"Emitiendo: {label}")
            result = fn()
            if result.get("success"):
                log.info(f"✓ {label} — OK {json.dumps({k: v for k, v in result.items() if k != 'raw'}, ensure_ascii=False)}")
            else:
                log.error(f"✗ {label} falló: {result.get('error')}")
            self._send_json(result, 200 if result.get("success") else 500)
        except Exception as e:
            log.error(f"Excepción en {label}: {e}", exc_info=True)
            self._send_json({"success": False, "error": str(e)}, 500)


def _show_error(msg: str):
    log.error(msg)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "VenPOS Bridge", 0x10)
    except Exception:
        pass


def acquire_single_instance() -> bool:
    """Una sola copia del Bridge por sesión de Windows."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Local\\VenPOS_Bridge_Singleton")
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return False
        globals()["_mutex_handle"] = handle  # mantener vivo mientras corra el proceso
    except Exception:
        pass
    return True


def run_server():
    host = "127.0.0.1"
    port = 8765
    try:
        server = BridgeServer((host, port), BridgeHandler)
    except OSError:
        # Puerto ocupado: casi siempre es otra copia (vieja) del Bridge abierta.
        _show_error(f"No se pudo iniciar el VenPOS Bridge: el puerto {port} ya está en uso.\n\n"
                    "Hay otra copia del Bridge abierta (quizá una versión anterior). Ciérrala desde el ícono "
                    "de la bandeja del sistema (junto al reloj) con 'Detener Bridge' y abre este programa de nuevo.")
        os._exit(1)
    log.info(f"VenPOS Bridge v{VERSION} iniciado en http://{host}:{port} (pid {os.getpid()})")
    log.info(f"Perfil fiscal: {config.brand} {config.model} en {config.port} · "
             f"Tickets: {'configurado' if config.ticket.configured else 'no configurado'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Bridge detenido.")
        server.shutdown()


if __name__ == "__main__":
    if not acquire_single_instance():
        _show_error("El VenPOS Bridge ya está abierto (busca su ícono verde junto al reloj de Windows).")
        os._exit(1)
    # El servidor corre en un hilo; el ícono de la bandeja (opcional) bloquea el hilo principal.
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    try:
        from tray import run_tray
        run_tray(VERSION)
    except Exception as e:
        log.warning(f"Sin ícono de bandeja ({e}); el Bridge sigue corriendo.")
    t.join()