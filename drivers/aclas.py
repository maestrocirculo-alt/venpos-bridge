import time, logging
from .base import BaseFiscalDriver
log = logging.getLogger('ACLAS')

class ACLASDriver(BaseFiscalDriver):
    def _cs(self, d):
        c=0
        for ch in d: c^=ord(ch)
        return '{:02X}'.format(c)
    def _cmd(self, conn, code, *params):
        body=code+';'+';'.join(str(p) for p in params)
        conn.write(('\x02'+body+';'+self._cs(body)+'\x03').encode('latin-1')); conn.flush(); time.sleep(0.2)
        resp=b''
        while conn.in_waiting: resp+=conn.read(conn.in_waiting); time.sleep(0.05)
        return resp.decode('latin-1',errors='replace').strip()
    def print_fiscal_invoice(self, payload):
        conn=None
        try:
            conn=self._open_port()
            rec=payload.get('receptor',{})
            r=self._cmd(conn,'OF',rec.get('nombre','CF')[:30],rec.get('rif','V-00000000')[:12],rec.get('direccion','')[:40])
            if r.startswith('E'): return {'success':False,'error':'ACLAS apertura: '+r}
            for item in payload.get('items',[]):
                r=self._cmd(conn,'VI',self._truncate(item.get('description','Producto'),20),'{:.3f}'.format(float(item.get('quantity',1))),'{:.4f}'.format(float(item.get('unit_price',0))),str(int(item.get('tax_rate',16))))
            disc=float(payload.get('descuento',0))
            if disc>0: self._cmd(conn,'DG','{:.4f}'.format(disc))
            r=self._cmd(conn,'TT','{:.4f}'.format(float(payload.get('total',0))))
            if r.startswith('E'): return {'success':False,'error':'ACLAS total: '+r}
            pm={'cash_usd':'E','cash_ves':'E','tarjeta':'T','pago_movil':'M','zelle':'Z'}
            for p in payload.get('pagos',[]): self._cmd(conn,'FP',pm.get(p.get('method',''),'E'),'{:.4f}'.format(float(p.get('amount',0))))
            r=self._cmd(conn,'CF')
            if r.startswith('E'): return {'success':False,'error':'ACLAS cierre: '+r}
            return {'success':True,'numero_control':payload.get('numero_control',''),'numero_factura':payload.get('numero_factura','')}
        except Exception as e: return {'success':False,'error':str(e)}
        finally: self._close_port(conn)