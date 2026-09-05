import serial
import logging
from abc import ABC, abstractmethod
from typing import Tuple

log = logging.getLogger("FiscalDriver")


def _is_windows_spooler(port: str) -> bool:
    if not port:
        return False
    p = str(port).upper()
    return p.startswith("USB") or p in ("SPOOLER", "WINDOWS", "WINSPOOL")


class WinSpoolerConnection:
    def __init__(self, printer_name: str, timeout: int = 10):
        self.printer_name = printer_name
        self.timeout = timeout
        self.is_open = False
        self._buf = bytearray()
        self._hprinter = None
        self._open()

    def _open(self):
        try:
            import win32print
        except ImportError as e:
            raise RuntimeError("win32print no disponible. Instala pywin32: pip install pywin32") from e
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        available = [p[2] for p in win32print.EnumPrinters(flags)]
        if not self.printer_name:
            raise RuntimeError("Falta el nombre de la impresora de Windows. Impresoras detectadas: " + (", ".join(available) or "(ninguna)"))
        if self.printer_name not in available:
            raise RuntimeError(f"La impresora '{self.printer_name}' no existe en Windows. Impresoras: {', '.join(available) or '(ninguna)'}")
        self._hprinter = win32print.OpenPrinter(self.printer_name)
        self.is_open = True

    def write(self, data):
        if isinstance(data, str):
            data = data.encode("latin-1", errors="replace")
        self._buf.extend(data)

    def flush(self):
        if not self._buf:
            return
        import win32print
        job = win32print.StartDocPrinter(self._hprinter, 1, ("VenPOS Ticket", None, "RAW"))
        try:
            win32print.StartPagePrinter(self._hprinter)
            win32print.WritePrinter(self._hprinter, bytes(self._buf))
            win32print.EndPagePrinter(self._hprinter)
            win32print.EndDocPrinter(self._hprinter)
        except Exception:
            try: win32print.EndDocPrinter(self._hprinter)
            except Exception: pass
            raise
        self._buf.clear()

    def close(self):
        try: self.flush()
        except Exception: pass
        try:
            import win32print
            if self._hprinter: win32print.ClosePrinter(self._hprinter)
        except Exception: pass
        self.is_open = False
        self._hprinter = None


class BaseFiscalDriver(ABC):
    def __init__(self, config):
        self.config = config
        self._serial = None

    def _open_port(self):
        port = self.config.port or "COM1"
        if _is_windows_spooler(port):
            printer_name = getattr(self.config, "printer_name", "") or ""
            return WinSpoolerConnection(printer_name, timeout=int(self.config.timeout or 10))
        return serial.Serial(port=port, baudrate=int(self.config.baud_rate or 9600), bytesize=int(self.config.data_bits or 8), parity=str(self.config.parity or "N"), stopbits=int(self.config.stop_bits or 1), timeout=float(self.config.timeout or 10))

    def _close_port(self, conn):
        try:
            if conn and getattr(conn, "is_open", False):
                conn.close()
        except Exception: pass

    def check_connection(self) -> Tuple[bool, str]:
        try:
            conn = self._open_port()
            self._close_port(conn)
            if _is_windows_spooler(self.config.port):
                return True, f"Impresora Windows '{self.config.printer_name}' OK"
            return True, f"Puerto {self.config.port} OK"
        except serial.SerialException as e:
            return False, f"No se puede abrir {self.config.port}: {e}"
        except RuntimeError as e:
            return False, str(e)

    @staticmethod
    def _fmt_amount(value, decimals=2): return f"{value:.{decimals}f}"
    @staticmethod
    def _fmt_date(iso):
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception: return iso[:19]
    @staticmethod
    def _truncate(text, max_len): return (text or "")[:max_len]

    @abstractmethod
    def print_fiscal_invoice(self, payload): pass

    def print_text(self, text):
        conn = None
        try:
            conn = self._open_port()
            encoding = self.config.encoding or "latin-1"
            esc_init = b"\x1b\x40"
            body = (text + "\n\n\n").encode(encoding, errors="replace")
            esc_cut = b"\x1d\x56\x01"
            conn.write(esc_init + body + esc_cut)
            conn.flush()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)

    def print_test(self): return {"success": True, "message": "Test no implementado"}
    def get_fiscal_status(self): return {"success": False, "error": "No soportado"}
    def print_report_x(self): return {"success": False, "error": "No soportado"}
    def print_report_z(self): return {"success": False, "error": "No soportado"}
    def cancel_document(self): return {"success": False, "error": "No soportado"}
