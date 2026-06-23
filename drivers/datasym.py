import time, logging
from .base import BaseFiscalDriver
log = logging.getLogger('Datasym')

class DatasymDriver(BaseFiscalDriver):
    def _cmd(self, conn, cmd):
        conn.write(('@'+cmd+'\r\n').encode('latin-1')); conn.flush(); time.sleep(0.2)
        resp=b''
        while conn.in_waiting: resp+=conn.read(conn.in_waiting); time.sleep(0.05)
        return resp.decode('latin-1',errors='replace').strip()
    def print_fiscal_invoice(self, payload):
        conn=None
        try:
            conn=self._open_port()
            rec=payload.get('receptor',{})
            r=self._cmd(conn,'OPEN_INV;'+rec.get('nombre','CF')[:30]+';'+rec.get('rif','V-0')[:12])
            if 'ERR' in r: return {'success':False,'error':'Datasym apertura: '+r}
            for item in payload.get('items',[]):
                self._cmd(conn,'ADD_ITEM;'+self._truncate(item.get('description','Producto'),20)+';'+'{:.3f}'.format(float(item.get('quantity',1)))+';'+'{:.4f}'.format(float(item.get('unit_price',0)))+';'+str(int(item.get('tax_rate',16))))
            self._cmd(conn,'TOTAL;'+'{:.4f}'.format(float(payload.get('total',0))))
            for p in payload.get('pagos',[]): self._cmd(conn,'PAYMENT;'+p.get('method','cash_usd')+';'+'{:.4f}'.format(float(p.get('amount',0))))
            r=self._cmd(conn,'CLOSE_INV')
            if 'ERR' in r: return {'success':False,'error':'Datasym cierre: '+r}
            return {'success':True,'numero_control':payload.get('numero_control',''),'numero_factura':payload.get('numero_factura','')}
        except Exception as e: return {'success':False,'error':str(e)}
        finally: self._close_port(conn)