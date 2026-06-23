import time, logging
from .base import BaseFiscalDriver

log = logging.getLogger('HKA')
IVA_TABLE = {0: 'A', 8: 'B', 16: 'C', 31: 'D'}

class HKADriver(BaseFiscalDriver):
    def _send_cmd(self, conn, cmd):
        conn.write((cmd + chr(13)).encode(self.config.encoding or 'latin-1'))
        conn.flush()
        time.sleep(0.15)
        resp = b''
        while conn.in_waiting:
            resp += conn.read(conn.in_waiting)
            time.sleep(0.05)
        return resp.decode(self.config.encoding or 'latin-1', errors='replace').strip()

    def _err(self, r): return r.startswith('E') or 'ERROR' in r.upper()

    def print_fiscal_invoice(self, payload):
        conn = None
        try:
            conn = self._open_port()
            receptor = payload.get('receptor', {})
            tipo = payload.get('tipo_documento', 'factura').upper()
            doc_type = 'F' if tipo == 'FACTURA' else 'N' if tipo == 'NOTA_ENTREGA' else 'T'
            r = self._send_cmd(conn, 'S0' + doc_type)
            if self._err(r): return {'success': False, 'error': 'Error inicio: ' + r}
            self._send_cmd(conn, 'S01' + self._truncate(receptor.get('nombre','CONSUMIDOR FINAL'),40))
            self._send_cmd(conn, 'S02' + self._truncate(receptor.get('rif','V-00000000'),12))
            for item in payload.get('items', []):
                desc = self._truncate(item.get('description','Producto'),20)
                qty = float(item.get('quantity',1))
                price = float(item.get('unit_price',0))
                alq = IVA_TABLE.get(int(item.get('tax_rate',16)),'C')
                self._send_cmd(conn, 'S1' + desc + '^' + '{:.3f}'.format(qty) + '^' + '{:.4f}'.format(price) + '^' + alq)
            disc = float(payload.get('descuento',0))
            if disc > 0: self._send_cmd(conn, 'S1Descuento^1^-' + '{:.4f}'.format(disc) + '^C')
            total = float(payload.get('total',0))
            pagos = payload.get('pagos',[])
            method = _pay((pagos[0] if pagos else {}).get('method','efectivo'))
            r = self._send_cmd(conn, 'S2' + method + '^' + '{:.4f}'.format(total))
            if self._err(r): return {'success': False, 'error': 'Error total: ' + r}
            for p in pagos[1:]:
                self._send_cmd(conn, 'S2' + _pay(p.get('method','')) + '^' + '{:.4f}'.format(float(p.get('amount',0))))
            r = self._send_cmd(conn, 'S3')
            if self._err(r): return {'success': False, 'error': 'Error cierre: ' + r}
            nc, nf = payload.get('numero_control',''), payload.get('numero_factura','')
            if '^' in r:
                parts = r.split('^')
                if len(parts) >= 3: nc, nf = parts[1].strip(), parts[2].strip()
            return {'success': True, 'numero_control': nc, 'numero_factura': nf}
        except Exception as e: return {'success': False, 'error': str(e)}
        finally: self._close_port(conn)

    def print_test(self):
        conn = None
        try:
            conn = self._open_port()
            r = self._send_cmd(conn, 'Z0')
            return {'success': True, 'message': 'HKA: ' + r}
        except Exception as e: return {'success': False, 'error': str(e)}
        finally: self._close_port(conn)

def _pay(method):
    return {'cash_usd':'EFECTIVO','cash_ves':'EFECTIVO_BS','pago_movil':'PAGO_MOVIL',
            'zelle':'ZELLE','tarjeta':'TARJETA','transferencia':'TRANSFERENCIA'}.get(method,'EFECTIVO')