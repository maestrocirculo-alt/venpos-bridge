"""
Driver ACLAS — Impresoras PP9A, PP7A, PP5A.
Protocolo: comandos ASCII con separador ';' y checksum XOR.
"""

import time
import logging
from .base import BaseFiscalDriver

log = logging.getLogger("ACLAS")


class ACLASDriver(BaseFiscalDriver):

    def _checksum(self, data: str) -> str:
        cs = 0
        for c in data:
            cs ^= ord(c)
        return f"{cs:02X}"

    def _cmd(self, conn, code: str, *params) -> str:
        body = code + ";" + ";".join(str(p) for p in params)
        full = f"\x02{body};{self._checksum(body)}\x03"
        conn.write(full.encode("latin-1"))
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
            r = self._cmd(conn, "OF",
                          receptor.get("nombre", "CONSUMIDOR FINAL")[:30],
                          receptor.get("rif", "V-00000000")[:12],
                          receptor.get("direccion", "")[:40])
            if r.startswith("E"):
                return {"success": False, "error": f"ACLAS error apertura: {r}"}

            # Ítems
            for item in items:
                r = self._cmd(conn, "VI",
                              self._truncate(item.get("description", "Producto"), 20),
                              f"{float(item.get('quantity', 1)):.3f}",
                              f"{float(item.get('unit_price', 0)):.4f}",
                              str(int(item.get("tax_rate", 16))))
                if r.startswith("E"):
                    log.warning(f"ACLAS: ítem rechazado — {r}")

            # Descuento
            desc = float(payload.get("descuento", 0))
            if desc > 0:
                self._cmd(conn, "DG", f"{desc:.4f}")

            # Totalizar + pagos
            total = float(payload.get("total", 0))
            r = self._cmd(conn, "TT", f"{total:.4f}")
            if r.startswith("E"):
                return {"success": False, "error": f"ACLAS error totalización: {r}"}

            for pago in pagos:
                self._cmd(conn, "FP",
                          _aclas_payment(pago.get("method", "cash_usd")),
                          f"{float(pago.get('amount', 0)):.4f}")

            # Cerrar
            r = self._cmd(conn, "CF")
            if r.startswith("E"):
                return {"success": False, "error": f"ACLAS error cierre: {r}"}

            return {
                "success": True,
                "numero_control": payload.get("numero_control", ""),
                "numero_factura": payload.get("numero_factura", ""),
            }
        except Exception as e:
            log.error(f"ACLAS error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)


def _aclas_payment(method: str) -> str:
    MAP = {"cash_usd": "E", "cash_ves": "E", "tarjeta": "T",
           "transferencia": "C", "pago_movil": "M", "zelle": "Z"}
    return MAP.get(method, "E")