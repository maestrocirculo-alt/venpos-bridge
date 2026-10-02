"""
Protocolo serial DIRECTO de The Factory HKA (impresoras HKA80, HKA112, SRP-812,
DT-230, PP9 y ACLAS PP9-PLUS).

Fuente: "Manual de Protocolos y Comandos V8.5.0 - Venezuela" (The Factory HKA, 23/08/2022).
Todo lo que hay en este archivo sale de ese manual — nada se asume:

  * Puerto serial (Tabla 3):      9600 bps, 8 bits de datos, paridad PAR, 1 bit de stop.
  * Trama (sección 8):            STX(0x02) + DATA + ETX(0x03) + LRC
  * LRC:                          XOR de todos los bytes de DATA y ETX (STX no cuenta).
                                  Ejemplo del manual: "I0X" -> 02 49 30 58 03 22
  * Caracteres de control:        ENQ 0x05 (pedir estado), ACK 0x06, NAK 0x15,
                                  ETB 0x17 (fin de bloque), EOT 0x04 (fin de transmisión)
  * ENQ:                          la impresora responde STX STS1 STS2 ETX LRC
  * Comando simple:               PC -> trama ; impresora -> ACK (ok) o NAK (error).
                                  Si está ocupada no responde nada.
  * Reporte X = "I0X", Reporte Z = "I0Z" (Tabla 59). El Z tarda ~20 s + 3 s.
"""

import logging
import threading
import time
import unicodedata

log = logging.getLogger("HKA-PROTO")

STX, ETX, ENQ, ACK, NAK, ETB, EOT = 0x02, 0x03, 0x05, 0x06, 0x15, 0x17, 0x04

# Parámetros del puerto exigidos por el fabricante (Tabla 3 del manual)
SERIAL_BAUD = 9600
SERIAL_LABEL = "9600 bps, 8 bits, paridad PAR, 1 stop (8E1)"


# ── Utilidades de trama ───────────────────────────────────────────────────────
def lrc(data: bytes) -> int:
    """XOR entre DATA y ETX (incluyendo ETX), según el manual."""
    v = ETX
    for b in data:
        v ^= b
    return v


def build_frame(data) -> bytes:
    raw = bytes(data) if isinstance(data, (bytes, bytearray)) else str(data).encode("latin-1", errors="replace")
    return bytes([STX]) + raw + bytes([ETX, lrc(raw)])


def hexs(b) -> str:
    return " ".join(f"{x:02X}" for x in bytes(b))


def extract_frame(buf: bytes):
    """
    Busca una trama completa STX ... (ETX|ETB) LRC dentro de buf.
    Devuelve (data, terminador, lrc_ok, bytes_consumidos) o None si está incompleta.
    """
    i = buf.find(bytes([STX]))
    if i < 0:
        return None
    for j in range(i + 1, len(buf)):
        if buf[j] in (ETX, ETB):
            if j + 1 >= len(buf):
                return None  # falta el LRC
            data = bytes(buf[i + 1:j])
            x = buf[j]
            for b in data:
                x ^= b
            return data, buf[j], (x == buf[j + 1]), j + 2
    return None


def clean_text(text, max_len: int) -> str:
    """ASCII imprimible (sin acentos): la tabla de caracteres de la impresora no es Unicode."""
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = "".join(ch for ch in s if 32 <= ord(ch) < 127)
    return s.strip()[:max_len]


# ── Estado (Tablas 7 y 8 del manual) ──────────────────────────────────────────
_STS1_KNOWN = {0x40, 0x41, 0x42, 0x60, 0x61, 0x62, 0x68, 0x69, 0x6A}
_STS2_TEXT = {
    0x40: None,
    0x48: "Error de gaveta",
    0x41: "Sin papel",
    0x42: "Error mecánico de la impresora / papel",
    0x43: "Error mecánico y fin de papel",
    0x60: "Error fiscal (si lleva más de 24 h abierta, emite el Cierre Z)",
    0x64: "Error en la memoria fiscal",
    0x6C: "Memoria fiscal llena",
}
_STS2_BLOCKING = {0x41, 0x42, 0x43, 0x60, 0x64, 0x6C}


def decode_status(sts1: int, sts2: int) -> dict:
    valid = sts1 in _STS1_KNOWN
    fiscal_mode = bool(sts1 & 0x20)
    in_fiscal_tx = bool(sts1 & 0x01)
    in_nonfiscal_tx = bool(sts1 & 0x02)
    mf_full = bool(sts1 & 0x08)
    idle = valid and not in_fiscal_tx and not in_nonfiscal_tx
    err_text = _STS2_TEXT.get(sts2, f"Error desconocido (0x{sts2:02X})")
    blocking = sts2 in _STS2_BLOCKING or sts2 not in _STS2_TEXT
    paper_ok = sts2 not in (0x41, 0x43)

    if not valid:
        text = f"Respuesta no válida de la impresora (STS1=0x{sts1:02X})"
    else:
        parts = ["Modo fiscal" if fiscal_mode else "Modo entrenamiento (no fiscal)"]
        if in_fiscal_tx:
            parts.append("documento fiscal abierto")
        elif in_nonfiscal_tx:
            parts.append("documento no fiscal abierto")
        else:
            parts.append("en espera")
        if mf_full:
            parts.append("memoria fiscal llena")
        if err_text:
            parts.append(err_text)
        text = " · ".join(parts)

    return {
        "valid": valid,
        "sts1": sts1, "sts2": sts2,
        "fiscal_mode": fiscal_mode,
        "training_mode": valid and not fiscal_mode,
        "in_fiscal_tx": in_fiscal_tx,
        "in_nonfiscal_tx": in_nonfiscal_tx,
        "mf_full": mf_full,
        "idle": idle,
        "paper_ok": paper_ok,
        "error_text": err_text,
        "blocking_error": blocking,
        "ready": idle and not blocking,
        "text": text,
    }


# ── Status S1 (Tabla 45, impresoras PP9 / ACLAS PP9-PLUS) ─────────────────────
def parse_s1(data: str) -> dict:
    """
    Extrae campos del status S1 usando los offsets del manual (protocolo directo,
    con separadores). Si la trama viene sin separadores se usan los offsets de librería.
    Devuelve solo lo que pudo validar como numérico; nunca inventa valores.
    """
    out = {"raw": data}
    if len(data) >= 129:
        offs = {"last_invoice": (23, 31), "z_counter": (83, 87), "rif": (93, 104), "serial": (105, 115)}
    elif len(data) >= 113:
        offs = {"last_invoice": (21, 29), "z_counter": (73, 77), "rif": (81, 92), "serial": (92, 102)}
    else:
        return out
    for key, (a, b) in offs.items():
        val = data[a:b].strip()
        if key in ("last_invoice", "z_counter"):
            if val.isdigit():
                out[key] = val
        elif val:
            out[key] = val
    return out


# ── Errores ───────────────────────────────────────────────────────────────────
class PrinterBusy(Exception):
    """El puerto está siendo usado por otra operación del propio Bridge."""


def explain_open_error(port: str, exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "permissionerror" in low or "access is denied" in low or "acceso denegado" in low or "(13," in msg:
        return (f"El puerto {port} está ocupado por otro programa (otra copia del VenPOS Bridge, "
                f"el software de la impresora u otro sistema). Ciérralo y vuelve a intentar.")
    if "filenotfounderror" in low or "no such file" in low or "(2," in msg or "cannot find" in low or "no puede encontrar" in low:
        return (f"El puerto {port} no existe en esta PC. Abre el Administrador de dispositivos → "
                f"Puertos (COM y LPT) y mira qué número tiene la impresora.")
    return f"No se pudo abrir {port}: {msg}"


# ── Puerto serial: un solo uso a la vez por puerto ────────────────────────────
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def port_lock(port: str):
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(str(port).upper(), threading.RLock())


class HKASession:
    """
    Conexión abierta a la impresora. Uso:

        with HKASession("COM3") as s:
            st = s.enq()
            r = s.command("I0X")     # 'ACK' | 'NAK' | None (sin respuesta)

    wait = segundos máximos esperando que otra operación suelte el puerto
    (0 = no esperar: lanza PrinterBusy de inmediato).
    """

    opener = None  # hook para pruebas: callable(port, baud) -> objeto tipo serial.Serial

    def __init__(self, port: str, baud: int = SERIAL_BAUD, wait: float = 120.0, parity: str = "E"):
        self.port, self.baud, self.wait, self.parity = port, baud, wait, parity
        self.conn = None
        self._lock = port_lock(port)
        self._locked = False

    def __enter__(self):
        if self.wait and self.wait > 0:
            self._locked = self._lock.acquire(timeout=self.wait)
        else:
            self._locked = self._lock.acquire(blocking=False)
        if not self._locked:
            raise PrinterBusy(self.port)
        try:
            self._open()
        except Exception:
            self._release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            if self.conn is not None:
                self.conn.close()
        except Exception:
            pass
        self.conn = None
        self._release()

    def _release(self):
        if self._locked:
            self._locked = False
            self._lock.release()

    def _open(self):
        if HKASession.opener:
            self.conn = HKASession.opener(self.port, self.baud)
            return
        import serial
        parity = {"E": serial.PARITY_EVEN, "N": serial.PARITY_NONE, "O": serial.PARITY_ODD}[self.parity]
        self.conn = serial.Serial(
            port=self.port, baudrate=self.baud, bytesize=serial.EIGHTBITS,
            parity=parity, stopbits=serial.STOPBITS_ONE,
            timeout=0.1, write_timeout=3,
        )
        log.info(f"Puerto {self.port} abierto ({self.baud} 8{self.parity}1)")

    # ── E/S de bajo nivel ─────────────────────────────────────────────────────
    def _flush_in(self):
        try:
            self.conn.reset_input_buffer()
        except Exception:
            pass

    def _write(self, data: bytes):
        log.info("TX %s", hexs(data))
        self.conn.write(data)
        try:
            self.conn.flush()
        except Exception:
            pass

    def _read_chunk(self) -> bytes:
        n = 0
        try:
            n = self.conn.in_waiting
        except Exception:
            pass
        return self.conn.read(n or 1)

    def _read_until(self, done, timeout: float) -> bytes:
        buf = bytearray()
        end = time.time() + timeout
        while time.time() < end:
            chunk = self._read_chunk()
            if chunk:
                buf.extend(chunk)
                if done(bytes(buf)):
                    break
        if buf:
            log.info("RX %s", hexs(buf))
        return bytes(buf)

    # ── Operaciones del protocolo ─────────────────────────────────────────────
    def enq(self, timeout: float = 2.0) -> dict:
        """ENQ -> STX STS1 STS2 ETX LRC. Es el 'handshake' real con la impresora."""
        self._flush_in()
        self._write(bytes([ENQ]))
        buf = self._read_until(lambda b: extract_frame(b) is not None, timeout)
        fr = extract_frame(buf)
        if not fr:
            return {"answered": bool(buf), "valid": False, "raw_hex": hexs(buf), "idle": False, "ready": False,
                    "text": "La impresora no respondió al ENQ" if not buf else f"Respuesta incompleta ({hexs(buf)})"}
        data, _term, lrc_ok, _n = fr
        if len(data) < 2:
            return {"answered": True, "valid": False, "raw_hex": hexs(buf), "idle": False, "ready": False,
                    "text": f"Respuesta de estado inesperada ({hexs(buf)})"}
        st = decode_status(data[0], data[1])
        st.update(answered=True, lrc_ok=lrc_ok, raw_hex=hexs(buf))
        return st

    def command(self, data, ack_timeout: float = 6.0):
        """Comando simple. Devuelve 'ACK', 'NAK' o None (sin respuesta: ocupada o mal configurada)."""
        self._flush_in()
        self._write(build_frame(data))
        buf = self._read_until(lambda b: (ACK in b) or (NAK in b), ack_timeout)
        for b in buf:
            if b == ACK:
                return "ACK"
            if b == NAK:
                return "NAK"
        return None

    def query(self, cmd, timeout: float = 4.0):
        """
        Comando de lectura (S1, SV, ...). Devuelve (resultado, texto) con resultado en
        'OK' | 'NAK' | 'NOACK' | 'NODATA'.
        """
        self._flush_in()
        self._write(build_frame(cmd))
        buf = bytearray()
        got_ack = False
        chunks = []
        end = time.time() + timeout
        while time.time() < end:
            new = self._read_chunk()
            if new:
                buf.extend(new)
            if not got_ack:
                for k, b in enumerate(buf):
                    if b == NAK:
                        log.info("RX %s", hexs(buf))
                        return "NAK", ""
                    if b == ACK:
                        got_ack = True
                        del buf[:k + 1]
                        break
            if got_ack:
                fr = extract_frame(bytes(buf))
                if fr:
                    data, term, _ok, consumed = fr
                    chunks.append(data)
                    del buf[:consumed]
                    if term == ETX:
                        break
                    self._write(bytes([ACK]))  # bloque ETB: pedir el siguiente
                elif chunks and EOT in buf:
                    break
        if chunks:
            return "OK", b"".join(chunks).decode("latin-1", errors="replace")
        return ("NODATA" if got_ack else "NOACK"), ""

    def wait_idle(self, timeout: float = 30.0, poll: float = 0.6):
        """Repite ENQ hasta que la impresora quede 'en espera'. Devuelve el último estado."""
        end = time.time() + timeout
        last = None
        while time.time() < end:
            last = self.enq(timeout=1.0)
            if last.get("valid") and last.get("idle"):
                return last
            time.sleep(poll)
        return last