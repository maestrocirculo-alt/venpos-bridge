"""
Driver Datasym — DS9300, DS9200.
Protocolo: comandos ASCII con prefijo '@' y checksum.
"""

import time
import logging
from .base import BaseFiscalDriver

log = logging.getLogger("Datasym")


class DatasymDriver(BaseFiscalDriver):

    def _cmd(self, conn, cmd: str) -> str:
        packet = f"@{cmd}\r\n"
        conn.write(packet.encode("latin-1"))
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

            # Abrir factura
            r = self._cmd(conn, f"OPEN_INV;{receptor.get('nombre','CF')[:30]};{receptor.get('rif','V-0')[:12]}")
            if "ERR" in r:
                return {"success": False, "error": f"Datasym apertura: {r}"}

            # Ítems
            for item in items:
                desc = self._truncate(item.get("description", "Producto"), 20)
                qty  = float(item.get("quantity", 1))
                price = float(item.get("unit_price", 0))
                tax  = int(item.get("tax_rate", 16))
                self._cmd(conn, f"ADD_ITEM;{desc};{qty:.3f};{price:.4f};{tax}")

            # Total y pago
            total = float(payload.get("total", 0))
            self._cmd(conn, f"TOTAL;{total:.4f}")
            for pago in pagos:
                self._cmd(conn, f"PAYMENT;{pago.get('method','cash_usd')};{float(pago.get('amount',0)):.4f}")

            # Cerrar
            r = self._cmd(conn, "CLOSE_INV")
            if "ERR" in r:
                return {"success": False, "error": f"Datasym cierre: {r}"}

            return {
                "success": True,
                "numero_control": payload.get("numero_control", ""),
                "numero_factura": payload.get("numero_factura", ""),
            }
        except Exception as e:
            log.error(f"Datasym error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)