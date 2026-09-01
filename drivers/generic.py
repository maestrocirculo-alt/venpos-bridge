"""
Driver Genérico — Para impresoras personalizadas o no reconocidas.
Imprime la factura en formato texto plano por el puerto serial.
Útil también para pruebas sin impresora física.
"""

import time
import logging
from .base import BaseFiscalDriver

log = logging.getLogger("Generic")

LINE_WIDTH = 42


class GenericDriver(BaseFiscalDriver):

    def _write_line(self, conn, text: str = "", center: bool = False, bold: bool = False):
        if center:
            text = text.center(LINE_WIDTH)
        line = (text[:LINE_WIDTH] + "\n").encode(self.config.encoding or "latin-1", errors="replace")
        conn.write(line)
        conn.flush()
        time.sleep(0.03)

    def _divider(self, conn, char: str = "-"):
        self._write_line(conn, char * LINE_WIDTH)

    def print_fiscal_invoice(self, payload: dict) -> dict:
        conn = None
        try:
            conn = self._open_port()
            emisor = payload.get("emisor", {})
            receptor = payload.get("receptor", {})
            items = payload.get("items", [])
            pagos = payload.get("pagos", [])

            self._divider(conn, "=")
            self._write_line(conn, emisor.get("razon_social", "EMPRESA"), center=True, bold=True)
            self._write_line(conn, f"RIF: {emisor.get('rif', '')}", center=True)
            self._write_line(conn, emisor.get("direccion", "")[:42], center=True)
            self._write_line(conn, emisor.get("telefono", ""), center=True)
            self._divider(conn, "-")

            tipo = payload.get("tipo_documento", "FACTURA").upper()
            nc = payload.get("numero_control", "")
            nf = payload.get("numero_factura", "")
            self._write_line(conn, f"{tipo} N° Control: {nc}", center=True, bold=True)
            self._write_line(conn, f"N° Factura: {nf}", center=True)
            self._write_line(conn, f"Fecha: {payload.get('fecha_hora', '')[:19]}")
            self._write_line(conn, f"Cajero: {payload.get('cajero', '')}")
            self._divider(conn, "-")
            self._write_line(conn, f"Cliente: {receptor.get('nombre', 'CONSUMIDOR FINAL')}")
            self._write_line(conn, f"RIF/CI: {receptor.get('rif', 'V-00000000')}")
            if receptor.get("direccion"):
                self._write_line(conn, f"Dir: {receptor['direccion'][:40]}")
            self._divider(conn, "-")

            for item in items:
                desc = item.get("description", "Producto")[:22]
                qty  = float(item.get("quantity", 1))
                price = float(item.get("unit_price", 0))
                total_item = float(item.get("subtotal", qty * price))
                unit = item.get("unit", "UND")
                self._write_line(conn, desc)
                self._write_line(conn, f"  {qty:.3f} {unit} x ${price:.4f} = ${total_item:.2f}")

            self._divider(conn, "-")
            subtotal = float(payload.get("subtotal", 0))
            iva = float(payload.get("monto_iva", 0))
            desc_val = float(payload.get("descuento", 0))
            total = float(payload.get("total", 0))
            total_ves = float(payload.get("total_ves", 0))
            tasa = float(payload.get("tasa_bcv", 0))

            if desc_val > 0:
                self._write_line(conn, f"{'Subtotal':<20}${subtotal:.2f}")
                self._write_line(conn, f"{'Descuento':<20}-${desc_val:.2f}")
            alicuota = payload.get("alicuota_iva", 16)
            self._write_line(conn, f"{'Base Imponible':<20}${subtotal:.4f}")
            self._write_line(conn, f"{'IVA (' + str(alicuota) + '%)':<20}${iva:.4f}")
            self._divider(conn, "=")
            self._write_line(conn, f"{'TOTAL':<20}${total:.2f}", bold=True)
            if tasa > 0:
                self._write_line(conn, f"{'Bs.':<20}Bs.{total_ves:.2f}")
                self._write_line(conn, f"Tasa BCV: Bs.{tasa:.2f}/$1")
            self._divider(conn, "-")

            for pago in pagos:
                method = pago.get("method", "efectivo").replace("_", " ").upper()
                amt = float(pago.get("amount", 0))
                currency = pago.get("currency", "USD")
                self._write_line(conn, f"{method:<20}${amt:.2f}")

            self._divider(conn, "=")
            self._write_line(conn, "Documento fiscal emitido conforme", center=True)
            self._write_line(conn, "al PROVIDENCIA SENIAT", center=True)
            self._divider(conn, "=")
            self._write_line(conn, "")
            self._write_line(conn, "")

            return {
                "success": True,
                "numero_control": nc,
                "numero_factura": nf,
            }
        except Exception as e:
            log.error(f"Generic driver error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)

    def print_test(self) -> dict:
        conn = None
        try:
            conn = self._open_port()
            test_line = "*** VenPOS Bridge — Prueba de impresión OK ***\n"
            conn.write(test_line.encode("latin-1"))
            conn.flush()
            return {"success": True, "message": "Prueba enviada al puerto"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)