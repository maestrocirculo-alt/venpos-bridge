"""
PrinterManager — Selecciona el driver correcto según la marca configurada
y delega la impresión y operaciones fiscales (X, Z, cancelación, estado).

Maneja dos perfiles independientes (ver config.py):
  fiscal  -> impresora fiscal
  ticket  -> impresora térmica de tickets no fiscales
"""

import logging
from typing import Optional, Tuple

from drivers.hka import HKADriver
from drivers.ncr import NCRDriver
from drivers.bematech import BematechDriver
from drivers.aclas import ACLASDriver
from drivers.epson_fiscal import EpsonFiscalDriver
from drivers.datasym import DatasymDriver
from drivers.generic import GenericDriver

log = logging.getLogger("PrinterManager")

DRIVERS = {
    "HKA":      HKADriver,
    "NCR":      NCRDriver,
    "Bematech": BematechDriver,
    "ACLAS":    ACLASDriver,
    "EPSON":    EpsonFiscalDriver,
    "Datasym":  DatasymDriver,
    "Custom":   GenericDriver,
}

# Marcas que hablan el protocolo fiscal HKA: NO sirven para imprimir texto ESC/POS
PROTOCOL_BRANDS = ("HKA", "ACLAS")


def _make_driver(cfg, default_brand: str):
    brand = cfg.brand or default_brand
    cls = DRIVERS.get(brand, GenericDriver)
    log.info(f"Cargando driver: {brand} ({cls.__name__})")
    return cls(cfg)


class PrinterManager:
    def __init__(self, config):
        self.reload(config)

    def reload(self, config):
        self.config = config
        self._fiscal = _make_driver(config, "HKA")
        self._ticket = _make_driver(config.ticket, "Custom") if config.ticket.configured else None

    # ── Perfil fiscal ─────────────────────────────────────────────────────────
    def fiscal_snapshot(self):
        """(ready, detail, fiscal_dict) — un solo acceso a la impresora."""
        drv = self._fiscal
        try:
            if hasattr(drv, "snapshot"):
                return drv.snapshot()
            ready, detail = drv.check_connection()
            return ready, detail, drv.get_fiscal_status()
        except Exception as e:
            return False, str(e), {"success": False, "error": str(e)}

    def check_printer(self) -> Tuple[bool, str]:
        try:
            return self._fiscal.check_connection()
        except Exception as e:
            return False, str(e)

    def print_fiscal(self, payload: dict) -> dict:
        try:
            return self._fiscal.print_fiscal_invoice(payload)
        except Exception as e:
            log.error(f"Error en print_fiscal: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def print_test(self) -> dict:
        try:
            return self._fiscal.print_test()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_fiscal_status(self) -> dict:
        try:
            return self._fiscal.get_fiscal_status()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def print_report_x(self) -> dict:
        try:
            return self._fiscal.print_report_x()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def print_report_z(self) -> dict:
        try:
            return self._fiscal.print_report_z()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cancel_document(self) -> dict:
        try:
            return self._fiscal.cancel_document()
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Perfil de tickets (térmica, texto plano) ──────────────────────────────
    def _ticket_driver(self) -> Optional[object]:
        if self._ticket is not None:
            return self._ticket
        # Compatibilidad: apps viejas empujaban la térmica como "fiscal". Solo se
        # acepta si esa marca NO es una impresora fiscal de protocolo HKA.
        if (self.config.brand or "") not in PROTOCOL_BRANDS and self.config.brand in DRIVERS:
            return self._fiscal
        return None

    def ticket_status(self) -> dict:
        drv = self._ticket_driver()
        if drv is None:
            return {"configured": False, "ready": False,
                    "detail": "No hay impresora de tickets configurada en el Bridge (Configuración → Tickets)."}
        try:
            ok, detail = drv.check_connection()
            return {"configured": True, "ready": bool(ok), "detail": detail,
                    "source": "ticket" if drv is self._ticket else "fiscal"}
        except Exception as e:
            return {"configured": True, "ready": False, "detail": str(e)}

    def print_text(self, text: str, logo_url: str = "") -> dict:
        """Ticket no fiscal (texto plano) — comprobante informativo automático."""
        drv = self._ticket_driver()
        if drv is None:
            return {"success": False, "code": "NO_TICKET_PRINTER",
                    "error": "No hay impresora de tickets configurada en el Bridge. "
                             "Configúrala en Configuración → Tickets y guarda."}
        try:
            return drv.print_text(text, logo_url)
        except Exception as e:
            log.error(f"Error en print_text: {e}", exc_info=True)
            return {"success": False, "error": str(e)}