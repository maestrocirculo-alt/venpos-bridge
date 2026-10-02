"""
Gestión de configuración del VenPOS Bridge.

Guarda/lee config.json junto al ejecutable. Desde la v5.0 el Bridge maneja DOS
perfiles independientes:

  * fiscal  — la impresora fiscal (HKA / ACLAS / NCR / ...). Vive en el nivel raíz
              del JSON (compatible con configs de versiones anteriores).
  * ticket  — la impresora térmica de tickets no fiscales (ESC/POS). Vive en "ticket".

Antes había un solo perfil y cada pantalla de la app (Fiscal / Tickets) pisaba la
configuración de la otra.
"""

import json
import os
import sys


def _base_dir() -> str:
    """
    Carpeta donde guardar config.json y logs.
    Si el programa está compilado con PyInstaller (--onefile), __file__ apunta
    a una carpeta temporal _MEIxxxx que se borra al cerrar. Usamos la carpeta
    del ejecutable real (sys.executable) para que la config persista.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(_base_dir(), "config.json")

DEFAULTS = {
    "brand": "HKA",
    "model": "80H",
    "port": "COM1",
    "baud_rate": 9600,
    "data_bits": 8,
    "parity": "N",
    "stop_bits": 1,
    "timeout": 10,
    "encoding": "latin-1",
    "printer_name": "",  # Nombre exacto de la impresora en Windows (térmicas USB)
}

TICKET_DEFAULTS = dict(DEFAULTS, brand="", model="", port="USB")

# Solo perfil fiscal: ajustes finos del protocolo (ver drivers/hka_fiscal.py)
FISCAL_EXTRAS = {
    "item_desc_len": 20,   # largo máximo de la descripción del ítem
    "payment_map": {},     # {"cash_ves": 1, "zelle": 21, ...} -> medio de pago de la impresora
    "tax_map": {},         # {"16": "!", "8": "\"", ...} -> comando del ítem por tasa
}

_ALLOWED = ("brand", "model", "port", "baud_rate", "encoding", "printer_name")


class ProfileConfig:
    """Acceso por atributo (config.port, config.brand, ...) sobre un dict."""

    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._data.get(name)

    def to_dict(self) -> dict:
        return dict(self._data)

    @property
    def configured(self) -> bool:
        return bool(self._data.get("brand") or self._data.get("printer_name"))


class BridgeConfig(ProfileConfig):
    def __init__(self):
        super().__init__(dict(DEFAULTS, **FISCAL_EXTRAS))
        self._ticket = dict(TICKET_DEFAULTS)
        self.load()

    @property
    def ticket(self) -> ProfileConfig:
        return ProfileConfig(self._ticket)

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._ticket.update(saved.pop("ticket", {}) or {})
                self._data.update(saved)
            except Exception:
                pass

    def save(self):
        data = dict(self._data)
        data["ticket"] = dict(self._ticket)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def update(self, data: dict, profile: str = "fiscal"):
        target = self._ticket if profile == "ticket" else self._data
        allowed = _ALLOWED if profile == "ticket" else _ALLOWED + tuple(FISCAL_EXTRAS)
        for k, v in data.items():
            if k not in allowed:
                continue
            if k == "baud_rate":
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    continue
            target[k] = v

    def to_dict(self) -> dict:
        d = dict(self._data)
        d["ticket"] = dict(self._ticket)
        d["config_file"] = CONFIG_FILE
        return d