# Referencia técnica

Detalle de opciones, configuración y reglas del Excel. Volver al [README](../README.md).

- [Línea de comandos](#línea-de-comandos)
- [Variables de configuración](#variables-de-configuración)
- [Parametría de negocio](#parametría-de-negocio)
- [Qué escribe el Excel de emisión](#qué-escribe-el-excel-de-emisión)
- [Hojas del reporte](#hojas-del-reporte)
- [Completitud y errores](#completitud-y-errores)
- [Planes soportados](#planes-soportados)
- [Flujo interno](#flujo-interno)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Alcance](#alcance)

---

## Línea de comandos

```powershell
python main.py --env dev                                     # mes actual
python main.py --env dev --mes 2 --anio 2026                 # mes puntual
python main.py --env dev --repo "..\OTRA CARPETA DE ENTRADA" # otra carpeta (apaga SharePoint)
python main.py --env dev --input "C:\ruta\09 VTAS SEPTIEMBRE 25" --recursive  # una sola carpeta
```

| Parámetro          | Descripción                                                          |
| ------------------ | -------------------------------------------------------------------- |
| `--env`            | Entorno: `dev`, `tst` o `pro` (default `dev`)                        |
| `--mes` / `--anio` | Período a procesar (van juntos). Sin ellos: mes actual               |
| `--repo`           | Carpeta raíz con todos los asesores. Reemplaza `INPUTS` y apaga SharePoint |
| `--input`          | Una sola carpeta de PDF (modo anterior). Apaga SharePoint            |
| `--output-dir`     | Dónde guardar los Excel (default `OUTPUTS`)                          |
| `--recursive`      | Buscar PDF en subcarpetas (con `--input`)                            |
| `--excel-asesor`   | Cruce opcional con el Excel de ventas del asesor                     |
| `--sin-filtro`     | Procesa todos los PDF sin filtrar (no recomendado)                   |

`main.py` usa el `.venv` local automáticamente si existe.

---

## Variables de configuración

Archivos en `configs/`: `.env.example` (plantilla versionada) y `.dev.env`, `.tst.env`, `.pro.env` (no versionados).

| Variable                              | Significado                                                                   |
| ------------------------------------- | ----------------------------------------------------------------------------- |
| `INPUTS`                              | Carpeta de entrada local (si SharePoint está apagado y no hay `--repo`)       |
| `OUTPUTS`                             | Destino de los Excel y base de `output/correos/`                              |
| `LOGS`                                | Carpeta de `process.log`                                                      |
| `TEMPLATES`                           | Carpeta del template `Modelo salud CE.xlsx`                                   |
| `MAIL_TEMPLATES`                      | Carpeta `Plantillas/` (HTML de inicio, fin OK y error)                        |
| `NOTIFY_ENABLED`                      | `true` = envía los avisos por SMTP. `false` = solo los guarda en disco        |
| `MAIL_SAVE_LOCAL`                     | Guarda los avisos HTML en `output/correos/<timestamp>/`                       |
| `PROCESS_SUCCESS_EMAILS` / `PROCESS_ERROR_EMAILS` | Destinatarios. Tienen que ser del dominio que acepta el relay SMTP |
| `GRAPH_ENABLED`                       | `true` = baja el mes de SharePoint y publica los Excel en `GRAPH_SALIDA`      |
| `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` | Tenant de Azure AD y app registrada (app-only)                                |
| `GRAPH_THUMBPRINT`                    | Thumbprint del certificado                                                    |
| `GRAPH_CERT_PATH`                     | Ruta al `.pem`. Vacío = certificado del store de Windows                      |
| `GRAPH_SITE_ID` / `GRAPH_LIST_ID`     | Sitio y biblioteca de SharePoint                                              |
| `GRAPH_VAVI_ROOT`                     | Carpeta raíz (default `SOLICITUDES SALUD VAVI-RETIRO`)                        |
| `GRAPH_SALIDA`                        | Carpeta donde se publican los Excel (default `_salida`)                       |
| `GRAPH_PUBLICAR_TODO_EN_SALIDA`       | Default `true`. `false` = el Excel de emisión va a la carpeta raíz            |
| `EXCEL_ASESOR_PREFERIDO`              | Sin `--excel-asesor`, elige el `VENTAS SALUD ASESORES*.xlsx` que contenga este texto |

Con `MAIL_SAVE_LOCAL=true`, cada corrida guarda `01_inicio.html`, `02_fin_ok.html` o `02_error.html` y `asuntos.txt`. Si el SMTP no responde, el lote sigue y queda anotado en el log.

Para ver muestras de los mails sin correr el lote:

```powershell
.venv\Scripts\python.exe scripts\preview_mail_templates.py   # → output\muestras_correo\
```

---

## Parametría de negocio

Archivo: `config/parametria.yaml`.

| Sección                             | Qué controla                                                     |
| ----------------------------------- | ---------------------------------------------------------------- |
| `opcion_cobertura_por_plan`         | Plan → código `OPCION_COBERTURA`                                 |
| `grupo_estadistico` / `pais_origen` | Valores fijos del Excel                                          |
| `tarjetas`                          | Nombre de tarjeta → código                                       |
| `formularios.modulo_excel`          | Módulo A/B → valor `MODULO` (1/2)                                |
| `formularios.variantes`             | Qué campos del PDF se leen en cada variante (`plan4`, `asesores`) |

> En YAML, las claves `On` y `Off` van entre comillas (`"On": "5"`). Sin comillas se leen como booleanos.

Si entregás el `.exe`, regeneralo después de cambiar el YAML.

---

## Qué escribe el Excel de emisión

Template: `templates/Modelo salud CE.xlsx` (formato `ExcelModelo` del Centro Emisor, Anexo 3.3).

| Tema                         | Comportamiento                                                                                                           |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Filas                        | Una fila **Titular** (tomador) y una por cada asegurado (**Asegurado Titular** / **Asegurado Familiar**)                 |
| Nombre / email               | Se repiten en el titular y en los asegurados                                                                             |
| Pago                         | Solo en la fila Titular. CBU de 22 dígitos o tarjeta válida se copian; si falta o está mal, `EFECTIVO=1`                 |
| `OPCION_COBERTURA`           | En todas las filas, según el plan                                                                                        |
| `ORGANIZADOR` / `PRODUCTOR`  | Solo si el PDF trae el número; si no, vacío                                                                              |
| `SEXO`                       | Solo si el PDF trae el campo; Plan Familia suele no tenerlo                                                              |
| `PROPUESTA`                  | Solo en la fila Titular: `VAVI` + fecha de la corrida (`yyyymmdd`) + 4 dígitos                                           |
| Vigencia                     | Usa la del PDF. Si solo trae el inicio, el fin es un año después. Si no trae ninguna, empieza el día 1 del mes siguiente a la carpeta y dura un año |

DNI, opción, organizador y similares se escriben como texto para no perder ceros.

---

## Hojas del reporte

| Hoja                   | Contenido                                                     |
| ---------------------- | ------------------------------------------------------------- |
| **Resumen**            | Veredicto, conteos y glosario                                 |
| **Hallazgos**          | Lista de cosas a revisar, separadas para Negocio y Técnico    |
| **Procesados**         | PDF emitidos (tomador, plan, módulo, pago)                    |
| **Incompletos**        | Solicitudes con datos faltantes                               |
| **Excluidos**          | PDF que no se pudieron leer (E1), con motivo                  |
| **Ignorados**          | Adjuntos u otros formularios                                  |
| **Revisar**            | Escaneos o casos dudosos                                      |
| **Cruce Excel asesor** | Solo si se usó `--excel-asesor`                               |
| **Validacion**         | Checklist de columnas del Anexo 3.3                           |

---

## Completitud y errores

| Categoría       | Significado                                                                  |
| --------------- | ---------------------------------------------------------------------------- |
| **Completa**    | Tiene todos los datos obligatorios. Va a `ExcelModelo`                        |
| **Incompleta**  | Se pudo leer pero le faltan datos. Va a `Incompletos`                         |
| **Duplicado**   | Dos PDF del mismo mes, asesor y DNI. Las dos versiones van a `Duplicados`     |
| **E1**          | No se pudo leer (escaneo, plantilla vacía, error). Solo aparece en el reporte |

El lote sigue aunque haya E1 o incompletas.

**Códigos de salida:** `0` = el lote corrió (aunque `ExcelModelo` esté vacío); `1` = error de configuración o no hay carpeta del mes; `2` = `--mes` sin `--anio` o al revés.

---

## Planes soportados

| Formulario              | Plan | `OPCION_COBERTURA` |
| ----------------------- | ---- | ------------------ |
| PLAN FAMILIA – PLAN 4   | 4    | 18484              |
| PLAN FAMILIA – ASESORES | 5    | 28275              |
| PLAN FAMILIA – ASESORES | 6    | 33403              |
| PLAN FAMILIA – ASESORES | 100  | 56128              |

"ASESORES" es la variante del PDF, no un plan. Si en ese formulario no marcan plan ni módulo A/B, la solicitud va a `Incompletos`.

---

## Flujo interno

```
Carpeta local o SharePoint + mes/año
  → Foto fija de los PDF del mes
  → Selector (solicitud Plan Familia vs. adjunto u otro formulario)
  → Extracción de campos del PDF
  → Normalización (vigencia, medio de pago)
  → Completitud (completa → ExcelModelo; incompleta → Incompletos)
  → Duplicados (mismo mes + asesor + DNI → Duplicados)
  → Un Excel de emisión + un reporte en output/ (y en _salida/ con SharePoint)
```

---

## Estructura del repositorio

```
extraccion-pdf-editables/
├── run.bat                 # lanzador del .exe
├── main.py                 # punto de entrada
├── main.spec               # build de PyInstaller
├── requirements.txt
├── configs/                # .env.example (los .env reales no se versionan)
├── config/parametria.yaml  # reglas de negocio
├── templates/              # Modelo salud CE.xlsx
├── Plantillas/             # plantillas de mail
├── src/                    # código
├── scripts/                # utilidades
├── tests/
├── docs/                   # esta documentación
├── SOLICITUDES SALUD VAVI-RETIRO/  # estructura de entrada de ejemplo (vacía)
├── dist/                   # no versionado: build del .exe
├── logs/                   # no versionado
└── output/                 # no versionado
```

---

## Alcance

- ✅ PDF editables → Excel de emisión + reporte, consolidado por mes
- ✅ Lectura y publicación en SharePoint (opcional)
- ✅ Ejecutable `.exe`
- ❌ OCR de escaneos o formularios manuscritos
- ❌ Reproceso del 27 a fin de mes
- ❌ Envío de mails por SMTP en producción
