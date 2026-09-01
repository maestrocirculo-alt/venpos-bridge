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
| POST   | `/print/test`   | Imprimir línea de prueba                                           |
| POST   | `/report/x`     | Reporte X — lectura parcial (no cierra la jornada)                 |
| POST   | `/report/z`     | Cierre Z — cierre de jornada fiscal (irreversible)                 |
| POST   | `/cancel-doc`   | Cancelar/abortar documento fiscal abierto (recuperación tras corte)|

### Respuesta de `/status` (v1.1)

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

> Solo el driver HKA implementa `fiscal` con valores reales. Los demás drivers devuelven `null` en los campos — la app lo muestra como "desconocido".

---

## Payload `/print/fiscal`

```json
{
  "tipo_documento": "factura",
  "numero_control": "00-00000001",
  "numero_factura": "00000001",
  "emisor": {
    "razon_social": "Mi Negocio C.A.",
    "rif": "J-12345678-9",
    "direccion": "Av. Principal, Local 1",
    "telefono": "0414-1234567"
  },
  "receptor": {
    "nombre": "CONSUMIDOR FINAL",
    "rif": "V-00000000",
    "direccion": ""
  },
  "items": [
    {
      "description": "Producto ejemplo",
      "quantity": 2,
      "unit_price": 5.00,
      "subtotal": 10.00,
      "tax_rate": 16,
      "unit": "UND"
    }
  ],
  "subtotal": 10.00,
  "base_imponible": 10.00,
  "alicuota_iva": 16,
  "monto_iva": 1.60,
  "descuento": 0,
  "total": 11.60,
  "total_ves": 422.48,
  "tasa_bcv": 36.42,
  "pagos": [
    { "method": "cash_usd", "amount": 11.60, "currency": "USD" }
  ],
  "printer": {
    "brand": "HKA",
    "model": "80H",
    "port": "COM1",
    "baud_rate": 9600
  },
  "fecha_hora": "2026-06-23T15:30:00",
  "cajero": "Maria Perez"
}
```

**Respuesta exitosa:**
```json
{
  "success": true,
  "numero_control": "00-00000001",
  "numero_factura": "00000001"
}
```

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

## Impresoras térmicas USB (tickets no fiscales)

Las impresoras térmicas conectadas por **USB** (Xprinter, EPSON TM-T20, Bematech, etc.) **NO son puertos serie**: Windows las instala como impresoras normales. Para imprimir tickets no fiscales automáticamente (sin la ventana del navegador), el Bridge usa el **spooler de Windows** (`win32print`):

1. Instala la impresora térmica en **Windows → Configuración → Dispositivos → Impresoras y escáneres**.
2. En la app VenPOS ve a **Configuración → Impresión de Ticket**, selecciona **"USB (impresora de Windows)"** como tipo de conexión.
3. En el campo **"Nombre exacto de la impresora en Windows"** escribe el nombre tal cual aparece en Windows (ej: `XP-5890K`, `EPSON TM-T20II`, `Xprinter XP-350C`).
4. Pulsa **Probar conexión** (el Bridge validará que la impresora exista) y luego **Guardar**.

> Requiere `pywin32` (incluido en `requirements.txt` para Windows). El Bridge envía los bytes ESC/POS crudos a esa impresora como un trabajo RAW, así no abre cuadros de diálogo.

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
├── config.json            # (auto-generado)
├── venpos_bridge.log      # (auto-generado)
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