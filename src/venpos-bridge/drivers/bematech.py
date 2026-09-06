"""
Driver Bematech — Impresoras MP-4200 TH, MP-2500 TH, MP-F4000.
Protocolo: comandos binarios ESC/BEMATECH via serial.

Referencia: Manual Bematech MP-4200 TH FISCAL — protocolo de comunicación.
"""

import time
import logging
import struct
from .base import BaseFiscalDriver

log = logging.getLogger("Bematech")

# Constantes del protocolo Bematech
ESC = b'\x1b'
STX = b'\x02'
ACK = 0x06
NAK = 0x15

CMD_OPEN_INVOICE        = b'\x41'   # A — Abrir cupón/factura
CMD_ADD_ITEM            = b'\x45'   # E — Añadir ítem
CMD_CLOSE_INVOICE       = b'\x46'   # F — Totalizar
CMD_PAYMENT             = b'\x47'   # G — Forma de pago
CMD_END_INVOICE         = b'\x48'   # H — Cerrar cupón
CMD_STATUS              = b'\x4C'   # L — Leer estado


class BematechDriver(BaseFiscalDriver):

    def _send_raw(self, conn, cmd: bytes, data: bytes = b"") -> bytes:
        """Envía comando en formato Bematech y espera ACK."""
        packet = ESC + cmd + data
        conn.write(packet)
        conn.flush()
        time.sleep(0.2)
        resp = b""
        deadline = time.time() + float(self.config.timeout or 10)
        while time.time() < deadline:
            if conn.in_waiting:
                resp += conn.read(conn.in_waiting)
                if len(resp) >= 1:
                    break
            time.sleep(0.05)
        log.debug(f"CMD: {cmd.hex()}  DATA: {data!r}  RESP: {resp.hex()}")
        return resp

    def _is_ok(self, resp: bytes) -> bool:
        return len(resp) > 0 and resp[0] == ACK

    def print_fiscal_invoice(self, payload: dict) -> dict:
        conn = None
        try:
            conn = self._open_port()
            receptor = payload.get("receptor", {})
            items = payload.get("items", [])
            pagos = payload.get("pagos", [])

            # 1. Abrir cupón — datos del cliente
            nombre = self._truncate(receptor.get("nombre", "CONSUMIDOR FINAL"), 30)
            rif = self._truncate(receptor.get("rif", "V00000000"), 14)
            open_data = f"{nombre}\x1c{rif}\x1c\x1c".encode("latin-1")
            r = self._send_raw(conn, CMD_OPEN_INVOICE, open_data)
            if not self._is_ok(r):
                return {"success": False, "error": "Error al abrir cupón Bematech"}

            # 2. Ítems
            for item in items:
                desc = self._truncate(item.get("description", "Producto"), 20).ljust(20)
                qty = float(item.get("quantity", 1))
                price = float(item.get("unit_price", 0))
                tax_rate = int(item.get("tax_rate", 16))
                # Bematech: descripción(20) + código_alícuota(2) + cantidad(7) + precio(8)
                alq = f"{tax_rate:02d}"
                item_str = f"{desc}{alq}{qty:07.3f}{price:08.2f}"
                r = self._send_raw(conn, CMD_ADD_ITEM, item_str.encode("latin-1"))
                if not self._is_ok(r):
                    log.warning(f"Ítem rechazado por Bematech: {desc}")

            # 3. Totalizar
            total = float(payload.get("total", 0))
            r = self._send_raw(conn, CMD_CLOSE_INVOICE, f"{total:014.2f}".encode("latin-1"))
            if not self._is_ok(r):
                return {"success": False, "error": "Error al totalizar en Bematech"}

            # 4. Formas de pago
            for pago in pagos:
                label = _bematech_payment(pago.get("method", "cash_usd"))
                amt = float(pago.get("amount", 0))
                pay_data = f"{label.ljust(16)}{amt:014.2f}".encode("latin-1")
                self._send_raw(conn, CMD_PAYMENT, pay_data)

            # 5. Cerrar cupón
            r = self._send_raw(conn, CMD_END_INVOICE)
            if not self._is_ok(r):
                return {"success": False, "error": "Error al cerrar cupón Bematech"}

            return {
                "success": True,
                "numero_control": payload.get("numero_control", ""),
                "numero_factura": payload.get("numero_factura", ""),
            }

        except Exception as e:
            log.error(f"Bematech error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)

    def print_test(self) -> dict:
        conn = None
        try:
            conn = self._open_port()
            r = self._send_raw(conn, CMD_STATUS)
            if r:
                return {"success": True, "message": f"Bematech responde: 0x{r.hex()}"}
            return {"success": False, "error": "Sin respuesta"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)


def _bematech_payment(method: str) -> str:
    MAP = {
        "cash_usd": "DINERO",    "cash_ves": "DINERO",
        "pago_movil": "CHEQUE",  "tarjeta": "TARJETA CREDITO",
        "transferencia": "CHEQUE", "zelle": "TRANSFERENCIA",
    }
    return MAP.get(method, "DINERO")