import time, logging
from .base import BaseFiscalDriver
log = logging.getLogger('EPSON_Fiscal')
ESC=b'\x1b'; GS=b'\x1d'

class EpsonFiscalDriver(BaseFiscalDriver):
    def _wt(self, conn, text): conn.write(text.encode('latin-1',errors='replace')); conn.flush(); time.sleep(0.05)
    def _fc(self, conn, code, data=b''):
        conn.write(ESC+b'\x46'+code+data+b'\r'); conn.flush(); time.sleep(0.2)
        resp=b''
        while conn.in_waiting: resp+=conn.read(conn.in_waiting); time.sleep(0.05)
        return resp
    def print_fiscal_invoice(self, payload):
        conn=None
        try:
            conn=self._open_port()
            emisor=payload.get('emisor',{}); rec=payload.get('receptor',{})
            conn.write(ESC+b'\x40'); time.sleep(0.3)
            self._wt(conn,'\x1b\x61\x01'); self._wt(conn,emisor.get('razon_social','')[:40]+'\n')
            self._wt(conn,'RIF: '+emisor.get('rif','')+'\n'); self._wt(conn,'\x1b\x61\x00')
            tipo=b'\x46' if 'factura' in payload.get('tipo_documento','factura') else b'\x54'
            r=self._fc(conn,b'\x01'+tipo,rec.get('nombre','CONSUMIDOR FINAL')[:30].encode('latin-1')+b'\x1c'+rec.get('rif','V-00000000')[:12].encode('latin-1'))
            if r and r[0]!=0x06: return {'success':False,'error':'EPSON apertura: 0x'+r.hex()}
            for item in payload.get('items',[]):
                desc=self._truncate(item.get('description','Producto'),20)
                data=(desc+'\x1c'+'{:.3f}'.format(float(item.get('quantity',1)))+'\x1c'+'{:.4f}'.format(float(item.get('unit_price',0)))+'\x1c'+'{:02d}'.format(int(item.get('tax_rate',16)))).encode('latin-1')
                self._fc(conn,b'\x02',data)
            r=self._fc(conn,b'\x03','{:.4f}'.format(float(payload.get('total',0))).encode('latin-1'))
            if r and r[0]!=0x06: return {'success':False,'error':'EPSON total error'}
            for p in payload.get('pagos',[]):
                code=b'\x45' if 'tarjeta' in p.get('method','') else b'\x43'
                self._fc(conn,code,'{:.4f}'.format(float(p.get('amount',0))).encode('latin-1'))
            r=self._fc(conn,b'\x04')
            if r and r[0]!=0x06: return {'success':False,'error':'EPSON cierre error'}
            conn.write(GS+b'\x56\x01'); conn.flush()
            return {'success':True,'numero_control':payload.get('numero_control',''),'numero_factura':payload.get('numero_factura','')}
        except Exception as e: return {'success':False,'error':str(e)}
        finally: self._close_port(conn)