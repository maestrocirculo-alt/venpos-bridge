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
pip install -r requirements.txt
python bridge.py
```

El ícono verde aparecerá en la barra de tareas de Windows.

---

## Compilar como .exe (Windows)

```bat
build_exe.bat
```

El ejecutable queda en `dist\VenPOS-Bridge.exe`. No requiere Python instalado.

> v2.0.0 incluye `pywin32` empaquetado para impresoras térmicas USB.

---

## Endpoints HTTP (v2.0)

| Método | Ruta            | Descripción                                                        |
|--------|-----------------|--------------------------------------------------------------------|
| GET    | `/status`       | Estado del bridge + estado fiscal real (papel / doc abierto / Z)   |
| GET    | `/config`       | Leer configuración actual                                          |
| POST   | `/config`       | Actualizar configuración                                           |
| POST   | `/print/fiscal` | Imprimir factura / nota de entrega / ticket fiscal (payload JSON)  |
| POST   | `/print/ticket` | Imprimir ticket no fiscal (texto plano, automático, sin navegador) |
| POST   | `/print/test`   | Imprimir línea de prueba                                           |
| POST   | `/report/x`     | Reporte X — lectura parcial (no cierra la jornada)                 |
| POST   | `/report/z`     | Cierre Z — cierre de jornada fiscal (irreversible)                 |
| POST   | `/cancel-doc`   | Cancelar/abortar documento fiscal abierto (recuperación tras corte)|

---

## Impresoras térmicas USB (tickets no fiscales)

Las impresoras térmicas conectadas por **USB** NO son puertos serie: Windows las instala como impresoras normales. Para imprimir tickets no fiscales automáticamente (sin la ventana del navegador), el Bridge usa el **spooler de Windows** (`win32print`):

1. Instala la impresora térmica en **Windows → Configuración → Impresoras y escáneres**.
2. En la app VenPOS ve a **Configuración → Impresión**, selecciona **USB (impresora de Windows)**.
3. En el campo **Nombre exacto de la impresora en Windows** escribe el nombre tal cual aparece en Windows.
4. Pulsa **Probar conexión** y luego **Guardar**.

> Requiere `pywin32` (incluido en `requirements.txt` y empaquetado en el .exe v2.0.0).
