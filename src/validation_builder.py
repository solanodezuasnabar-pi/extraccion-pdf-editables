"""Checklist técnico Anexo 3.3 / columnas CE — filas para la hoja Validacion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re

import openpyxl

from .settings import Parametria, cargar_parametria


@dataclass(frozen=True)
class ColumnaAnexo:
    columna: str
    letra: str
    regla: str
    regla_codigo: str = "OPT"
    vacio_diseno: bool = False
    obligatorio_titular: bool = False
    obligatorio_asegurado: bool = False
    vacio_en_titular: bool = False
    vacio_en_asegurado: bool = False
    valor_fijo: Any | None = None


# regla_codigo: OBL_TIT | OBL_ASEG | OBL_AMBOS | FIXED | VACIO_DISENO | VACIO_TIT | OPT | PROPUESTA_TIT
COLUMNAS_ANEXO_33: list[ColumnaAnexo] = [
    ColumnaAnexo("TIPO_DOC_REFERENCIA", "A", "Tipo doc Tomador (DNI/LE/LC/CI)", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo("NRO_DOCUMENTO_REFERENCIA", "B", "DNI Tomador en todas las filas", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo("PAIS_ORIGEN_REFERENCIA", "C", "Valor fijo Negocio (parametria.pais_origen)", "FIXED", valor_fijo=1),
    ColumnaAnexo("CERTIF_ROL_REF", "D", "Fuera de operatoria VAVI — debe permanecer vacío", "VACIO_DISENO", vacio_diseno=True),
    ColumnaAnexo("TIPO_RELACION", "E", "Titular | Asegurado Titular | Asegurado Familiar", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo("TIPO_DOC_TITULAR", "F", "Tipo doc de la figura de la fila", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo("NRO_DOCUMENTO_TITULAR", "G", "Nro doc de la figura de la fila", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo("PAIS_ORIGEN_TITULAR", "H", "Valor fijo Negocio (parametria.pais_origen)", "FIXED", valor_fijo=1),
    ColumnaAnexo(
        "APELLIDO_NOMBRE_TITULAR",
        "I",
        "Nombre figura (Titular y Asegurados; se puede repetir)",
        "OBL_AMBOS",
        obligatorio_titular=True,
        obligatorio_asegurado=True,
    ),
    ColumnaAnexo("FECHA_NACIMIENTO", "J", "Fecha nacimiento figura (datetime)", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo("SEXO", "K", "M|F|X solo si viene en PDF; Plan Familia suele vacío", "OPT"),
    ColumnaAnexo("DIRECCION", "L", "Calle+Nro+Piso+Dto Tomador (todas las figuras)", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo("CODIGO_POSTAL", "M", "CP Tomador numérico", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo("LOCALIDAD", "N", "Localidad Tomador sin abreviar", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo(
        "EMAIL",
        "O",
        "Email tomador repetido en Titular y Asegurados",
        "OBL_AMBOS",
        obligatorio_titular=True,
        obligatorio_asegurado=True,
    ),
    ColumnaAnexo("SUMA_ASEGURADA", "P", "No aplica operatoria — vacío por diseño", "VACIO_DISENO", vacio_diseno=True),
    ColumnaAnexo("TARJETA_CREDITO", "Q", "Código Anexo 3.4 si forma_pago=tarjeta; si no vacío", "OPT"),
    ColumnaAnexo("NRO_TARJETA", "R", "Nro tarjeta si forma_pago=tarjeta; si no vacío", "OPT"),
    ColumnaAnexo("EFECTIVO", "S", "1 si forma_pago=efectivo; si no vacío", "OPT"),
    ColumnaAnexo("CBU", "T", "CBU si forma_pago=cbu; solo fila Titular en emision", "OPT"),
    ColumnaAnexo(
        "TIPO_DOC_BENEF",
        "U",
        "Solo filas Asegurado; vacío en Titular",
        "VACIO_TIT",
        vacio_en_titular=True,
        obligatorio_asegurado=True,
    ),
    ColumnaAnexo(
        "NRO_DOCUMENTO_BENEF",
        "V",
        "Solo filas Asegurado; vacío en Titular",
        "VACIO_TIT",
        vacio_en_titular=True,
        obligatorio_asegurado=True,
    ),
    ColumnaAnexo(
        "PAIS_ORIGEN_BENEF",
        "W",
        "Fijo parametria.pais_origen solo en Asegurados",
        "VACIO_TIT",
        vacio_en_titular=True,
        valor_fijo=1,
    ),
    ColumnaAnexo(
        "APELLIDO_NOMBRE_BENEF",
        "X",
        "Solo filas Asegurado; vacío en Titular",
        "VACIO_TIT",
        vacio_en_titular=True,
        obligatorio_asegurado=True,
    ),
    ColumnaAnexo("INICIO_VIGENCIA", "AA", "Vigencia desde (PDF o día 1 del mes siguiente a la carpeta)", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo("FIN_VIGENCIA", "AB", "Vigencia hasta (típicamente inicio+1 año)", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo("MODULO", "AK", "1=A / 2=B en todas las figuras", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo(
        "PROPUESTA",
        "AL",
        "VAVI+yyyymmdd+fila solo en Titular; vacío en el resto",
        "PROPUESTA_TIT",
    ),
    ColumnaAnexo("ORGANIZADOR", "AM", "Nro organizador del PDF si existe", "OPT"),
    ColumnaAnexo("PRODUCTOR", "AN", "Nro productor del PDF si existe", "OPT"),
    ColumnaAnexo("OPCION_COBERTURA", "AS", "Código plan Anexo 3.5 (parametria)", "OBL_TIT", obligatorio_titular=True),
    ColumnaAnexo(
        "TIPO_COBERTURA",
        "AT",
        "Individual|Grupo Familiar solo en asegurados",
        "VACIO_TIT",
        vacio_en_titular=True,
        obligatorio_asegurado=True,
    ),
    ColumnaAnexo(
        "RELACIÓN_TITULAR",
        "AU",
        "Titular|Cónyuge|Hijos solo en asegurados",
        "VACIO_TIT",
        vacio_en_titular=True,
        obligatorio_asegurado=True,
    ),
    ColumnaAnexo("GRUPO_ESTADISTICO", "AX", "Valor fijo Negocio (parametria.grupo_estadistico)", "FIXED", valor_fijo=2301),
]


@dataclass
class ResultadoCheck:
    seccion: str
    letra: str
    campo: str
    regla_codigo: str
    regla: str
    estado: str
    n_filas: int
    n_titulares: int
    n_asegurados: int
    n_completas: int
    pct_completas: float
    esperado: str
    muestra: str
    detalle: str
    # Texto legible: PDF / tomador / figura / fila Excel (vacío si OK).
    origen: str = ""


_RE_PROPUESTA = re.compile(r"^VAVI(\d{8})(\d{4})$")


def _vacio(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _norm_rel(value: Any) -> str:
    return str(value or "").strip()


def _es_titular(rel: str) -> bool:
    return rel == "Titular"


def _es_asegurado(rel: str) -> bool:
    return rel.startswith("Asegurado")


def _norm_header(name: str) -> str:
    return (
        str(name)
        .upper()
        .replace("Ó", "O")
        .replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ú", "U")
    )


def _muestra_valores(vals: list[Any], limit: int = 3) -> str:
    out: list[str] = []
    for v in vals:
        if _vacio(v):
            continue
        if hasattr(v, "strftime"):
            out.append(v.strftime("%d/%m/%Y"))
        else:
            s = str(v).strip()
            if len(s) > 40:
                s = s[:37] + "..."
            out.append(s)
        if len(out) >= limit:
            break
    return " | ".join(out) if out else "(vacío)"


def _dni_str(value: Any) -> str:
    if _vacio(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _etiqueta_fila(
    row: dict[str, Any],
    *,
    excel_row: int,
    pdf_por_dni: dict[str, list[str]] | None,
) -> str:
    """Descripción legible de una fila problemática del Excel de emisión."""
    dni = _dni_str(row.get("NRO_DOCUMENTO_REFERENCIA"))
    pdfs = (pdf_por_dni or {}).get(dni, []) if dni else []
    pdf_txt = ", ".join(pdfs) if pdfs else "(PDF no identificado por DNI tomador)"
    figura = str(row.get("APELLIDO_NOMBRE_TITULAR") or "").strip()
    if not figura:
        figura = str(row.get("APELLIDO_NOMBRE_BENEF") or "").strip() or "(sin nombre)"
    rel = _norm_rel(row.get("TIPO_RELACION")) or "(sin relación)"
    partes = [
        f"Excel fila {excel_row}",
        f"PDF: {pdf_txt}",
        f"Tomador DNI: {dni or '(vacío)'}",
        f"{rel}: {figura}",
    ]
    return " | ".join(partes)


def _leer_emision(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["ExcelModelo"] if "ExcelModelo" in wb.sheetnames else wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    rows: list[dict[str, Any]] = []
    for excel_row, raw in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not any(raw):
            continue
        item = {headers[i]: raw[i] for i in range(len(headers)) if headers[i]}
        item["_excel_row"] = excel_row
        rows.append(item)
    wb.close()
    return [h for h in headers if h], rows


def _valores_columna(rows: list[dict[str, Any]], col: str) -> list[Any]:
    return [r.get(col) for r in rows]


def _resolver_header(columna: str, headers: list[str]) -> str | None:
    if columna in headers:
        return columna
    target = _norm_header(columna)
    for h in headers:
        if _norm_header(h) == target:
            return h
    return None


def _resultado_base(
    col: ColumnaAnexo,
    *,
    estado: str,
    detalle: str,
    esperado: str,
    n_filas: int,
    n_tit: int,
    n_aseg: int,
    n_completas: int,
    muestra: str,
    origen: str = "",
) -> ResultadoCheck:
    pct = (100.0 * n_completas / n_filas) if n_filas else 0.0
    return ResultadoCheck(
        seccion="ANEXO_3.3",
        letra=col.letra,
        campo=col.columna,
        regla_codigo=col.regla_codigo,
        regla=col.regla,
        estado=estado,
        n_filas=n_filas,
        n_titulares=n_tit,
        n_asegurados=n_aseg,
        n_completas=n_completas,
        pct_completas=round(pct, 1),
        esperado=esperado,
        muestra=muestra,
        detalle=detalle,
        origen=origen,
    )


def _origen_filas(
    filas: list[dict[str, Any]],
    pdf_por_dni: dict[str, list[str]] | None,
    *,
    limite: int = 8,
) -> str:
    lineas: list[str] = []
    for r in filas[:limite]:
        lineas.append(
            _etiqueta_fila(
                r,
                excel_row=int(r.get("_excel_row") or 0),
                pdf_por_dni=pdf_por_dni,
            )
        )
    if len(filas) > limite:
        lineas.append(f"… y {len(filas) - limite} fila(s) más")
    return "\n".join(lineas)


def _chequear_columna(
    col: ColumnaAnexo,
    headers: list[str],
    rows: list[dict[str, Any]],
    parametria: Parametria,
    pdf_por_dni: dict[str, list[str]] | None = None,
) -> ResultadoCheck:
    n_filas = len(rows)
    titulares = [r for r in rows if _es_titular(_norm_rel(r.get("TIPO_RELACION")))]
    asegurados = [r for r in rows if _es_asegurado(_norm_rel(r.get("TIPO_RELACION")))]
    n_tit, n_aseg = len(titulares), len(asegurados)

    header = _resolver_header(col.columna, headers)
    if header is None:
        return _resultado_base(
            col,
            estado="ERROR",
            detalle="Columna ausente en hoja ExcelModelo (schema mismatch)",
            esperado=col.regla,
            n_filas=n_filas,
            n_tit=n_tit,
            n_aseg=n_aseg,
            n_completas=0,
            muestra="(N/A)",
            origen="Revisar template Modelo salud CE.xlsx / headers del Excel de emisión",
        )

    vals = _valores_columna(rows, header)
    n_completas = sum(1 for v in vals if not _vacio(v))
    muestra = _muestra_valores(vals)

    if not rows:
        return _resultado_base(
            col,
            estado="ERROR",
            detalle="ExcelModelo sin filas de datos",
            esperado=col.regla,
            n_filas=0,
            n_tit=0,
            n_aseg=0,
            n_completas=0,
            muestra="(N/A)",
        )

    if col.regla_codigo == "PROPUESTA_TIT":
        mal: list[dict[str, Any]] = []
        fechas: set[str] = set()
        for r in rows:
            rel = _norm_rel(r.get("TIPO_RELACION"))
            val = r.get(header)
            excel_row = int(r.get("_excel_row") or 0)
            if rel == "Titular":
                texto = "" if _vacio(val) else str(val).strip()
                m = _RE_PROPUESTA.match(texto)
                if not m:
                    mal.append(r)
                    continue
                fechas.add(m.group(1))
                if int(m.group(2)) != excel_row + 23:
                    mal.append(r)
            elif not _vacio(val):
                mal.append(r)
        ok = not mal and len(fechas) <= 1
        return _resultado_base(
            col,
            estado="OK" if ok else "ERROR",
            detalle=(
                f"titulares_ok={n_tit - sum(1 for r in mal if _es_titular(_norm_rel(r.get('TIPO_RELACION'))))}/{n_tit}; "
                f"fechas={sorted(fechas) or ['(ninguna)']}"
            ),
            esperado="VAVI+yyyymmdd+(fila+23) en Titular; vacío en el resto",
            n_filas=n_filas,
            n_tit=n_tit,
            n_aseg=n_aseg,
            n_completas=n_completas,
            muestra=muestra,
            origen=_origen_filas(mal, pdf_por_dni) if mal else "",
        )

    if col.vacio_diseno:
        if n_completas:
            mal = [r for r in rows if not _vacio(r.get(header))]
            return _resultado_base(
                col,
                estado="ERROR",
                detalle=f"VACIO_DISENO violado: {n_completas}/{n_filas} celdas con valor",
                esperado="NULL en 100% filas",
                n_filas=n_filas,
                n_tit=n_tit,
                n_aseg=n_aseg,
                n_completas=n_completas,
                muestra=muestra,
                origen=_origen_filas(mal, pdf_por_dni),
            )
        return _resultado_base(
            col,
            estado="VACIO_OK",
            detalle=f"VACIO_DISENO ok — {n_filas} filas NULL",
            esperado="NULL en 100% filas",
            n_filas=n_filas,
            n_tit=n_tit,
            n_aseg=n_aseg,
            n_completas=0,
            muestra=muestra,
        )

    fijo = col.valor_fijo
    if col.columna == "GRUPO_ESTADISTICO":
        fijo = parametria.grupo_estadistico
    if col.columna in {"PAIS_ORIGEN_REFERENCIA", "PAIS_ORIGEN_TITULAR", "PAIS_ORIGEN_BENEF"}:
        fijo = parametria.pais_origen

    if col.columna == "PAIS_ORIGEN_BENEF":
        mal_t = [r for r in titulares if not _vacio(r.get(header))]
        mal_a = [
            r
            for r in asegurados
            if _vacio(r.get(header)) or str(r.get(header)) != str(fijo)
        ]
        mal = mal_t + mal_a
        ok = not mal
        return _resultado_base(
            col,
            estado="OK" if ok else "ERROR",
            detalle=(
                f"titulares_con_valor={len(mal_t)}; asegurados_invalidos={len(mal_a)}; "
                f"esperado_aseg={fijo}"
            ),
            esperado=f"Titular=NULL; Asegurado={fijo}",
            n_filas=n_filas,
            n_tit=n_tit,
            n_aseg=n_aseg,
            n_completas=n_completas,
            muestra=muestra,
            origen=_origen_filas(mal, pdf_por_dni) if mal else "",
        )

    if fijo is not None and col.regla_codigo == "FIXED":
        mal = [
            r
            for r in rows
            if _vacio(r.get(header))
            or (r.get(header) != fijo and str(r.get(header)) != str(fijo))
        ]
        vacios = n_filas - n_completas
        mismatch = sum(
            1
            for v in vals
            if not _vacio(v) and v != fijo and str(v) != str(fijo)
        )
        ok = not mal
        return _resultado_base(
            col,
            estado="OK" if ok else "ERROR",
            detalle=f"fixed={fijo}; vacios={vacios}; mismatch={mismatch}",
            esperado=f"constante={fijo} en 100% filas",
            n_filas=n_filas,
            n_tit=n_tit,
            n_aseg=n_aseg,
            n_completas=n_completas,
            muestra=muestra,
            origen=_origen_filas(mal, pdf_por_dni) if mal else "",
        )

    notas: list[str] = []
    problemas = 0
    mal: list[dict[str, Any]] = []

    if col.obligatorio_titular:
        faltan = [r for r in titulares if _vacio(r.get(header))]
        if faltan:
            problemas += 1
            notas.append(f"tit_null={len(faltan)}/{n_tit}")
            mal.extend(faltan)

    if col.obligatorio_asegurado:
        faltan = [r for r in asegurados if _vacio(r.get(header))]
        if faltan:
            problemas += 1
            notas.append(f"aseg_null={len(faltan)}/{n_aseg}")
            mal.extend(faltan)

    if col.vacio_en_titular:
        sobran = [r for r in titulares if not _vacio(r.get(header))]
        if sobran:
            problemas += 1
            notas.append(f"tit_filled_illegal={len(sobran)}/{n_tit}")
            mal.extend(sobran)

    if col.vacio_en_asegurado:
        sobran = [r for r in asegurados if not _vacio(r.get(header))]
        if sobran:
            problemas += 1
            notas.append(f"aseg_filled_illegal={len(sobran)}/{n_aseg}")
            mal.extend(sobran)

    esperado = col.regla
    if col.regla_codigo == "OBL_TIT":
        esperado = "NOT NULL en filas Titular"
    elif col.regla_codigo == "OBL_ASEG":
        esperado = "NOT NULL en filas Asegurado*"
    elif col.regla_codigo == "OBL_AMBOS":
        esperado = "NOT NULL en Titular y Asegurado*"
    elif col.regla_codigo == "VACIO_TIT":
        esperado = "NULL en Titular; NOT NULL en Asegurado*"
    elif col.regla_codigo == "OPT":
        esperado = "opcional (NULL permitido)"

    detalle = "; ".join(notas) if notas else f"filled={n_completas}/{n_filas}"
    # dedupe mal rows by excel row
    seen: set[int] = set()
    mal_uniq: list[dict[str, Any]] = []
    for r in mal:
        er = int(r.get("_excel_row") or 0)
        if er in seen:
            continue
        seen.add(er)
        mal_uniq.append(r)

    return _resultado_base(
        col,
        estado="ERROR" if problemas else "OK",
        detalle=detalle,
        esperado=esperado,
        n_filas=n_filas,
        n_tit=n_tit,
        n_aseg=n_aseg,
        n_completas=n_completas,
        muestra=muestra,
        origen=_origen_filas(mal_uniq, pdf_por_dni) if problemas else "",
    )


def filas_checklist_emision(
    emision_path: Path | None,
    parametria: Parametria | None = None,
    pdf_por_dni: dict[str, list[str]] | None = None,
) -> list[ResultadoCheck]:
    """Checklist técnico de columnas Anexo 3.3 + columnas CE fuera de mapeo."""
    if emision_path is None or not Path(emision_path).is_file():
        return [
            ResultadoCheck(
                seccion="META",
                letra="-",
                campo="EMISION_XLSX",
                regla_codigo="META",
                regla="Debe existir emision_MM_YYYY.xlsx",
                estado="ERROR",
                n_filas=0,
                n_titulares=0,
                n_asegurados=0,
                n_completas=0,
                pct_completas=0.0,
                esperado="archivo presente",
                muestra="(N/A)",
                detalle="No se generó Excel de emisión en esta corrida",
                origen="No hay Excel de emisión para esta carpeta de mes",
            )
        ]

    parametria = parametria or cargar_parametria()
    headers, rows = _leer_emision(Path(emision_path))
    n_tit = sum(1 for r in rows if _es_titular(_norm_rel(r.get("TIPO_RELACION"))))
    n_aseg = sum(1 for r in rows if _es_asegurado(_norm_rel(r.get("TIPO_RELACION"))))

    out: list[ResultadoCheck] = [
        ResultadoCheck(
            seccion="META",
            letra="-",
            campo="SCHEMA_EXCELMODELO",
            regla_codigo="META",
            regla="Conteo estructural del Excel de emisión",
            estado="OK" if rows else "ERROR",
            n_filas=len(rows),
            n_titulares=n_tit,
            n_asegurados=n_aseg,
            n_completas=len(headers),
            pct_completas=100.0 if rows else 0.0,
            esperado=">=1 fila; headers Anexo 3.3",
            muestra=f"headers={len(headers)}; GE={parametria.grupo_estadistico}; pais={parametria.pais_origen}",
            detalle=str(Path(emision_path).resolve()),
            origen="" if rows else "ExcelModelo sin filas de datos",
        )
    ]

    for col in COLUMNAS_ANEXO_33:
        out.append(_chequear_columna(col, headers, rows, parametria, pdf_por_dni))

    anexadas = {_norm_header(c.columna) for c in COLUMNAS_ANEXO_33}
    for h in headers:
        if _norm_header(h) in anexadas:
            continue
        vals = _valores_columna(rows, h)
        llenas = sum(1 for v in vals if not _vacio(v))
        mal = [r for r in rows if not _vacio(r.get(h))] if llenas else []
        out.append(
            ResultadoCheck(
                seccion="CE_EXTRA",
                letra="-",
                campo=str(h),
                regla_codigo="FUERA_3.3",
                regla="Columna del template CE no mapeada en Anexo 3.3 — debe estar vacía",
                estado="ERROR" if llenas else "VACIO_OK",
                n_filas=len(rows),
                n_titulares=n_tit,
                n_asegurados=n_aseg,
                n_completas=llenas,
                pct_completas=round(100.0 * llenas / len(rows), 1) if rows else 0.0,
                esperado="NULL en 100% filas",
                muestra=_muestra_valores(vals),
                detalle=f"filled={llenas}/{len(rows)} — fuera de alcance VAVI",
                origen=_origen_filas(mal, pdf_por_dni) if mal else "",
            )
        )

    return out
