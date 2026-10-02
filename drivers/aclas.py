"""
Driver ACLAS — PP9-PLUS, PP9A, PP7A, PP5A.

Son equipos de The Factory HKA: usan EXACTAMENTE el protocolo directo del
"Manual de Protocolos y Comandos V8.5.0" (la PP9-PLUS aparece en sus tablas).
Toda la lógica vive en hka_fiscal.py / hka_protocol.py.
"""

from .hka_fiscal import HKAFiscalDriver


class ACLASDriver(HKAFiscalDriver):
    NAME = "ACLAS"