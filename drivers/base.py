"""
Driver base para todas las impresoras fiscales.
Cada driver concreto hereda de esta clase e implementa los métodos abstractos.
Incluye la interfaz completa de operaciones fiscales SENIAT:
  - Emisión de factura / nota de entrega / ticket
  - Reporte X (lectura parcial) y Cierre Z (cierre de jornada)
  - Cancelar/abortar documento fiscal abierto (recuperación tras corte)
  - Consulta de estado fiscal detallado (papel, documento abierto, Z pendiente)
"""
import serial, logging
from abc import ABC, abstractmethod
from typing import Tuple

log = logging.getLogger("FiscalDriver")

class BaseFiscalDriver(ABC):
    def __init__(self, config):
        self.config = config
        self._serial = None

    def _open_port(self) -> serial.Serial:
        port = self.config.port or "COM1"
        conn = serial.Serial(port=port, baudrate=int(self.config.baud_rate or 9600),
            bytesize=int(self.config.data_bits or 8), parity=str(self.config.parity or "N"),
            stopbits=int(self.config.stop_bits or 1), timeout=float(self.config.timeout or 10))
        log.info(f"Puerto {port} abierto a {self.config.baud_rate} bps")
        return conn

    def _close_port(self, conn):
        try:
            if conn and conn.is_open: conn.close()
        except Exception: pass

    def check_connection(self) -> Tuple[bool, str]:
        try:
            conn = self._open_port(); self._close_port(conn)
            return True, f"Puerto {self.config.port} OK"
        except serial.SerialException as e:
            return False, f"No se puede abrir {self.config.port}: {e}"

    @staticmethod
    def _fmt_amount(value, decimals=2): return f"{value:.{decimals}f}"
    @staticmethod
    def _fmt_date(iso):
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00")); return dt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception: return iso[:19]
    @staticmethod
    def _truncate(text, max_len): return (text or "")[:max_len]

    @abstractmethod
    def print_fiscal_invoice(self, payload): pass

    def print_text(self, text) -> dict:
        conn = None
        try:
            conn = self._open_port()
            encoding = self.config.encoding or "latin-1"
            conn.write((text + "\n\n").encode(encoding, errors="replace")); conn.flush()
            return {"success": True}
        except Exception as e:
            log.error(f"print_text error: {e}", exc_info=True); return {"success": False, "error": str(e)}
        finally: self._close_port(conn)

    def print_test(self): return {"success": True, "message": "Test no implementado para este driver"}
    def get_fiscal_status(self): return {"success": False, "paper_ok": None, "doc_open": None, "z_pending": None, "printer_ready": None, "error": "Consulta de estado fiscal no soportada por este driver"}
    def print_report_x(self): return {"success": False, "error": "Reporte X no soportado por este driver"}
    def print_report_z(self): return {"success": False, "error": "Cierre Z no soportado por este driver"}
    def cancel_document(self): return {"success": False, "error": "Cancelación de documento no soportada por este driver"}
