import time, struct, logging
from .base import BaseFiscalDriver
log = logging.getLogger("Bematech")
ESC=b'\x1b'; ACK=0x06
CMD_OPEN_INVOICE=b'\x41'; CMD_ADD_ITEM=b'\x45'; CMD_CLOSE_INVOICE=b'\x46'; CMD_PAYMENT=b'\x47'; CMD_END_INVOICE=b'\x48'; CMD_STATUS=b'\x4C'

class BematechDriver(BaseFiscalDriver):
    def _send_raw(self, conn, cmd, data=b""):
        conn.write(ESC+cmd+data); conn.flush(); time.sleep(0.2)
        resp=b""; deadline=time.time()+float(self.config.timeout or 10)
        while time.time()<deadline:
            if conn.in_waiting:
                resp+=conn.read(conn.in_waiting)
                if len(resp)>=1: break
            time.sleep(0.05)
        return resp
    def _is_ok(self, resp): return len(resp)>0 and resp[0]==ACK
    def print_fiscal_invoice(self, payload):
        conn=None
        try:
            conn=self._open_port()
            receptor=payload.get("receptor",{}); items=payload.get("items",[]); pagos=payload.get("pagos",[])
            nombre=self._truncate(receptor.get("nombre","CONSUMIDOR FINAL"),30); rif=self._truncate(receptor.get("rif","V00000000"),14)
            r=self._send_raw(conn,CMD_OPEN_INVOICE,f"{nombre}\x1c{rif}\x1c\x1c".encode("latin-1"))
            if not self._is_ok(r): return {"success":False,"error":"Apertura Bematech"}
            for item in items:
                desc=self._truncate(item.get("description","Producto"),20).ljust(20)
                r=self._send_raw(conn,CMD_ADD_ITEM,f"{desc}{int(item.get('tax_rate',16)):02d}{float(item.get('quantity',1)):07.3f}{float(item.get('unit_price',0)):08.2f}".encode("latin-1"))
                if not self._is_ok(r): log.warning(f"Ítem rechazado: {desc}")
            r=self._send_raw(conn,CMD_CLOSE_INVOICE,f"{float(payload.get('total',0)):014.2f}".encode("latin-1"))
            if not self._is_ok(r): return {"success":False,"error":"Totalizar Bematech"}
            for pago in pagos:
                self._send_raw(conn,CMD_PAYMENT,f"{_bematech_payment(pago.get('method','cash_usd')).ljust(16)}{float(pago.get('amount',0)):014.2f}".encode("latin-1"))
            r=self._send_raw(conn,CMD_END_INVOICE)
            return {"success":self._is_ok(r),"numero_control":payload.get("numero_control",""),"numero_factura":payload.get("numero_factura","")}
        except Exception as e:
            return {"success":False,"error":str(e)}
        finally:
            self._close_port(conn)
def _bematech_payment(method):
    MAP={"cash_usd":"DINERO","cash_ves":"DINERO","pago_movil":"CHEQUE","tarjeta":"TARJETA CREDITO","transferencia":"CHEQUE","zelle":"TRANSFERENCIA"}
    return MAP.get(method,"DINERO")
