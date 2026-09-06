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

    def print_text(self, text: str, logo_url: str = "") -> dict:
        """
        Imprime texto plano (no fiscal) — ticket simple / comprobante informativo.
        Útil para impresoras térmicas genéricas o texto no fiscal en fiscales que
        lo soporten. Envía comandos ESC/POS de inicialización + (opcional) el logo
        como imagen raster + el texto + corte de papel.
        Retorna: {"success": bool, "error": str}
        """
        conn = None
        try:
            conn = self._open_port()
            encoding = self.config.encoding or "latin-1"
            esc_init = b"\x1b\x40"
            body = (text + "\n\n\n").encode(encoding, errors="replace")
            esc_cut = b"\x1d\x56\x01"
            # Logo opcional (raster ESC/POS GS v 0) — se imprime centrado antes del texto
            logo_data = b""
            if logo_url:
                try:
                    logo_data = self._build_logo_raster(logo_url)
                except Exception as e:
                    log.warning(f"No se pudo cargar el logo ({logo_url}): {e}")
            data = esc_init + logo_data + body + esc_cut
            conn.write(data)
            conn.flush()
            return {"success": True}
        except Exception as e:
            log.error(f"print_text error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)

    def _build_logo_raster(self, url: str) -> bytes:
        """Descarga la imagen del logo y la convierte a raster ESC/POS (GS v 0).
        La imagen se redimensiona para caber en papel 80mm (máx 576 dots de ancho)
        y se umbraliza a 1-bit (blanco/negro). Retorna los bytes ESC/POS listos
        para enviar a la impresora, ya envueltos en alineación centrada."""
        import urllib.request
        from io import BytesIO
        from PIL import Image

        max_width = 576  # 80mm a ~203 DPI
        max_height = 240
        req = urllib.request.Request(url, headers={"User-Agent": "VenPOS-Bridge"})
        with urllib.request.urlopen(req, timeout=10) as r:
            img_data = r.read()
        img = Image.open(BytesIO(img_data)).convert("L")
        # Redimensionar manteniendo aspect ratio
        w, h = img.size
        if w > max_width:
            ratio = max_width / w
            img = img.resize((max_width, int(h * ratio)), Image.LANCZOS)
        w, h = img.size
        if h > max_height:
            ratio = max_height / h
            img = img.resize((int(w * ratio), max_height), Image.LANCZOS)
        w, h = img.size
        # Padding del ancho a múltiplo de 8 (raster ESC/POS usa 8 pixels por byte)
        width_bytes = (w + 7) // 8
        padded_w = width_bytes * 8
        if padded_w != w:
            img = img.resize((padded_w, h))
            w = padded_w
        # Umbral a 1-bit: <128 = negro (bit 1), >=128 = blanco (bit 0)
        pixels = img.load()
        raster = bytearray()
        for y in range(h):
            for x_byte in range(width_bytes):
                byte = 0
                for bit in range(8):
                    px = x_byte * 8 + bit
                    if px < w and pixels[px, y] < 128:
                        byte |= (0x80 >> bit)
                raster.append(byte)
        # GS v 0 m xL xH yL yH d1..dk
        m = 0
        xL = width_bytes & 0xFF
        xH = (width_bytes >> 8) & 0xFF
        yL = h & 0xFF
        yH = (h >> 8) & 0xFF
        cmd = b"\x1d\x76\x30" + bytes([m, xL, xH, yL, yH]) + bytes(raster)
        # Centrar el logo y dejar una línea en blanco después
        return b"\x1ba\x01" + cmd + b"\x1ba\x00\n"

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