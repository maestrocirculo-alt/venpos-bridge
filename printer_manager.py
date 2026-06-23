import logging
from drivers.hka import HKADriver
from drivers.ncr import NCRDriver
from drivers.bematech import BematechDriver
from drivers.aclas import ACLASDriver
from drivers.epson_fiscal import EpsonFiscalDriver
from drivers.datasym import DatasymDriver
from drivers.generic import GenericDriver

log = logging.getLogger('PrinterManager')
DRIVERS = {'HKA': HKADriver, 'NCR': NCRDriver, 'Bematech': BematechDriver,
           'ACLAS': ACLASDriver, 'EPSON': EpsonFiscalDriver, 'Datasym': DatasymDriver, 'Custom': GenericDriver}

class PrinterManager:
    def __init__(self, config):
        self.config = config
        self._driver = self._load_driver()

    def _load_driver(self):
        cls = DRIVERS.get(self.config.brand or 'HKA', GenericDriver)
        log.info(f'Driver: {cls.__name__}')
        return cls(self.config)

    def reload(self, config):
        self.config = config
        self._driver = self._load_driver()

    def check_printer(self):
        try:
            return self._driver.check_connection()
        except Exception as e:
            return False, str(e)

    def print_fiscal(self, payload):
        try:
            return self._driver.print_fiscal_invoice(payload)
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def print_test(self):
        try:
            return self._driver.print_test()
        except Exception as e:
            return {'success': False, 'error': str(e)}