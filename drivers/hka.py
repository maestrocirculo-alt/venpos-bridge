"""
Driver HKA — HKA80, HKA112 y equipos compatibles de The Factory HKA.

Protocolo directo del "Manual de Protocolos y Comandos V8.5.0".
Toda la lógica vive en hka_fiscal.py / hka_protocol.py.
"""

from .hka_fiscal import HKAFiscalDriver


class HKADriver(HKAFiscalDriver):
    NAME = "HKA"