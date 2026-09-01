"""
Driver Bematech — Impresoras MP-4200 TH, MP-2500 TH, MP-F4000.
Protocolo: comandos binarios ESC/BEMATECH via serial.
"""
import time, logging
from .base import BaseFiscalDriver
log = logging.getLogger("Bematech")
ESC = b'\x1b'; STX = b'\x02'; ACK = 0x06; NAK = 0x15
CMD_OPEN_INVOICE = b'\x41'; CMD_ADD_ITEM = b'\x45'; CMD_CLOSE_INVOICE = b'\x46'
CMD_PAYMENT = b'\x47'; CMD_END_INVOICE = b'\x48'; CMD_STATUS = b'\x4c'

class BematechDriver(BaseFiscalDriver):
    def _send_raw(self, conn, cmd, data=b""):
        conn.write(ESC + cmd + data); conn.flush(); time.sleep(0.2)
        resp = b""; deadline = time.time() + float(self.config.timeout or 10)
        while time.time() < deadline:
            if conn.in_waiting: resp += conn.read(conn.in_waiting)
            if len(resp) >= 1: break
            time.sleep(0.05)
        return resp
    def _is_ok(self, resp): return len(resp) > 0 and resp[0] == ACK
    def print_fiscal_invoice(self, payload):
        conn = None
        try:
            conn = self._open_port()
            receptor = payload.get("receptor", {}); items = payload.get("items", []); pagos = payload.get("pagos", [])
            nombre = self._truncate(receptor.get("nombre", "CONSUMIDOR FINAL"), 30)
            rif = self._truncate(receptor.get("rif", "V00000000"), 14)
            r = self._send_raw(conn, CMD_OPEN_INVOICE, f"{nombre}\x1c{rif}\x1c\x1c".encode("latin-1"))
            if not self._is_ok(r): return {"success": False, "error": "Error al abrir cupón Bematech"}
            for item in items:
                desc = self._truncate(item.get("description", "Producto"), 20).ljust(20)
                qty = float(item.get("quantity", 1)); price = float(item.get("unit_price", 0)); tax_rate = int(item.get("tax_rate", 16))
                r = self._send_raw(conn, CMD_ADD_ITEM, f"{desc}{tax_rate:02d}{qty:07.3f}{price:08.2f}".encode("latin-1"))
                if not self._is_ok(r): log.warning(f"Ítem rechazado por Bematech: {desc}")
            total = float(payload.get("total", 0))
            r = self._send_raw(conn, CMD_CLOSE_INVOICE, f"{total:014.2f}".encode("latin-1"))
            if not self._is_ok(r): return {"success": False, "error": "Error al totalizar en Bematech"}
            for pago in pagos:
                label = _bematech_payment(pago.get("method", "cash_usd")); amt = float(pago.get("amount", 0))
                self._send_raw(conn, CMD_PAYMENT, f"{label.ljust(16)}{amt:014.2f}".encode("latin-1"))
            r = self._send_raw(conn, CMD_END_INVOICE)
            if not self._is_ok(r): return {"success": False, "error": "Error al cerrar cupón Bematech"}
            return {"success": True, "numero_control": payload.get("numero_control", ""), "numero_factura": payload.get("numero_factura", "")}
        except Exception as e:
            log.error(f"Bematech error: {e}", exc_info=True); return {"success": False, "error": str(e)}
        finally: self._close_port(conn)
    def print_test(self):
        conn = None
        try:
            conn = self._open_port(); r = self._send_raw(conn, CMD_STATUS)
            if r: return {"success": True, "message": f"Bematech responde: 0x{r.hex()}"}
            return {"success": False, "error": "Sin respuesta"}
        except Exception as e: return {"success": False, "error": str(e)}
        finally: self._close_port(conn)

def _bematech_payment(method):
    MAP = {"cash_usd": "DINERO", "cash_ves": "DINERO", "pago_movil": "CHEQUE",
        "tarjeta": "TARJETA CREDITO", "transferencia": "CHEQUE", "zelle": "TRANSFERENCIA"}
    return MAP.get(method, "DINERO")
