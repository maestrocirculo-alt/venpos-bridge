"""
Diagnóstico del VenPOS Bridge.

En vez de suponer por qué una impresora "no conecta", prueba el handshake real
del protocolo (ENQ 0x05) y reporta EXACTAMENTE qué bytes vuelven, en qué puerto
y con qué parámetros seriales. El resultado es un informe de texto que el dueño
puede copiar y enviar a soporte.
"""

import os
import platform
import sys
import time
from datetime import datetime

from drivers.hka_protocol import (
    ENQ, SERIAL_LABEL, decode_status, explain_open_error, extract_frame, hexs, port_lock,
)


def list_serial_ports():
    try:
        from serial.tools import list_ports
        return [{"device": p.device, "description": p.description or "", "hwid": p.hwid or ""}
                for p in sorted(list_ports.comports(), key=lambda x: x.device)]
    except Exception as e:
        return [{"device": "?", "description": f"No se pudo listar puertos: {e}", "hwid": ""}]


def list_windows_printers():
    try:
        import win32print  # type: ignore
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return [p[2] for p in win32print.EnumPrinters(flags)]
    except Exception:
        return []


def raw_enq(port: str, baud: int, parity: str, listen: float = 1.2) -> dict:
    """Abre el puerto con los parámetros dados, envía ENQ y devuelve lo recibido (en hex)."""
    res = {"port": port, "baud": baud, "parity": parity, "opened": False, "rx_hex": "", "valid": False}
    try:
        import serial
        par = {"E": serial.PARITY_EVEN, "N": serial.PARITY_NONE}[parity]
        conn = serial.Serial(port=port, baudrate=baud, bytesize=serial.EIGHTBITS, parity=par,
                             stopbits=serial.STOPBITS_ONE, timeout=0.1, write_timeout=2)
    except Exception as e:
        res["error"] = explain_open_error(port, e)
        return res
    try:
        res["opened"] = True
        conn.reset_input_buffer()
        conn.write(bytes([ENQ]))
        conn.flush()
        buf = bytearray()
        end = time.time() + listen
        while time.time() < end:
            chunk = conn.read(conn.in_waiting or 1)
            if chunk:
                buf.extend(chunk)
                if extract_frame(bytes(buf)):
                    break
        res["rx_hex"] = hexs(buf)
        fr = extract_frame(bytes(buf))
        if fr and len(fr[0]) >= 2:
            st = decode_status(fr[0][0], fr[0][1])
            res["valid"] = st["valid"]
            res["status_text"] = st["text"]
    except Exception as e:
        res["error"] = str(e)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return res


def run_diagnostics(config, version: str, scan: bool = False) -> dict:
    """Toma el puerto de forma exclusiva mientras prueba (si el Bridge está imprimiendo, lo informa)."""
    lock = port_lock(config.port or "COM1")
    got = lock.acquire(blocking=False)
    try:
        return _diagnose(config, version, scan, busy=not got)
    finally:
        if got:
            lock.release()


def _diagnose(config, version: str, scan: bool, busy: bool) -> dict:
    port = config.port or "COM1"
    ports = list_serial_ports()
    lines = [
        f"VenPOS Bridge v{version} — Diagnóstico",
        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Sistema: {platform.platform()} · Python {sys.version.split()[0]} · {'compilado' if getattr(sys, 'frozen', False) else 'script'}",
        f"Perfil fiscal: {config.brand} {config.model} en {port}",
        f"Perfil tickets: " + (f"{config.ticket.brand or 'ESC/POS'} · puerto {config.ticket.port}"
                               + (f" · Windows «{config.ticket.printer_name}»" if config.ticket.printer_name else "")
                               if config.ticket.configured else "no configurado"),
        "Puertos COM en esta PC: " + (", ".join(f"{p['device']} ({p['description']})" for p in ports) or "ninguno"),
    ]
    wp = list_windows_printers()
    if wp:
        lines.append("Impresoras de Windows: " + ", ".join(wp))
    lines += ["", f"── Prueba de comunicación (ENQ) — el fabricante exige {SERIAL_LABEL} ──"]

    attempts = []
    primary = None

    if busy:
        lines.append(f"{port}: el Bridge está usando la impresora en este momento (operación en curso). Vuelve a intentar en unos segundos.")
    else:
        primary = raw_enq(port, 9600, "E")
        attempts.append(primary)
        if primary.get("error"):
            lines.append(f"{port} 9600 8E1: {primary['error']}")
        elif primary["rx_hex"]:
            lines.append(f"{port} 9600 8E1: RESPONDE [{primary['rx_hex']}] → {primary.get('status_text', 'trama no reconocida')}")
        else:
            lines.append(f"{port} 9600 8E1: sin respuesta")

        # Si el puerto abre pero calla, probar otras velocidades/paridades solo para diagnosticar
        if primary.get("opened") and not primary["valid"]:
            for baud in (9600, 19200, 38400, 57600, 115200):
                for parity in ("E", "N"):
                    if baud == 9600 and parity == "E":
                        continue
                    r = raw_enq(port, baud, parity, listen=0.8)
                    attempts.append(r)
                    tag = "RESPONDE" if r["rx_hex"] else "sin respuesta"
                    lines.append(f"{port} {baud} 8{parity}1: {tag}" + (f" [{r['rx_hex']}]" if r["rx_hex"] else ""))

    detected = None
    if scan and not busy:
        lines += ["", "── Búsqueda en los demás puertos COM (9600 8E1) ──"]
        for p in ports:
            dev = p["device"]
            if dev in ("?", port):
                continue
            r = raw_enq(dev, 9600, "E", listen=1.0)
            attempts.append(r)
            if r.get("valid"):
                detected = dev
                lines.append(f"{dev} ({p['description']}): ¡LA IMPRESORA ESTÁ AQUÍ! → {r.get('status_text')}")
            elif r.get("error"):
                lines.append(f"{dev}: {r['error']}")
            else:
                lines.append(f"{dev} ({p['description']}): sin respuesta")

    # ── Conclusión ────────────────────────────────────────────────────────────
    if busy:
        conclusion = "La impresora está ocupada con otra operación del Bridge."
    elif primary and primary.get("valid"):
        conclusion = f"✓ La impresora responde correctamente en {port} ({primary.get('status_text')})."
    elif detected:
        conclusion = f"La impresora NO está en {port}: responde en {detected}. Cambia el puerto a {detected} en Configuración → Fiscal y guarda."
    elif primary and primary.get("error"):
        conclusion = primary["error"]
    else:
        other = [a for a in attempts if a.get("rx_hex") and not (a["baud"] == 9600 and a["parity"] == "E")]
        if other:
            a = other[0]
            conclusion = (f"La impresora contesta a {a['baud']} bps / paridad {a['parity']}, pero el protocolo exige {SERIAL_LABEL}. "
                          "Hay que reconfigurar el puerto serial de la impresora.")
        else:
            conclusion = (f"{port} abre, pero la impresora no contesta. Revisa: 1) que esté encendida, "
                          "2) el cable serial (algunos equipos requieren cable cruzado/null-modem) o el adaptador USB-Serial, "
                          "3) que el número de COM sea el de la impresora (Administrador de dispositivos → Puertos). "
                          "Pulsa «Buscar en todos los puertos» para probar los demás COM.")
    lines += ["", "CONCLUSIÓN: " + conclusion, "", f"Config: {getattr(config, 'to_dict', lambda: {})().get('config_file', '')}"]

    return {
        "ok": True, "version": version, "port": port, "busy": busy,
        "printer_responding": bool(primary and primary.get("valid")),
        "detected_port": detected, "conclusion": conclusion,
        "ports": ports, "attempts": attempts, "report_text": "\n".join(lines),
    }