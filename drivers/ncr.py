import time, logging
from .base import BaseFiscalDriver
log = logging.getLogger('NCR')

class NCRDriver(BaseFiscalDriver):
    def _cmd(self, conn, code, params=''):
        conn.write(('\x02'+code+params+'\x03\r\n').encode('latin-1')); conn.flush(); time.sleep(0.2)
        resp=b''
        while conn.in_waiting: resp+=conn.read(conn.in_waiting); time.sleep(0.05)
        return resp.decode('latin-1',errors='replace').strip()
    def print_fiscal_invoice(self, payload):
        conn=None
        try:
            conn=self._open_port()
            rec=payload.get('receptor',{})
            tipo='F' if 'factura' in payload.get('tipo_documento','factura') else 'T'
            r=self._cmd(conn,'DIF'+tipo)
            if 'ERR' in r.upper(): return {'success':False,'error':'NCR apertura: '+r}
            self._cmd(conn,'DCN',rec.get('nombre','CONSUMIDOR FINAL')[:30])
            self._cmd(conn,'DCR',rec.get('rif','V-00000000')[:12])
            for item in payload.get('items',[]):
                desc=self._truncate(item.get('description','Producto'),20)
                self._cmd(conn,'VIT',desc+'|'+'{:.3f}'.format(float(item.get('quantity',1)))+'|'+'{:.4f}'.format(float(item.get('unit_price',0)))+'|'+str(int(item.get('tax_rate',16))))
            self._cmd(conn,'SUB','{:.4f}'.format(float(payload.get('total',0))))
            for p in payload.get('pagos',[]): self._cmd(conn,'PAG',p.get('method','cash_usd')+'|'+'{:.4f}'.format(float(p.get('amount',0))))
            r=self._cmd(conn,'CIE')
            if 'ERR' in r.upper(): return {'success':False,'error':'NCR cierre: '+r}
            return {'success':True,'numero_control':payload.get('numero_control',''),'numero_factura':payload.get('numero_factura','')}
        except Exception as e: return {'success':False,'error':str(e)}
        finally: self._close_port(conn)