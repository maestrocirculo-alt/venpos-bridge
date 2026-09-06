"""
Driver NCR — Impresoras 2008, 2010, 7197.
Protocolo: similar a Epson/ESC-POS con extensiones fiscales NCR.
"""

import time
import logging
from .base import BaseFiscalDriver

log = logging.getLogger("NCR")

ESC = b'\x1b'
LF  = b'\x0a'
CR  = b'\x0d'


class NCRDriver(BaseFiscalDriver):

    def _write(self, conn, data: bytes):
        conn.write(data)
        conn.flush()
        time.sleep(0.1)

    def _cmd(self, conn, code: str, params: str = "") -> str:
        line = f"\x02{code}{params}\x03\r\n"
        conn.write(line.encode("latin-1"))
        conn.flush()
        time.sleep(0.2)
        resp = b""
        while conn.in_waiting:
            resp += conn.read(conn.in_waiting)
            time.sleep(0.05)
        return resp.decode("latin-1", errors="replace").strip()

    def print_fiscal_invoice(self, payload: dict) -> dict:
        conn = None
        try:
            conn = self._open_port()
            receptor = payload.get("receptor", {})
            items = payload.get("items", [])
            pagos = payload.get("pagos", [])

            # Abrir documento
            tipo = "F" if "factura" in payload.get("tipo_documento", "factura") else "T"
            r = self._cmd(conn, f"DIF{tipo}")
            if "ERR" in r.upper():
                return {"success": False, "error": f"NCR: error al abrir — {r}"}

            # Datos cliente
            self._cmd(conn, "DCN", receptor.get("nombre", "CONSUMIDOR FINAL")[:30])
            self._cmd(conn, "DCR", receptor.get("rif", "V-00000000")[:12])

            # Ítems
            for item in items:
                desc = self._truncate(item.get("description", "Producto"), 20)
                qty  = float(item.get("quantity", 1))
                price = float(item.get("unit_price", 0))
                tax  = int(item.get("tax_rate", 16))
                self._cmd(conn, "VIT", f"{desc}|{qty:.3f}|{price:.4f}|{tax}")

            # Totales
            total = float(payload.get("total", 0))
            self._cmd(conn, "SUB", f"{total:.4f}")

            # Pagos
            for pago in pagos:
                method = pago.get("method", "cash_usd")
                amt = float(pago.get("amount", 0))
                self._cmd(conn, "PAG", f"{method}|{amt:.4f}")

            # Cerrar
            r = self._cmd(conn, "CIE")
            if "ERR" in r.upper():
                return {"success": False, "error": f"NCR: error al cerrar — {r}"}

            return {
                "success": True,
                "numero_control": payload.get("numero_control", ""),
                "numero_factura": payload.get("numero_factura", ""),
            }
        except Exception as e:
            log.error(f"NCR error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)

    def print_test(self) -> dict:
        conn = None
        try:
            conn = self._open_port()
            r = self._cmd(conn, "STS")
            return {"success": True, "message": f"NCR status: {r}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)