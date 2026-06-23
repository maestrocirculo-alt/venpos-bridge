import time, logging
from .base import BaseFiscalDriver
log = logging.getLogger('Generic')
W=42

class GenericDriver(BaseFiscalDriver):
    def _l(self,conn,text='',center=False):
        if center: text=text.center(W)
        conn.write((text[:W]+'\n').encode(self.config.encoding or 'latin-1',errors='replace')); conn.flush(); time.sleep(0.03)
    def _d(self,conn,ch='-'): self._l(conn,ch*W)
    def print_fiscal_invoice(self, payload):
        conn=None
        try:
            conn=self._open_port()
            em=payload.get('emisor',{}); rec=payload.get('receptor',{})
            nc=payload.get('numero_control',''); nf=payload.get('numero_factura','')
            self._d(conn,'='); self._l(conn,em.get('razon_social','EMPRESA'),center=True)
            self._l(conn,'RIF: '+em.get('rif',''),center=True)
            self._d(conn,'-')
            self._l(conn,'FACTURA N Control: '+nc,center=True)
            self._l(conn,'N Factura: '+nf,center=True)
            self._l(conn,'Fecha: '+payload.get('fecha_hora','')[:19])
            self._l(conn,'Cajero: '+payload.get('cajero',''))
            self._d(conn,'-')
            self._l(conn,'Cliente: '+rec.get('nombre','CONSUMIDOR FINAL'))
            self._l(conn,'RIF/CI: '+rec.get('rif','V-00000000'))
            self._d(conn,'-')
            for item in payload.get('items',[]):
                qty=float(item.get('quantity',1)); price=float(item.get('unit_price',0))
                total_item=float(item.get('subtotal',qty*price))
                self._l(conn,item.get('description','Producto')[:22])
                self._l(conn,'  '+'{:.3f}'.format(qty)+' x '+'{:.4f}'.format(price)+' = '+'{:.2f}'.format(total_item))
            self._d(conn,'=')
            self._l(conn,'Base Imponible'.ljust(20)+'{:.4f}'.format(float(payload.get('subtotal',0))))
            self._l(conn,'IVA (16%)'.ljust(20)+'{:.4f}'.format(float(payload.get('monto_iva',0))))
            self._d(conn,'=')
            total=float(payload.get('total',0))
            self._l(conn,'TOTAL'.ljust(20)+'{:.2f}'.format(total))
            tasa=float(payload.get('tasa_bcv',0))
            if tasa>0: self._l(conn,'Bs.'.ljust(20)+'Bs.'+'{:.2f}'.format(float(payload.get('total_ves',0))))
            self._d(conn,'-')
            for p in payload.get('pagos',[]): self._l(conn,p.get('method','').replace('_',' ').upper().ljust(20)+'{:.2f}'.format(float(p.get('amount',0))))
            self._d(conn,'='); self._l(conn,'Documento fiscal SENIAT',center=True); self._d(conn,'=')
            self._l(conn,''); self._l(conn,'')
            return {'success':True,'numero_control':nc,'numero_factura':nf}
        except Exception as e: return {'success':False,'error':str(e)}
        finally: self._close_port(conn)
    def print_test(self):
        conn=None
        try:
            conn=self._open_port(); conn.write(b'*** VenPOS Bridge - Prueba OK ***\n'); conn.flush()
            return {'success':True,'message':'Prueba enviada'}
        except Exception as e: return {'success':False,'error':str(e)}
        finally: self._close_port(conn)