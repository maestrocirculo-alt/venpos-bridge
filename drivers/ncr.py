import time, logging
from .base import BaseFiscalDriver
log=logging.getLogger("NCR")
ESC=b'\x1b'
class NCRDriver(BaseFiscalDriver):
    def _cmd(self, conn, code, params=""):
        conn.write(f"\x02{code}{params}\x03\r\n".encode("latin-1")); conn.flush(); time.sleep(0.2)
        resp=b""
        while conn.in_waiting:
            resp+=conn.read(conn.in_waiting); time.sleep(0.05)
        return resp.decode("latin-1",errors="replace").strip()
    def print_fiscal_invoice(self, payload):
        conn=None
        try:
            conn=self._open_port()
            receptor=payload.get("receptor",{}); items=payload.get("items",[]); pagos=payload.get("pagos",[])
            tipo="F" if "factura" in payload.get("tipo_documento","factura") else "T"
            r=self._cmd(conn,f"DIF{tipo}")
            if "ERR" in r.upper(): return {"success":False,"error":f"NCR apertura: {r}"}
            self._cmd(conn,"DCN",receptor.get("nombre","CONSUMIDOR FINAL")[:30])
            self._cmd(conn,"DCR",receptor.get("rif","V-00000000")[:12])
            for item in items:
                self._cmd(conn,"VIT",f"{self._truncate(item.get('description','Producto'),20)}|{float(item.get('quantity',1)):.3f}|{float(item.get('unit_price',0)):.4f}|{int(item.get('tax_rate',16))}")
            self._cmd(conn,"SUB",f"{float(payload.get('total',0)):.4f}")
            for pago in pagos:
                self._cmd(conn,"PAG",f"{pago.get('method','cash_usd')}|{float(pago.get('amount',0)):.4f}")
            r=self._cmd(conn,"CIE")
            if "ERR" in r.upper(): return {"success":False,"error":f"NCR cierre: {r}"}
            return {"success":True,"numero_control":payload.get("numero_control",""),"numero_factura":payload.get("numero_factura","")}
        except Exception as e:
                       return {"success":False,"error":str(e)}
        finally:
            self._close_port(conn)
