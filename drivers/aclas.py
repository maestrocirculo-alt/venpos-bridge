"""
Driver ACLAS — Impresoras PP9-PLUS, PP9A, PP7A, PP5A.
Protocolo: comandos ASCII con separador ';' y checksum XOR.
Fabricadas por THE FACTORY HKA C.A.
"""

import time
import logging
from .base import BaseFiscalDriver

log = logging.getLogger("ACLAS")


class ACLASDriver(BaseFiscalDriver):

    def _checksum(self, data: str) -> str:
        cs = 0
        for c in data:
            cs ^= ord(c)
        return f"{cs:02X}"

    def _cmd(self, conn, code: str, *params) -> str:
        body = code + ";" + ";".join(str(p) for p in params)
        full = f"\x02{body};{self._checksum(body)}\x03"
        conn.write(full.encode("latin-1"))
        conn.flush()
        time.sleep(0.2)
        resp = b""
        while conn.in_waiting:
            resp += conn.read(conn.in_waiting)
            time.sleep(0.05)
        return resp.decode("latin-1", errors="replace").strip()

    def print_fiscal_invoice(self, payload: dict) -> dict:
        conn = None
        try:
            conn = self._open_port()
            receptor = payload.get("receptor", {})
            items = payload.get("items", [])
            pagos = payload.get("pagos", [])

            # Abrir factura
            r = self._cmd(conn, "OF",
                          receptor.get("nombre", "CONSUMIDOR FINAL")[:30],
                          receptor.get("rif", "V-00000000")[:12],
                          receptor.get("direccion", "")[:40])
            if r.startswith("E"):
                return {"success": False, "error": f"ACLAS error apertura: {r}"}

            # Ítems
            for item in items:
                r = self._cmd(conn, "VI",
                              self._truncate(item.get("description", "Producto"), 20),
                              f"{float(item.get('quantity', 1)):.3f}",
                              f"{float(item.get('unit_price', 0)):.4f}",
                              str(int(item.get("tax_rate", 16))))
                if r.startswith("E"):
                    log.warning(f"ACLAS: ítem rechazado — {r}")

            # Descuento
            desc = float(payload.get("descuento", 0))
            if desc > 0:
                self._cmd(conn, "DG", f"{desc:.4f}")

            # Totalizar + pagos
            total = float(payload.get("total", 0))
            r = self._cmd(conn, "TT", f"{total:.4f}")
            if r.startswith("E"):
                return {"success": False, "error": f"ACLAS error totalización: {r}"}

            for pago in pagos:
                self._cmd(conn, "FP",
                          _aclas_payment(pago.get("method", "cash_usd")),
                          f"{float(pago.get('amount', 0)):.4f}")

            # Cerrar
            r = self._cmd(conn, "CF")
            if r.startswith("E"):
                return {"success": False, "error": f"ACLAS error cierre: {r}"}

            return {
                "success": True,
                "numero_control": payload.get("numero_control", ""),
                "numero_factura": payload.get("numero_factura", ""),
            }
        except Exception as e:
            log.error(f"ACLAS error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)

    # ── Operaciones de mantenimiento fiscal (SENIAT) ──────────────────────────
    # THE FACTORY HKA fabrica la linea ACLAS (PP9-PLUS, PP9A, etc.) y comparte
    # los mismos codigos de mantenimiento que la linea HKA: Z0=estado, X0=Reporte
    # X, Z1=Cierre Z, S4=cancelar documento. Se envian con el framing ACLAS
    # (STX + comando;params;checksum + ETX) heredado de _cmd.

    def get_fiscal_status(self) -> dict:
        conn = None
        try:
            conn = self._open_port()
            raw = self._cmd(conn, "Z0")
            err = raw.startswith("E") or "ERROR" in raw.upper()
            low = raw.upper()
            paper_ok = "SINPAPEL" not in low and "PAPER" not in low.replace("PAPEROUT", "")
            doc_open = "ABIER" in low or "DOC" in low
            z_pending = "ZPEND" in low or "CIERRE" in low
            ready = not err and paper_ok and not doc_open and not z_pending
            return {
                "success": True,
                "paper_ok": paper_ok,
                "doc_open": doc_open,
                "z_pending": z_pending,
                "printer_ready": ready,
                "raw": raw,
            }
        except Exception as e:
            return {
                "success": False, "paper_ok": None, "doc_open": None,
                "z_pending": None, "printer_ready": False, "error": str(e),
            }
        finally:
            self._close_port(conn)

    def print_report_x(self) -> dict:
        conn = None
        try:
            conn = self._open_port()
            r = self._cmd(conn, "X0")
            if r.startswith("E"):
                return {"success": False, "error": f"Error en Reporte X: {r}", "code": r}
            return {"success": True, "message": "Reporte X emitido", "raw": r}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)

    def print_report_z(self) -> dict:
        conn = None
        try:
            conn = self._open_port()
            r = self._cmd(conn, "Z1")
            if r.startswith("E"):
                return {"success": False, "error": f"Error en Cierre Z: {r}", "code": r}
            z_number = ""
            if "^" in r:
                parts = r.split("^")
                if len(parts) >= 2:
                    z_number = parts[1].strip()
            elif r:
                z_number = r.replace("OK", "").strip()
            return {"success": True, "z_number": z_number, "message": "Cierre Z emitido", "raw": r}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)

    def cancel_document(self) -> dict:
        conn = None
        try:
            conn = self._open_port()
            r = self._cmd(conn, "S4")
            if r.startswith("E"):
                return {"success": False, "error": f"Error al cancelar documento: {r}", "code": r}
            return {"success": True, "message": "Documento cancelado", "raw": r}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self._close_port(conn)


def _aclas_payment(method: str) -> str:
    MAP = {"cash_usd": "E", "cash_ves": "E", "tarjeta": "T",
           "transferencia": "C", "pago_movil": "M", "zelle": "Z"}
    return MAP.get(method, "E")
