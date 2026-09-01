"""
Driver base para todas las impresoras fiscales.
Cada driver concreto hereda de esta clase e implementa los métodos abstractos.

Incluye la interfaz completa de operaciones fiscales SENIAT:
  - Emisión de factura / nota de entrega / ticket
  - Reporte X (lectura parcial) y Cierre Z (cierre de jornada)
  - Cancelar/abortar documento fiscal abierto (recuperación tras corte)
  - Consulta de estado fiscal detallado (papel, documento abierto, Z pendiente)
"""

import serial
import logging
from abc import ABC, abstractmethod
from typing import Tuple

log = logging.getLogger("FiscalDriver")


def _is_windows_spooler(port: str) -> bool:
    """Detecta si el puerto corresponde a una impresora USB de Windows.
    Las impresoras térmicas USB en Windows NO son puertos serie: se instalan
    como impresoras del sistema y se imprimen vía el spooler (win32print),
    no con pyserial. Cualquier puerto que empiece con USB, o los valores
    explícitos SPOOLER / WINDOWS, usan esta ruta."""
    if not port:
        return False
    p = str(port).upper()
    return p.startswith("USB") or p in ("SPOOLER", "WINDOWS", "WINSPOOL")


class WinSpoolerConnection:
    """Imita la interfaz de serial.Serial (write / flush / close / is_open)
    pero envía los bytes crudos (RAW) al spooler de Windows por el nombre
    de la impresora instalada. así se pueden imprimir tickets ESC/POS a
    impresoras térmicas conectadas por USB.

    Requiere pywin32 (win32print). En Linux/Mac no se usa (el puerto no
    será USB/Windows)."""

    def __init__(self, printer_name: str, timeout: int = 10):
        self.printer_name = printer_name
        self.timeout = timeout
        self.is_open = False
        self._buf = bytearray()
        self._hprinter = None
        self._open()

    def _open(self):
        try:
            import win32print  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "win32print no disponible. Instala pywin32: pip install pywin32"
            ) from e
        # Validar que la impresora exista en Windows
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        available = [p[2] for p in win32print.EnumPrinters(flags)]
        if not self.printer_name:
            raise RuntimeError(
                "Falta el nombre de la impresora de Windows. Instala la impresora térmica en Windows y escribe su nombre exacto en la configuración. Impresoras detectadas: " + (", ".join(available) or "(ninguna)")
            )
        if self.printer_name not in available:
            raise RuntimeError(
                f"La impresora '{self.printer_name}' no existe en Windows. "
                f"Impresoras detectadas: {', '.join(available) or '(ninguna)'}"
            )
        self._hprinter = win32print.OpenPrinter(self.printer_name)
        self.is_open = True
        log.info(f"Spooler de Windows conectado a '{self.printer_name}'")

    def write(self, data: bytes):
        if isinstance(data, str):
            data = data.encode("latin-1", errors="replace")
        self._buf.extend(data)

    def flush(self):
        if not self._buf:
            return
        import win32print  # type: ignore
        job = win32print.StartDocPrinter(self._hprinter, 1, ("VenPOS Ticket", None, "RAW"))
        try:
            win32print.StartPagePrinter(self._hprinter)
            win32print.WritePrinter(self._hprinter, bytes(self._buf))
            win32print.EndPagePrinter(self._hprinter)
            win32print.EndDocPrinter(self._hprinter)
        except Exception:
            try:
                win32print.EndDocPrinter(self._hprinter)
            except Exception:
                pass
            raise
        self._buf.clear()

    def close(self):
        try:
            self.flush()
        except Exception:
            pass
        try:
            import win32print  # type: ignore
            if self._hprinter:
                win32print.ClosePrinter(self._hprinter)
        except Exception:
            pass
        self.is_open = False
        self._hprinter = None


class BaseFiscalDriver(ABC):
    """Clase base para todos los drivers de impresoras fiscales venezolanas."""

    def __init__(self, config):
        self.config = config
        self._serial: serial.Serial | None = None

    # ── Conexión serial ───────────────────────────────────────────────────────

    def _open_port(self):
        """Abre el puerto según la configuración.
        Si el puerto es USB / SPOOLER / WINDOWS, usa el spooler de Windows
        (win32print) con el nombre de la impresora configurada. Si no,
        usa pyserial como antes (COM1, /dev/ttyUSB0, etc.)."""
        port = self.config.port or "COM1"
        if _is_windows_spooler(port):
            printer_name = getattr(self.config, "printer_name", "") or ""
            conn = WinSpoolerConnection(printer_name, timeout=int(self.config.timeout or 10))
            log.info(f"Spooler de Windows '{printer_name}' abierto")
            return conn
        conn = serial.Serial(
            port=port,
            baudrate=int(self.config.baud_rate or 9600),
            bytesize=int(self.config.data_bits or 8),
            parity=str(self.config.parity or "N"),
            stopbits=int(self.config.stop_bits or 1),
            timeout=float(self.config.timeout or 10),
        )
        log.info(f"Puerto {port} abierto a {self.config.baud_rate} bps")
        return conn

    def _close_port(self, conn):
        try:
            if conn and getattr(conn, "is_open", False):
                conn.close()
        except Exception:
            pass

    def check_connection(self) -> Tuple[bool, str]:
        """Verifica que el puerto esté disponible (conexión física)."""
        try:
            conn = self._open_port()
            self._close_port(conn)
            if _is_windows_spooler(self.config.port):
                return True, f"Impresora Windows '{self.config.printer_name}' OK"
            return True, f"Puerto {self.config.port} OK"
        except serial.SerialException as e:
            return False, f"No se puede abrir {self.config.port}: {e}"
        except RuntimeError as e:
            # Errores del spooler de Windows (impresora no existe, pywin32 ausente)
            return False, str(e)

    # ── Helpers de formato ────────────────────────────────────────────────────

    @staticmethod
    def _fmt_amount(value: float, decimals: int = 2) -> str:
        return f"{value:.{decimals}f}"

    @staticmethod
    def _fmt_date(iso: str) -> str:
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            return iso[:19]

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        return (text or "")[:max_len]

    # ── Interfaz pública abstracta ────────────────────────────────────────────

    @abstractmethod
    def print_fiscal_invoice(self, payload: dict) -> dict:
        """
        Imprime una factura fiscal.
        Retorna: {"success": bool, "numero_control": str, "numero_factura": str, "error": str, "code": str}
        """

    def print_text(self, text: str) -> dict:
        """
        Imprime texto plano (no fiscal) — ticket simple / comprobante informativo.
        Útil para impresoras térmicas genéricas o texto no fiscal en fiscales que
        lo soporten. Envía comandos ESC/POS de inicialización + el texto + corte
        de papel, por la conexión serial o el spooler de Windows (USB).
        Retorna: {"success": bool, "error": str}
        """
        conn = None
        try:
            conn = self._open_port()
            encoding = self.config.encoding or "latin-1"
            # ESC @ — inicializa la impresora (reseta modo, alineación, etc.)
            # El texto crudo tal cual (latin-1)
            # GS V 1 — corte de papel total al final
            esc_init = b"\x1b\x40"
            body = (text + "\n\n\n").encode(encoding, errors="replace")
            esc_cut = b"\x1d\x56\x01"
            data = esc_init + body + esc_cut
            conn.write(data)
            conn.flush()
            return {"success": True}
        except Exception as e:
            log.error(f"print_text error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)

    def print_test(self) -> dict:
        return {"success": True, "message": "Test no implementado para este driver"}

    # ── Operaciones de mantenimiento fiscal (SENIAT) ───────────────────────────
    # Cada driver concreto puede sobrescribir estos métodos con los comandos
    # específicos de su firmware. La implementación base devuelve "no soportado"
    # para que la app lo indique claramente en lugar de fallar en silencio.

    def get_fiscal_status(self) -> dict:
        """
        Consulta el estado fiscal real de la impresora.
        Retorna: {
          "success": bool,
          "paper_ok": bool,        # hay papel
          "doc_open": bool,        # hay documento fiscal abierto (recuperar tras corte)
          "z_pending": bool,       # requiere Cierre Z (bloqueo a las 24h)
          "printer_ready": bool,   # puede emitir facturas ahora
          "raw": str, "error": str
        }
        """
        return {
            "success": False,
            "paper_ok": None,
            "doc_open": None,
            "z_pending": None,
            "printer_ready": None,
            "error": "Consulta de estado fiscal no soportada por este driver",
        }

    def print_report_x(self) -> dict:
        """Emitir Reporte X (lectura parcial — no cierra la jornada)."""
        return {"success": False, "error": "Reporte X no soportado por este driver"}

    def print_report_z(self) -> dict:
        """
        Emitir Cierre Z (cierre de jornada fiscal — irreversible).
        Retorna: {"success": bool, "z_number": str, "error": str}
        """
        return {"success": False, "error": "Cierre Z no soportado por este driver"}

    def cancel_document(self) -> dict:
        """Cancelar/abortar documento fiscal abierto (recuperación tras falla)."""
        return {"success": False, "error": "Cancelación de documento no soportada por este driver"}