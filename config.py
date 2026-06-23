import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

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
}


class BridgeConfig:
    def __init__(self):
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self._data.update(saved)
            except Exception:
                pass

    def save(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def update(self, data: dict):
        for k, v in data.items():
            if k in DEFAULTS or k in ("brand", "model", "port", "baud_rate", "encoding"):
                self._data[k] = v

    def to_dict(self) -> dict:
        return dict(self._data)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._data.get(name)
