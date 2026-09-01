"""
Driver HKA — Impresoras fiscales HKA 80H, 110H, Hasar 715F, 330F.
Protocolo: comandos ASCII via serial.
Comandos principales:
  S0 — Inicio de documento (factura)
  S1 — Línea de ítem: descripción, cantidad, precio, alícuota
  S2 — Total, descuento, forma de pago
  S3 — Cierre de documento
  S4 — Cancelar/abortar documento abierto
  X0 — Reporte X (lectura parcial)
  Z0/Z1 — Consultar estado / Cierre Z (cierre de jornada — irreversible)
"""
import time, logging
from .base import BaseFiscalDriver
log = logging.getLogger("HKA")
IVA_TABLE = {0: "A", 8: "B", 16: "C", 31: "D"}

class HKADriver(BaseFiscalDriver):
    def _send_cmd(self, conn, cmd, wait=0.15):
        conn.write((cmd + "\r").encode(self.config.encoding or "latin-1")); conn.flush(); time.sleep(wait)
        response = b""; deadline = time.time() + 5
        while conn.in_waiting or (time.time() < deadline and not response):
            if conn.in_waiting: response += conn.read(conn.in_waiting); time.sleep(0.05)
            else: time.sleep(0.05)
            if response and not conn.in_waiting: break
        return response.decode(self.config.encoding or "latin-1", errors="replace").strip()

    def _check_error(self, response): return response.startswith("E") or "ERROR" in response.upper()

    def get_fiscal_status(self):
        conn = None
        try:
            conn = self._open_port()
            raw = self._send_cmd(conn, "Z0", wait=0.3); err = self._check_error(raw); low = raw.upper()
            paper_ok = "SINPAPEL" not in low and "PAPER" not in low.replace("PAPEROUT", "")
            doc_open = "ABIER" in low or "DOC" in low; z_pending = "ZPEND" in low or "CIERRE" in low
            ready = not err and paper_ok and not doc_open and not z_pending
            return {"success": True, "paper_ok": paper_ok, "doc_open": doc_open, "z_pending": z_pending, "printer_ready": ready, "raw": raw}
        except Exception as e:
            return {"success": False, "paper_ok": None, "doc_open": None, "z_pending": None, "printer_ready": False, "error": str(e)}
        finally: self._close_port(conn)

    def print_report_x(self):
        conn = None
        try:
            conn = self._open_port(); r = self._send_cmd(conn, "X0", wait=0.5)
            if self._check_error(r): return {"success": False, "error": f"Error en Reporte X: {r}", "code": r}
            return {"success": True, "message": "Reporte X emitido", "raw": r}
        except Exception as e: return {"success": False, "error": str(e)}
        finally: self._close_port(conn)

    def print_report_z(self):
        conn = None
        try:
            conn = self._open_port(); r = self._send_cmd(conn, "Z1", wait=1.0)
            if self._check_error(r): return {"success": False, "error": f"Error en Cierre Z: {r}", "code": r}
            z_number = ""
            if "^" in r:
                parts = r.split("^")
                if len(parts) >= 2: z_number = parts[1].strip()
            elif r: z_number = r.replace("OK", "").strip()
            return {"success": True, "z_number": z_number, "message": "Cierre Z emitido", "raw": r}
        except Exception as e: return {"success": False, "error": str(e)}
        finally: self._close_port(conn)

    def cancel_document(self):
        conn = None
        try:
            conn = self._open_port(); r = self._send_cmd(conn, "S4", wait=0.3)
            if self._check_error(r): return {"success": False, "error": f"Error al cancelar: {r}", "code": r}
            return {"success": True, "message": "Documento cancelado", "raw": r}
        except Exception as e: return {"success": False, "error": str(e)}
        finally: self._close_port(conn)

    def print_fiscal_invoice(self, payload):
        conn = None
        try:
            conn = self._open_port()
            receptor = payload.get("receptor", {}); items = payload.get("items", []); pagos = payload.get("pagos", [])
            tipo = payload.get("tipo_documento", "factura").upper()
            doc_type = "F" if tipo == "FACTURA" else "N" if tipo == "NOTA_ENTREGA" else "T"
            r = self._send_cmd(conn, f"S0{doc_type}")
            if self._check_error(r): return {"success": False, "error": f"Error al iniciar documento: {r}", "code": r}
            nombre = self._truncate(receptor.get("nombre", "CONSUMIDOR FINAL"), 40)
            rif = self._truncate(receptor.get("rif", "V-00000000"), 12)
            direccion = self._truncate(receptor.get("direccion", ""), 60)
            self._send_cmd(conn, f"S01{nombre}"); self._send_cmd(conn, f"S02{rif}")
            if direccion: self._send_cmd(conn, f"S03{direccion}")
            for item in items:
                desc = self._truncate(item.get("description", "Producto"), 20)
                qty = float(item.get("quantity", 1)); price = float(item.get("unit_price", 0))
                tax_rate = int(item.get("tax_rate", 16)); aliquot = IVA_TABLE.get(tax_rate, "C")
                r = self._send_cmd(conn, f"S1{desc}^{qty:.3f}^{price:.4f}^{aliquot}")
                if self._check_error(r): log.warning(f"Advertencia en ítem '{desc}': {r}")
            igtf = float(payload.get("igtf_amount", 0) or 0)
            if igtf > 0:
                r = self._send_cmd(conn, f"S1IGTF 3% Divisas^1^{igtf:.4f}^A")
                if self._check_error(r): log.warning(f"Advertencia al enviar IGTF: {r}")
            discount = float(payload.get("descuento", 0))
            if discount > 0: self._send_cmd(conn, f"S1Descuento^1^-{discount:.4f}^C")
            total = float(payload.get("total", 0))
            pago_principal = pagos[0] if pagos else {"method": "efectivo", "amount": total}
            method_label = _payment_label(pago_principal.get("method", "efectivo"))
            r = self._send_cmd(conn, f"S2{method_label}^{total:.4f}")
            if self._check_error(r): return {"success": False, "error": f"Error en totalización: {r}", "code": r}
            for pago in pagos[1:]:
                self._send_cmd(conn, f"S2{_payment_label(pago.get('method', 'otro'))}^{float(pago.get('amount', 0)):.4f}")
            r = self._send_cmd(conn, "S3")
            if self._check_error(r): return {"success": False, "error": f"Error al cerrar documento: {r}", "code": r}
            nc, nf = payload.get("numero_control", ""), payload.get("numero_factura", "")
            if "^" in r:
                parts = r.split("^")
                if len(parts) >= 3: nc = parts[1].strip(); nf = parts[2].strip()
            code = r if r.startswith("R") or r.startswith("E") else "R200"
            return {"success": True, "numero_control": nc, "numero_factura": nf, "code": code}
        except Exception as e:
            log.error(f"HKA error: {e}", exc_info=True); return {"success": False, "error": str(e), "code": "E501"}
        finally: self._close_port(conn)

    def print_test(self):
        conn = None
        try:
            conn = self._open_port(); r = self._send_cmd(conn, "Z0")
            return {"success": True, "message": f"HKA status: {r}"}
        except Exception as e: return {"success": False, "error": str(e)}
        finally: self._close_port(conn)

def _payment_label(method):
    MAP = {"cash_usd": "EFECTIVO", "cash_ves": "EFECTIVO_BS", "cash_eur": "EFECTIVO_EUR",
        "pago_movil": "PAGO_MOVIL", "zelle": "ZELLE", "tarjeta": "TARJETA",
        "transferencia": "TRANSFERENCIA", "usdt": "CRIPTO", "cashea": "CASHEA"}
    return MAP.get(method, "EFECTIVO")
