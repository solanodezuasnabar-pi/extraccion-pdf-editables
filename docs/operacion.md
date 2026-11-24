# Operación

Cómo generar el `.exe`, correrlo con `run.bat` y dejarlo programado en Control-M. Volver al [README](../README.md).

- [Generar el ejecutable](#generar-el-ejecutable)
- [Correr con run.bat](#correr-con-runbat)
- [Programarlo con Control-M](#programarlo-con-control-m)
- [Errores comunes](#errores-comunes)

---

## Generar el ejecutable

```powershell
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pyinstaller.exe --clean -y main.spec
```

Queda en `dist\EmisionPlanFamiliaVAVI\`: el `.exe` y la carpeta `_internal\`. Las dos cosas van juntas; el `.exe` solo no funciona. El `.exe` no se sube a git: cada máquina lo genera.

Después de cambiar código hay que volver a generarlo. El binario no se actualiza solo.

Prueba rápida después de generarlo:

```powershell
.\run.bat --mes 1 --anio 2026
```

Tiene que terminar con código `0` y dejar `emision_01_2026.xlsx` y `reporte_01_2026.xlsx` en `dist\EmisionPlanFamiliaVAVI\output\`.

---

## Correr con run.bat

`run.bat`, en la raíz del proyecto, es la forma recomendada de correr el `.exe`:

```powershell
.\run.bat                                # mes actual
.\run.bat --mes 2 --anio 2026            # mes puntual
.\run.bat --env tst --mes 2 --anio 2026  # con configs/.tst.env
```

Qué hace:

1. Busca `dist\EmisionPlanFamiliaVAVI\EmisionPlanFamiliaVAVI.exe`.
2. Si está en una carpeta de red, copia el programa a un disco local y lo corre desde ahí (ver abajo).
3. Pasa `--env pro`, salvo que se indique otro `--env` o la variable `EMISION_ENV`.
4. Si existe la carpeta `SOLICITUDES SALUD VAVI-RETIRO` al lado del bat y `GRAPH_ENABLED` no es `true`, la usa como entrada local. Eso apaga SharePoint.
5. Termina con el código de salida del `.exe`.

Para forzar SharePoint desde el clone, donde la carpeta de ejemplo sí existe:

```powershell
$env:GRAPH_ENABLED = "true"
.\run.bat --env tst --mes 2 --anio 2026
```

Los resultados quedan en `dist\EmisionPlanFamiliaVAVI\output\` y el log en `dist\EmisionPlanFamiliaVAVI\logs\`. Con SharePoint activo, los dos Excel se publican además en la carpeta `_salida`.

### Desde una carpeta de red

El `.exe` ejecutado directo desde una carpeta de red no resuelve DNS (error 11003) y no llega a SharePoint ni al SMTP. Por eso, cuando `run.bat` está en `\\servidor\...` o en una unidad mapeada:

1. Copia `dist\EmisionPlanFamiliaVAVI\` a `%LOCALAPPDATA%\EmisionPlanFamiliaVAVI\<carpeta del bat>`. La primera vez copia todo (unos 85 MB); después, solo lo que cambió.
2. Corre el `.exe` desde esa copia.
3. Devuelve `logs\` y `output\` a la carpeta de red.

Para usar otra carpeta local, definí `EMISION_LOCAL_DIR` (por ejemplo `C:\RPA`). La configuración se edita siempre en la carpeta de red; la copia local se pisa en cada corrida.

---

## Programarlo con Control-M

Esta sección es para IT.

**Cuándo:** día 26 de cada mes a las 13:00 (hora Argentina). El bot procesa el mes del calendario, no hace falta pasarle mes ni año.

**Carpeta en el servidor:**

```
\\<servidor>\<carpeta-del-bot>\PRO\
  run.bat
  dist\EmisionPlanFamiliaVAVI\
    EmisionPlanFamiliaVAVI.exe
    _internal\
    configs\.pro.env
```

- Copiá la carpeta `EmisionPlanFamiliaVAVI` completa.
- Usá el mismo `.exe` que ya se probó en TST.
- No pongas la carpeta `SOLICITUDES SALUD VAVI-RETIRO` al lado de `run.bat`: si está, el bot no usa SharePoint.

**Comando del job:**

```bat
\\<servidor>\<carpeta-del-bot>\PRO\run.bat --env pro
```

No agregues `--mes`, `--anio` ni una carpeta de solicitudes. No hace falta mapear una unidad ni hacer `cd`.

Si llaman al `.exe` en lugar del bat, tienen que pasar `--env pro`, ejecutarlo desde `dist\EmisionPlanFamiliaVAVI\` y tenerlo en un disco local.

**Configuración (`configs\.pro.env`):**

| Variable          | Valor                  | Para qué                                                        |
| ----------------- | ---------------------- | --------------------------------------------------------------- |
| `GRAPH_ENABLED`   | `true`                 | Lee y publica en SharePoint                                     |
| `NOTIFY_ENABLED`  | `false`                | No manda mails (hasta que haya SMTP)                            |
| `MAIL_SAVE_LOCAL` | `true`                 | Guarda el aviso HTML en disco                                   |
| `GRAPH_CERT_PATH` | vacío o ruta a `.pem`  | Vacío = usa el certificado instalado en Windows                 |
| `GRAPH_SALIDA`    | `_salida`              | Carpeta de SharePoint donde quedan los dos Excel                |

La cuenta con la que corre el job necesita:

- acceso al certificado (el mismo de TST);
- permiso de escritura en la carpeta local y en `logs\` y `output\` de la carpeta de red.

**Cómo se ve una corrida buena:**

| Qué              | Dónde                                         |
| ---------------- | --------------------------------------------- |
| Excel de emisión | SharePoint, carpeta `_salida`                 |
| Reporte          | La misma carpeta `_salida`                    |
| Log              | `logs\process.log`, al lado del `.exe`        |
| Aviso HTML       | `output\correos\`, al lado del `.exe`         |

Si alguien tiene el Excel abierto en SharePoint, el bot termina igual y lo anota en el log. El job puede quedar en verde sin que el archivo esté en `_salida`: en ese caso, revisar el log.

**Códigos de salida:**

| Código | Qué significa                                                                  |
| ------ | ------------------------------------------------------------------------------ |
| `0`    | Terminó bien. Puede haber filas para emitir, incompletas, o las dos.           |
| `1`    | Error de configuración, o no encontró la carpeta del mes de ningún asesor.     |
| `2`    | Se pasó `--mes` sin `--anio`, o al revés.                                      |

Un `ExcelModelo` vacío con código `0` no es un fallo: las solicitudes están en `Incompletos` o `Duplicados`. Quien valida el mes mira esas hojas, no el color del job.

---

## Errores comunes

| Problema                                              | Qué hacer                                                                                                  |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `'.\EmisionPlanFamiliaVAVI.exe' no se reconoce`       | El `.exe` no está en la raíz. Usá `.\run.bat`.                                                             |
| `No se encontro el .exe` (de `run.bat`)               | Falta generarlo. Ver [Generar el ejecutable](#generar-el-ejecutable).                                      |
| `CMD no es compatible con las rutas UNC`              | No hagas `cd` a `\\servidor\...`. Llamá a `run.bat` por su ruta completa.                                  |
| `getaddrinfo failed` / error 11003                    | Se corrió el `.exe` desde la red. Usá `run.bat`.                                                           |
| `no se pudo copiar el programa` / `ya existe y no es una copia` | Definí `EMISION_LOCAL_DIR` con una carpeta local donde la cuenta pueda escribir.                 |
| `No existe el repo indicado (--repo)`                 | La ruta de `--repo` es incorrecta.                                                                         |
| `No existe la carpeta de entrada`                     | Revisá `INPUTS` o `--repo`.                                                                                |
| No baja de SharePoint                                 | Sacá `--repo`/`--input` y poné `GRAPH_ENABLED=true`. Revisá el certificado (`GRAPH_CERT_PATH`).            |
| El token de Windows no responde (60 s)                | Revisá el certificado en el store de la cuenta del job, o usá un `.pem` en `GRAPH_CERT_PATH`.              |
| El mail no llega                                      | Los destinatarios tienen que ser del dominio corporativo que acepta el relay SMTP.                         |
| `PermissionError` al guardar el Excel                 | Cerrá el `.xlsx` si está abierto.                                                                          |
| `Selector → procesar: 0`                              | Los PDF no son solicitudes Plan Familia. Mirá la hoja **Ignorados** del reporte.                           |
| Incompletos por plan o módulo                         | En el PDF no están marcados el plan ni la cobertura (A/B).                                                 |
