# VenPOS Bridge

Servidor HTTP local que actúa como middleware entre la app web **VenPOS** y las impresoras fiscales venezolanas homologadas por SENIAT.

Corre en `http://127.0.0.1:8765` en la PC donde está conectada la impresora.

---

## Impresoras soportadas

| Marca     | Modelos                                 | Driver         |
|-----------|-----------------------------------------|----------------|
| HKA       | 80H, 110H, Hasar 715F, 330F             | `hka.py`       |
| NCR       | 2008, 2010, 7197                        | `ncr.py`       |
| Bematech  | MP-4200 TH, MP-2500 TH, MP-F4000       | `bematech.py`  |
| ACLAS     | PP9A, PP7A, PP5A                        | `aclas.py`     |
| EPSON     | TM-T20X Fiscal, TM-T88VI Fiscal        | `epson_fiscal.py` |
| Datasym   | DS9300, DS9200                          | `datasym.py`   |
| Otro      | Cualquier impresora serial/texto plano  | `generic.py`   |

---

## Instalación rápida

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Correr el bridge
python bridge.py
```

El ícono verde aparecerá en la barra de tareas de Windows.

---

## Compilar como .exe (Windows)

```bat
build_exe.bat
```

El ejecutable queda en `dist\VenPOS-Bridge.exe`. No requiere Python instalado.

---

## Instalar como servicio de Windows (arranque automático)

```bat
install_service.bat
```

Requiere [NSSM](https://nssm.cc/download) en la carpeta o en el PATH.

---

## Endpoints HTTP (v1.1)

| Método | Ruta            | Descripción                                                        |
|--------|-----------------|--------------------------------------------------------------------|
| GET    | `/status`       | Estado del bridge + estado fiscal real (papel / doc abierto / Z)   |
| GET    | `/config`       | Leer configuración actual                                          |
| POST   | `/config`       | Actualizar configuración                                           |
| POST   | `/print/fiscal` | Imprimir factura / nota de entrega / ticket fiscal (payload JSON)  |
| POST   | `/print/ticket` | Imprimir ticket no fiscal (texto plano, automático, sin botón)     |
| POST   | `/print/test`   | Imprimir línea de prueba                                           |
| POST   | `/report/x`     | Reporte X — lectura parcial (no cierra la jornada)                 |
| POST   | `/report/z`     | Cierre Z — cierre de jornada fiscal (irreversible)                 |
| POST   | `/cancel-doc`   | Cancelar/abortar documento fiscal abierto (recuperación tras corte)|

### Respuesta de `/status`

```json
{
  "ok": true,
  "version": "1.1.0",
  "printer_ready": true,
  "printer_brand": "HKA",
  "port": "COM1",
  "fiscal": {
    "paper_ok": true,
    "doc_open": false,
    "z_pending": false,
    "printer_ready": true
  }
}
```

> Solo el driver HKA implementa `fiscal` con valores reales. Los demás devuelven `null` — la app lo muestra como "desconocido".

---

## Configuración (`config.json`)

```json
{
  "brand": "HKA",
  "model": "80H",
  "port": "COM1",
  "baud_rate": 9600,
  "data_bits": 8,
  "parity": "N",
  "stop_bits": 1,
  "timeout": 10,
  "encoding": "latin-1"
}
```

La configuración también puede actualizarse en vivo desde la app VenPOS (Configuración → Impresora Fiscal → Probar Conexión).

---

## Estructura del proyecto

```
venpos-bridge/
├── bridge.py              # Servidor HTTP principal
├── config.py              # Gestión de configuración
├── printer_manager.py     # Selector de drivers
├── tray.py                # Ícono en bandeja del sistema
├── requirements.txt
├── build_exe.bat          # Compilar a .exe
├── install_service.bat    # Instalar servicio Windows
└── drivers/
    ├── base.py            # Clase base abstracta
    ├── hka.py             # Driver HKA
    ├── ncr.py             # Driver NCR
    ├── bematech.py        # Driver Bematech
    ├── aclas.py           # Driver ACLAS
    ├── epson_fiscal.py    # Driver EPSON Fiscal
    ├── datasym.py         # Driver Datasym
    └── generic.py         # Driver genérico (texto plano)
```

---

## Notas de desarrollo

- Cada driver implementa `print_fiscal_invoice(payload)` y `print_test()`.
- Los protocolos de HKA y Bematech están basados en sus manuales técnicos oficiales.
- Para agregar soporte a una nueva marca: crear `drivers/nueva_marca.py` heredando `BaseFiscalDriver` y registrarlo en `printer_manager.py`.
- El puente usa CORS abierto (`*`) ya que solo escucha en `127.0.0.1`.
