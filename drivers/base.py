import serial, logging
from abc import ABC, abstractmethod

log = logging.getLogger('FiscalDriver')

class BaseFiscalDriver(ABC):
    def __init__(self, config):
        self.config = config

    def _open_port(self):
        return serial.Serial(
            port=self.config.port or 'COM1',
            baudrate=int(self.config.baud_rate or 9600),
            bytesize=int(self.config.data_bits or 8),
            parity=str(self.config.parity or 'N'),
            stopbits=int(self.config.stop_bits or 1),
            timeout=float(self.config.timeout or 10),
        )

    def _close_port(self, conn):
        try:
            if conn and conn.is_open: conn.close()
        except Exception: pass

    def check_connection(self):
        try:
            conn = self._open_port()
            self._close_port(conn)
            return True, 'Puerto ' + str(self.config.port) + ' OK'
        except serial.SerialException as e:
            return False, 'Error: ' + str(e)

    @staticmethod
    def _truncate(text, max_len):
        return (text or '')[:max_len]

    @abstractmethod
    def print_fiscal_invoice(self, payload: dict) -> dict: pass

    def print_test(self) -> dict:
        return {'success': True, 'message': 'Test no implementado'}