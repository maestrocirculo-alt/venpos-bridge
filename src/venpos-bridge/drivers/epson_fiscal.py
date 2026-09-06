"""
Driver EPSON Fiscal — TM-T20X Fiscal, TM-T88VI Fiscal.
Protocolo: ESC/POS extendido con comandos fiscales Venezuela.
"""

import time
import logging
from .base import BaseFiscalDriver

log = logging.getLogger("EPSON_Fiscal")

ESC = b'\x1b'
GS  = b'\x1d'


class EpsonFiscalDriver(BaseFiscalDriver):

    def _write_text(self, conn, text: str, encoding: str = "latin-1"):
        conn.write(text.encode(encoding, errors="replace"))
        conn.flush()
        time.sleep(0.05)

    def _cmd_fiscal(self, conn, code: bytes, data: bytes = b"") -> bytes:
        packet = ESC + b'\x46' + code + data + b'\r'
        conn.write(packet)
        conn.flush()
        time.sleep(0.2)
        resp = b""
        while conn.in_waiting:
            resp += conn.read(conn.in_waiting)
            time.sleep(0.05)
        return resp

    def print_fiscal_invoice(self, payload: dict) -> dict:
        conn = None
        try:
            conn = self._open_port()
            emisor = payload.get("emisor", {})
            receptor = payload.get("receptor", {})
            items = payload.get("items", [])
            pagos = payload.get("pagos", [])

            # Inicializar
            conn.write(ESC + b'\x40')  # ESC @ — reset
            time.sleep(0.3)

            # Encabezado emisor (modo texto antes del documento fiscal)
            self._write_text(conn, "\x1b\x61\x01")  # centrar
            self._write_text(conn, f"{emisor.get('razon_social', '')[:40]}\n")
            self._write_text(conn, f"RIF: {emisor.get('rif', '')}\n")
            self._write_text(conn, f"{emisor.get('direccion', '')[:40]}\n")
            self._write_text(conn, "\x1b\x61\x00")  # izquierda

            # Abrir documento fiscal
            tipo = b'\x46' if "factura" in payload.get("tipo_documento", "factura") else b'\x54'
            r = self._cmd_fiscal(conn, b'\x01' + tipo,
                                 receptor.get("nombre", "CONSUMIDOR FINAL")[:30].encode("latin-1") +
                                 b'\x1c' +
                                 receptor.get("rif", "V-00000000")[:12].encode("latin-1"))
            if r and r[0] != 0x06:
                return {"success": False, "error": f"EPSON: error apertura 0x{r.hex()}"}

            # Ítems
            for item in items:
                desc = self._truncate(item.get("description", "Producto"), 20)
                qty = float(item.get("quantity", 1))
                price = float(item.get("unit_price", 0))
                tax = int(item.get("tax_rate", 16))
                item_data = f"{desc}\x1c{qty:.3f}\x1c{price:.4f}\x1c{tax:02d}".encode("latin-1")
                r = self._cmd_fiscal(conn, b'\x02', item_data)

            # Totalizar
            total = float(payload.get("total", 0))
            r = self._cmd_fiscal(conn, b'\x03', f"{total:.4f}".encode("latin-1"))
            if r and r[0] != 0x06:
                return {"success": False, "error": f"EPSON: error totalización"}

            # Pagos
            for pago in pagos:
                method_code = b'\x45' if "tarjeta" in pago.get("method", "") else b'\x43'
                amt = float(pago.get("amount", 0))
                self._cmd_fiscal(conn, method_code, f"{amt:.4f}".encode("latin-1"))

            # Cerrar documento
            r = self._cmd_fiscal(conn, b'\x04')
            if r and r[0] != 0x06:
                return {"success": False, "error": f"EPSON: error cierre"}

            # Corte de papel
            conn.write(GS + b'\x56\x01')
            conn.flush()

            return {
                "success": True,
                "numero_control": payload.get("numero_control", ""),
                "numero_factura": payload.get("numero_factura", ""),
            }
        except Exception as e:
            log.error(f"EPSON error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)