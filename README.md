# VenPOS Bridge v5.0

Servidor HTTP local (`http://127.0.0.1:8765`) que conecta VenPOS con la impresora fiscal y la impresora térmica de tickets de la misma PC.

## Instalar (lo más fácil)

Descarga el `.exe` ya compilado (siempre la última versión):

https://github.com/maestrocirculo-alt/venpos-bridge/releases/latest/download/VenPOS-Bridge.exe

1. Si tienes un Bridge anterior abierto: ícono verde junto al reloj → **Detener Bridge**.
2. Ejecuta `VenPOS-Bridge.exe`. Crea `config.json` y `venpos_bridge.log` en su misma carpeta.
3. En VenPOS: **Configuración → Fiscal** → *Probar Conexión*. Debe decir **v5.0.0**.

Si algo falla, usa **Diagnóstico** en esa misma pantalla y copia el informe.

## Impresoras fiscales HKA / ACLAS (PP9-PLUS, PP9A, HKA80...)

Hablan el **protocolo directo de The Factory HKA** (Manual de Protocolos y Comandos V8.5.0), implementado en `drivers/hka_protocol.py`:

| Dato | Valor (del manual) |
|---|---|
| Puerto serial | 9600 bps · 8 bits · **paridad PAR** · 1 stop |
| Trama | `STX(02)` + DATA + `ETX(03)` + `LRC` (XOR de DATA y ETX) |
| Estado | `ENQ (05)` → `STX STS1 STS2 ETX LRC` |
| Respuesta a un comando | `ACK (06)` / `NAK (15)` |
| Reporte X / Cierre Z | `I0X` / `I0Z` (el Z tarda ~20 s) |
| Anular documento | `7` |

El Bridge **no da nada por conectado hasta recibir la respuesta real de la impresora** (ENQ). "El puerto abre" ya no significa "conectada".

## Dos impresoras, dos perfiles

- **fiscal**: la impresora fiscal (Configuración → Fiscal).
- **ticket**: la térmica de tickets (Configuración → Tickets). Si tiene nombre de impresora de Windows, imprime por el spooler y **no usa el COM** de la fiscal.

Cada pantalla guarda solo su perfil; ya no se pisan.

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/status` | versión, estado fiscal (ENQ) y estado de la térmica |
| GET | `/diagnose?scan=1` | informe de diagnóstico; `scan=1` prueba todos los COM |
| GET/POST | `/config` | leer / guardar (`{"profile":"fiscal"\|"ticket", ...}`) |
| POST | `/print/fiscal` | factura fiscal |
| POST | `/print/ticket` | ticket de texto en la térmica |
| POST | `/report/x` · `/report/z` | Reporte X · Cierre Z |
| POST | `/cancel-doc` | anular documento fiscal abierto |

## Compilar a mano (opcional)

`build_exe.bat` genera `dist\VenPOS-Bridge.exe`. El repositorio también lo compila solo en GitHub Actions en cada cambio.

## Otras marcas

NCR, Bematech, Epson Fiscal, Datasym y Genérica conservan sus drivers anteriores.