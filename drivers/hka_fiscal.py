"""
Driver fiscal para impresoras con el protocolo de The Factory HKA:
HKA80 / HKA112 / SRP-812 / DT-230 / PP9 / ACLAS PP9-PLUS (PP9A, PP7A, PP5A).

Implementado sobre el Manual de Protocolos y Comandos V8.5.0 (ver hka_protocol.py).
Comandos usados (todos del manual):

  ENQ (0x05)            estado de la impresora
  I0X / I0Z             Reporte X / Cierre Z            (Tabla 59)
  7                     anular el documento fiscal en curso
  S1                    status: contadores, RIF, serial  (Tabla 45)
  iR*<rif> / iS*<nom>   RIF/C.I. y razón social del cliente
  i01..i09              líneas adicionales
  ' ' ! " # $           ítem exento / tasa 1 / 2 / 3 / 4 (percibido) + precio(10) + cantidad(8) + descripción
  q-<9 dígitos>         descuento por monto (aplica al último ítem)
  2<medio 2d><monto 12d> pago parcial       1<medio 2d> pago directo (completa el total)
  199                   cierre del documento cuando el flag 50 (IGTF) está en 01
"""

import logging
import time

from .base import BaseFiscalDriver
from .hka_protocol import (
    HKASession, PrinterBusy, SERIAL_LABEL, clean_text, explain_open_error, parse_s1,
)

log = logging.getLogger("HKA")

# Tasa del ítem -> carácter de comando (Tabla 28). Depende de cómo esté programada la impresora.
TAX_CHARS = {0: " ", 8: '"', 16: "!", 31: "#"}

# Métodos de pago cuyo monto ya está en Bs. (el resto viene en la moneda base del negocio)
VES_METHODS = {"cash_ves", "pago_movil", "tarjeta", "transferencia", "cashea", "biopago"}
# Divisas: usan los medios 20-24 (IGTF) solo si el flag 50 está activo en la impresora
DIVISA_METHODS = {"cash_usd", "cash_eur", "zelle", "usdt"}

# Medios de pago por defecto (Tabla 16: 01-06 Efectivo, 07-12 Cheque, 13-18 Tarjeta, 19 Ticket, 20-24 Divisa)
MEDIO_NACIONAL = {
    "cash_ves": 1, "pago_movil": 2, "transferencia": 7,
    "tarjeta": 13, "biopago": 13, "cashea": 14,
    "cuenta_cliente": 19, "gift_card": 19,
}
MEDIO_DIVISA = {"cash_usd": 20, "zelle": 21, "cash_eur": 22, "usdt": 23}
MEDIO_FORANEA_SIN_IGTF = {"cash_usd": 3, "zelle": 4, "cash_eur": 5, "usdt": 6}


class FiscalCommandError(Exception):
    def __init__(self, message, code="E503"):
        super().__init__(message)
        self.code = code


def _looks_like_spooler(port: str) -> bool:
    p = str(port or "").upper()
    return p.startswith("USB") or p in ("SPOOLER", "WINDOWS", "WINSPOOL")


class HKAFiscalDriver(BaseFiscalDriver):

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _port(self) -> str:
        return self.config.port or "COM1"

    def _require_serial_port(self):
        if _looks_like_spooler(self._port()):
            raise FiscalCommandError(
                "La impresora fiscal se conecta por un puerto COM (ej. COM3). "
                "Elige el puerto COM correcto en Configuración → Fiscal.", "E504")

    def _no_answer_msg(self) -> str:
        return (f"El puerto {self._port()} abre, pero la impresora NO responde ({SERIAL_LABEL}). "
                "Revisa: impresora encendida, cable serial/adaptador USB bien conectado y el número de COM "
                "correcto (usa «Diagnóstico» para buscarla).")

    def _ready_or_raise(self, s, allow_open_doc: bool = False, tolerate_fiscal_error: bool = False) -> dict:
        """ENQ previo a cualquier operación: la impresora debe responder y estar en espera.
        tolerate_fiscal_error: el Cierre Z debe poder emitirse aunque la impresora marque
        'error fiscal' (0x60), que es justo lo que ocurre cuando lleva más de 24 h sin Z."""
        st = s.enq(timeout=2.0)
        if not st.get("answered"):
            raise FiscalCommandError(self._no_answer_msg(), "E502")
        if not st.get("valid"):
            raise FiscalCommandError(
                f"La impresora respondió datos no válidos ({st.get('raw_hex')}). "
                f"Casi siempre es configuración serial incorrecta: debe ser {SERIAL_LABEL}.", "E505")
        if st.get("blocking_error") and not (tolerate_fiscal_error and st.get("sts2") == 0x60):
            raise FiscalCommandError(f"La impresora reporta un error: {st.get('error_text')}.", "E506")
        if not allow_open_doc and not st.get("idle"):
            # Puede estar imprimiendo el reporte anterior: darle tiempo antes de rendirse
            st2 = s.wait_idle(timeout=25.0)
            if not st2 or not st2.get("idle"):
                raise FiscalCommandError(
                    f"La impresora no está en espera: {(st2 or st).get('text')}. "
                    "Si hay un documento abierto, usa «Cancelar Doc.» en Mantenimiento Fiscal.", "E507")
            st = st2
        return st

    def _must(self, s, cmd: str, what: str):
        r = s.command(cmd)
        if r == "ACK":
            return
        if r == "NAK":
            raise FiscalCommandError(f"La impresora rechazó «{what}» (NAK). Comando: {cmd!r}", "E508")
        raise FiscalCommandError(f"La impresora no respondió a «{what}» (sin ACK). ¿Está ocupada o sin papel?", "E502")

    # ── Conexión / estado ─────────────────────────────────────────────────────
    def _probe(self, wait: float = 0.0) -> dict:
        try:
            self._require_serial_port()
        except FiscalCommandError as e:
            return {"opened": False, "error": str(e)}
        port = self._port()
        try:
            with HKASession(port, wait=wait) as s:
                return {"opened": True, "enq": s.enq(timeout=2.0)}
        except PrinterBusy:
            return {"busy": True}
        except Exception as e:
            return {"opened": False, "error": explain_open_error(port, e)}

    def snapshot(self):
        """(ready, detail, fiscal_dict) con un único ENQ."""
        p = self._probe(wait=0.0)
        empty = {"paper_ok": None, "doc_open": None, "z_pending": None, "printer_ready": False}
        if p.get("busy"):
            txt = "Ocupada: hay una operación en curso (Cierre Z, reporte o factura)"
            return True, txt, {**empty, "success": True, "busy": True, "status_text": txt}
        if not p.get("opened"):
            return False, p["error"], {**empty, "success": False, "error": p["error"]}
        st = p["enq"]
        if not st.get("answered"):
            msg = self._no_answer_msg()
            return False, msg, {**empty, "success": False, "error": msg}
        if not st.get("valid"):
            msg = (f"La impresora respondió datos no válidos ({st.get('raw_hex')}). "
                   f"Debe estar en {SERIAL_LABEL}.")
            return False, msg, {**empty, "success": False, "error": msg, "raw": st.get("raw_hex")}
        detail = f"Impresora respondiendo en {self._port()} — {st['text']}"
        return True, detail, {
            "success": True,
            "paper_ok": st["paper_ok"],
            "doc_open": st["in_fiscal_tx"],
            "z_pending": None,  # el protocolo no expone "Z pendiente": se detecta por el error fiscal (STS2)
            "printer_ready": st["ready"],
            "training_mode": st["training_mode"],
            "status_text": st["text"],
            "sts1": f"0x{st['sts1']:02X}", "sts2": f"0x{st['sts2']:02X}",
            "raw": st["raw_hex"],
        }

    def check_connection(self):
        ready, detail, _ = self.snapshot()
        return ready, detail

    def get_fiscal_status(self) -> dict:
        return self.snapshot()[2]

    # ── Status S1 (Z, última factura, serial) ─────────────────────────────────
    def _read_s1(self, s) -> dict:
        try:
            res, text = s.query("S1", timeout=4.0)
            if res == "OK":
                return parse_s1(text)
            log.warning(f"S1: {res}")
        except Exception as e:
            log.warning(f"S1 falló: {e}")
        return {}

    # ── Reporte X ─────────────────────────────────────────────────────────────
    def print_report_x(self) -> dict:
        try:
            self._require_serial_port()
            with HKASession(self._port()) as s:
                self._ready_or_raise(s)
                self._must(s, "I0X", "Reporte X")
                s.wait_idle(timeout=30.0)
                return {"success": True, "message": "Reporte X emitido"}
        except FiscalCommandError as e:
            return {"success": False, "error": str(e), "code": e.code}
        except Exception as e:
            return {"success": False, "error": self._explain(e)}

    # ── Cierre Z (irreversible) ───────────────────────────────────────────────
    def print_report_z(self) -> dict:
        try:
            self._require_serial_port()
            with HKASession(self._port()) as s:
                self._ready_or_raise(s, tolerate_fiscal_error=True)
                before = self._read_s1(s).get("z_counter")
                self._must(s, "I0Z", "Cierre Z")
                # El manual: el Z tarda ~20 s (+3 s de reporte de transmisión). Esperar a que termine.
                final = s.wait_idle(timeout=55.0)
                after = self._read_s1(s).get("z_counter")
                z_number = ""
                if after and (before is None or after != before):
                    z_number = after.lstrip("0") or after
                msg = "Cierre Z emitido"
                if not (final and final.get("idle")):
                    msg += " (la impresora sigue imprimiendo el reporte)"
                return {"success": True, "z_number": z_number, "message": msg}
        except FiscalCommandError as e:
            return {"success": False, "error": str(e), "code": e.code}
        except Exception as e:
            return {"success": False, "error": self._explain(e)}

    # ── Anular documento abierto ──────────────────────────────────────────────
    def cancel_document(self) -> dict:
        try:
            self._require_serial_port()
            with HKASession(self._port()) as s:
                st = self._ready_or_raise(s, allow_open_doc=True)
                if st.get("in_nonfiscal_tx"):
                    raise FiscalCommandError(
                        "Hay un documento NO fiscal abierto; esta función solo anula documentos fiscales.", "E509")
                if not st.get("in_fiscal_tx"):
                    return {"success": True, "message": "No había ningún documento fiscal abierto"}
                self._must(s, "7", "Anular documento")
                final = s.wait_idle(timeout=15.0)
                if final and final.get("idle"):
                    return {"success": True, "message": "Documento fiscal anulado"}
                raise FiscalCommandError(
                    "La impresora aceptó anular pero el documento sigue abierto (si ya hay pagos aplicados "
                    "debe completarse). Estado: " + ((final or {}).get("text") or "desconocido"), "E509")
        except FiscalCommandError as e:
            return {"success": False, "error": str(e), "code": e.code}
        except Exception as e:
            return {"success": False, "error": self._explain(e)}

    # ── Factura fiscal ────────────────────────────────────────────────────────
    def _rate_factor(self, payload: dict) -> float:
        base = str(payload.get("moneda_base") or "USD").upper()
        if base == "VES":
            return 1.0
        rate = float(payload.get("tasa_eur") or 0) if base == "EUR" else float(payload.get("tasa_bcv") or 0)
        if rate <= 0:
            raise FiscalCommandError(
                "Falta la tasa de cambio en la venta: la impresora fiscal factura en Bs.", "E510")
        return rate

    def _item_cmd(self, item: dict, factor: float, desc_len: int) -> str:
        rate = item.get("tax_rate")
        rate = 16 if rate is None else int(float(rate))
        tax_map = {**TAX_CHARS, **{int(k): v for k, v in (getattr(self.config, "tax_map", None) or {}).items()}}
        ch = tax_map.get(rate, "!")
        cents = int(round(float(item.get("unit_price", 0)) * factor * 100))
        qty_milli = int(round(float(item.get("quantity", 1)) * 1000))
        desc = clean_text(item.get("description", "Producto"), desc_len) or "Producto"
        return f"{ch}{cents:010d}{qty_milli:08d}{desc}"

    def _medio(self, method: str, igtf: bool) -> int:
        custom = getattr(self.config, "payment_map", None) or {}
        if method in custom:
            return int(custom[method])
        if method in DIVISA_METHODS:
            return (MEDIO_DIVISA if igtf else MEDIO_FORANEA_SIN_IGTF)[method]
        return MEDIO_NACIONAL.get(method, 1)

    def _payment_plan(self, payload: dict, factor: float, igtf: bool) -> list:
        rows = []
        for p in payload.get("pagos") or []:
            m, amt = p.get("method") or "cash_ves", float(p.get("amount") or 0)
            if amt <= 0:
                continue
            bs = amt if m in VES_METHODS else amt * factor
            rows.append({"medio": self._medio(m, igtf), "cents": int(round(bs * 100)),
                         "divisa": igtf and m in DIVISA_METHODS})
        if not rows:
            total_bs = float(payload.get("total_ves") or 0) or float(payload.get("total") or 0) * factor
            rows.append({"medio": 1, "cents": int(round(total_bs * 100)), "divisa": False})
        rows.sort(key=lambda r: r["divisa"])  # nacionales primero, divisas al final
        return rows

    def print_fiscal_invoice(self, payload: dict) -> dict:
        try:
            self._require_serial_port()
            factor = self._rate_factor(payload)
            igtf = bool(payload.get("igtf_enabled"))
            desc_len = int(getattr(self.config, "item_desc_len", None) or 20)
            items = payload.get("items") or []
            if not items:
                raise FiscalCommandError("La venta no tiene ítems para facturar.", "E510")

            tipo = str(payload.get("tipo_documento") or "factura").lower()
            if tipo != "factura":
                log.warning(f"Tipo de documento '{tipo}' se emite como factura fiscal (única opción del protocolo directo).")

            with HKASession(self._port()) as s:
                self._ready_or_raise(s)
                try:
                    r = payload.get("receptor") or {}
                    self._must(s, "iR*" + (clean_text(r.get("rif"), 20) or "V-00000000"), "RIF del cliente")
                    self._must(s, "iS*" + (clean_text(r.get("nombre"), 38) or "CONSUMIDOR FINAL"), "nombre del cliente")
                    if r.get("direccion"):
                        self._must(s, "i01" + clean_text("Dir: " + str(r["direccion"]), 38), "dirección del cliente")

                    for it in items:
                        self._must(s, self._item_cmd(it, factor, desc_len), "ítem " + clean_text(it.get("description"), 20))

                    discount = float(payload.get("descuento") or 0)
                    if discount > 0:
                        self._must(s, f"q-{int(round(discount * factor * 100)):09d}", "descuento")

                    plan = self._payment_plan(payload, factor, igtf)
                    for i, row in enumerate(plan):
                        last = i == len(plan) - 1
                        cmd = f"1{row['medio']:02d}" if last else f"2{row['medio']:02d}{row['cents']:012d}"
                        self._must(s, cmd, f"pago medio {row['medio']:02d}" + (" (NAK: ¿flag 50/IGTF no activo en la impresora?)" if row["divisa"] else ""))

                    st = s.wait_idle(timeout=3.0)
                    if st and st.get("in_fiscal_tx"):
                        # Con el flag 50 (IGTF) en 01 el documento solo cierra con el comando 199
                        r199 = s.command("199")
                        if r199 != "ACK" and igtf:
                            raise FiscalCommandError("La impresora no aceptó el cierre del documento (199).", "E508")
                    st = s.wait_idle(timeout=30.0)
                    if not (st and st.get("idle")):
                        raise FiscalCommandError(
                            "El documento no terminó de cerrarse: " + ((st or {}).get("text") or "sin respuesta"), "E511")
                except Exception:
                    # Nunca dejar un documento abierto: anularlo antes de informar el error
                    try:
                        s.command("7")
                        s.wait_idle(timeout=10.0)
                    except Exception:
                        pass
                    raise

                info = self._read_s1(s)
                return {
                    "success": True,
                    "numero_control": payload.get("numero_control", ""),
                    "numero_factura": info.get("last_invoice") or payload.get("numero_factura", ""),
                    "printer_serial": info.get("serial", ""),
                    "code": "R200",
                }
        except FiscalCommandError as e:
            log.error(f"Factura fiscal falló: {e}")
            return {"success": False, "error": str(e), "code": e.code}
        except PrinterBusy:
            return {"success": False, "error": "La impresora está ocupada con otra operación.", "code": "E507"}
        except Exception as e:
            log.error(f"Factura fiscal falló: {e}", exc_info=True)
            return {"success": False, "error": self._explain(e), "code": "E501"}

    def print_test(self) -> dict:
        ready, detail, _ = self.snapshot()
        return {"success": ready, "message": detail} if ready else {"success": False, "error": detail}

    def _explain(self, exc: Exception) -> str:
        return explain_open_error(self._port(), exc)