"""
PrinterManager — Selecciona el driver correcto según la marca configurada
y delega la impresión y operaciones fiscales (X, Z, cancelación, estado).
"""

import logging
from typing import Tuple

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


class PrinterManager:
    def __init__(self, config):
        self.config = config
        self._driver = self._load_driver()

    def _load_driver(self):
        brand = self.config.brand or "HKA"
        cls = DRIVERS.get(brand, GenericDriver)
        log.info(f"Cargando driver: {brand} ({cls.__name__})")
        return cls(self.config)

    def reload(self, config):
        self.config = config
        self._driver = self._load_driver()

    def check_printer(self) -> Tuple[bool, str]:
        try:
            return self._driver.check_connection()
        except Exception as e:
            return False, str(e)

    def print_fiscal(self, payload: dict) -> dict:
        try:
            return self._driver.print_fiscal_invoice(payload)
        except Exception as e:
            log.error(f"Error en print_fiscal: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def print_test(self) -> dict:
        try:
            return self._driver.print_test()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def print_text(self, text: str) -> dict:
        """Ticket no fiscal (texto plano) — comprobante informativo automático."""
        try:
            return self._driver.print_text(text)
        except Exception as e:
            log.error(f"Error en print_text: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # ── Mantenimiento fiscal ──────────────────────────────────────────────────
    def get_fiscal_status(self) -> dict:
        try:
            return self._driver.get_fiscal_status()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def print_report_x(self) -> dict:
        try:
            return self._driver.print_report_x()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def print_report_z(self) -> dict:
        try:
            return self._driver.print_report_z()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cancel_document(self) -> dict:
        try:
            return self._driver.cancel_document()
        except Exception as e:
            return {"success": False, "error": str(e)}