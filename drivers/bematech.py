import time, logging
from .base import BaseFiscalDriver
log = logging.getLogger('Bematech')
ESC=b'\x1b'; ACK=0x06
OPEN=b'\x41'; ITEM=b'\x45'; CLOSE=b'\x46'; PAY=b'\x47'; END=b'\x48'; STATUS=b'\x4C'

class BematechDriver(BaseFiscalDriver):
    def _raw(self, conn, cmd, data=b''):
        conn.write(ESC+cmd+data); conn.flush(); time.sleep(0.2)
        resp=b''; deadline=time.time()+float(self.config.timeout or 10)
        while time.time()<deadline:
            if conn.in_waiting: resp+=conn.read(conn.in_waiting)
            if resp: break
            time.sleep(0.05)
        return resp
    def _ok(self,r): return len(r)>0 and r[0]==ACK
    def print_fiscal_invoice(self, payload):
        conn=None
        try:
            conn=self._open_port()
            rec=payload.get('receptor',{})
            nombre=self._truncate(rec.get('nombre','CONSUMIDOR FINAL'),30)
            rif=self._truncate(rec.get('rif','V00000000'),14)
            r=self._raw(conn,OPEN,(nombre+'\x1c'+rif+'\x1c\x1c').encode('latin-1'))
            if not self._ok(r): return {'success':False,'error':'Error apertura Bematech'}
            for item in payload.get('items',[]):
                desc=self._truncate(item.get('description','Producto'),20).ljust(20)
                s=desc+'{:02d}'.format(int(item.get('tax_rate',16)))+'{:07.3f}'.format(float(item.get('quantity',1)))+'{:08.2f}'.format(float(item.get('unit_price',0)))
                self._raw(conn,ITEM,s.encode('latin-1'))
            r=self._raw(conn,CLOSE,'{:014.2f}'.format(float(payload.get('total',0))).encode('latin-1'))
            if not self._ok(r): return {'success':False,'error':'Error total Bematech'}
            for p in payload.get('pagos',[]):
                label={'cash_usd':'DINERO','cash_ves':'DINERO','tarjeta':'TARJETA CREDITO'}.get(p.get('method',''),'DINERO')
                self._raw(conn,PAY,(label.ljust(16)+'{:014.2f}'.format(float(p.get('amount',0)))).encode('latin-1'))
            r=self._raw(conn,END)
            if not self._ok(r): return {'success':False,'error':'Error cierre Bematech'}
            return {'success':True,'numero_control':payload.get('numero_control',''),'numero_factura':payload.get('numero_factura','')}
        except Exception as e: return {'success':False,'error':str(e)}
        finally: self._close_port(conn)
    def print_test(self):
        conn=None
        try:
            conn=self._open_port(); r=self._raw(conn,STATUS)
            return {'success':bool(r),'message':'0x'+r.hex() if r else 'Sin respuesta'}
        except Exception as e: return {'success':False,'error':str(e)}
        finally: self._close_port(conn)