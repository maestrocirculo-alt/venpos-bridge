import time, logging
from .base import BaseFiscalDriver
log=logging.getLogger("Generic")
LINE_WIDTH=42
class GenericDriver(BaseFiscalDriver):
    def _write_line(self, conn, text="", center=False):
        if center: text=text.center(LINE_WIDTH)
        conn.write((text[:LINE_WIDTH]+"\n").encode(self.config.encoding or "latin-1",errors="replace")); conn.flush(); time.sleep(0.03)
    def _divider(self, conn, char="-"): self._write_line(conn, char*LINE_WIDTH)
    def print_fiscal_invoice(self, payload):
        conn=None
        try:
            conn=self._open_port()
            emisor=payload.get("emisor",{}); receptor=payload.get("receptor",{}); items=payload.get("items",[]); pagos=payload.get("pagos",[])
            self._divider(conn,"=")
            self._write_line(conn,emisor.get("razon_social","EMPRESA"),center=True)
            self._write_line(conn,f"RIF: {emisor.get('rif','')}",center=True)
            self._divider(conn,"-")
            for item in items:
                self._write_line(conn,item.get("description","Producto")[:22])
                self._write_line(conn,f"  {float(item.get('quantity',1)):.3f} {item.get('unit','UND')} x ${float(item.get('unit_price',0)):.4f}")
            self._divider(conn,"-")
            self._write_line(conn,f"TOTAL: ${float(payload.get('total',0)):.2f}",center=True)
            self._divider(conn,"=")
            return {"success":True,"numero_control":payload.get("numero_control",""),"numero_factura":payload.get("numero_factura","")}
        except Exception as e:
            return {"success":False,"error":str(e)}
        finally:
            self._close_port(conn)
