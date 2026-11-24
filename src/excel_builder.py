"""Generación del Excel de emisión masiva (modelo Centro Emisor)."""

from __future__ import annotations

import os
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.cell.cell import Cell
from openpyxl.styles import PatternFill

from .completitud import ResultadoCompletitud, aplicar_blancos_completitud
from .models import SolicitudSalud
from .rules import solicitud_a_filas
from .settings import OUTPUT_DIR, Parametria, template_xlsx

_TEXT_COLUMNS = {
    "NRO_DOCUMENTO_REFERENCIA",
    "NRO_DOCUMENTO_TITULAR",
    "NRO_TARJETA",
    "CBU",
    "NRO_DOCUMENTO_BENEF",
    "CODIGO_POSTAL",
    "ORGANIZADOR",
    "PRODUCTOR",
    "OPCION_COBERTURA",
    "GRUPO_ESTADISTICO",
    "PROPUESTA",
}

_SHEET_COMPLETAS = "ExcelModelo"
_SHEET_INCOMPLETOS = "Incompletos"
_SHEET_DUPLICADOS = "Duplicados"
# Amarillo suave: celdas que el usuario debe completar a mano.
_FILL_FALTANTE = PatternFill("solid", fgColor="FFEB9C")
_META_KEYS = {"_celdas_faltantes"}


def numero_propuesta(fecha: date, fila_excel: int) -> str:
    return f"VAVI{fecha:%Y%m%d}{fila_excel + 23:04d}"


def asignar_propuestas(
    filas: list[dict[str, Any]],
    *,
    fecha: date,
    primera_fila_datos: int = 2,
) -> list[dict[str, Any]]:
    for offset, fila in enumerate(filas):
        fila_excel = primera_fila_datos + offset
        if fila.get("TIPO_RELACION") == "Titular":
            fila["PROPUESTA"] = numero_propuesta(fecha, fila_excel)
        else:
            fila["PROPUESTA"] = None
    return filas


def _read_headers(ws) -> list[str]:
    return [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]


def _write_cell(cell: Cell, header: str, value: Any, *, destacar_faltante: bool = False) -> None:
    if value is None:
        cell.value = None
    elif header in _TEXT_COLUMNS and value != "":
        cell.value = str(value)
        cell.number_format = "@"
    elif isinstance(value, datetime):
        cell.value = value
        cell.number_format = "DD/MM/YYYY"
    else:
        cell.value = value
    if destacar_faltante:
        cell.fill = _FILL_FALTANTE


def _escribir_filas(
    ws,
    headers: list[str],
    filas: list[dict[str, Any]],
    *,
    fecha_propuesta: date,
) -> None:
    asignar_propuestas(filas, fecha=fecha_propuesta)
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    for fila in filas:
        faltantes = fila.get("_celdas_faltantes") or set()
        row_idx = ws.max_row + 1
        for col_idx, header in enumerate(headers, start=1):
            if header in _META_KEYS or header is None:
                continue
            _write_cell(
                ws.cell(row=row_idx, column=col_idx),
                header,
                fila.get(header),
                destacar_faltante=header in faltantes,
            )


def _filas_solicitud(
    solicitud: SolicitudSalud,
    parametria: Parametria,
    resultado: ResultadoCompletitud | None = None,
) -> list[dict[str, Any]]:
    filas = solicitud_a_filas(solicitud, parametria)
    if resultado is not None and not resultado.completa:
        return aplicar_blancos_completitud(filas, resultado)
    return filas


def generar_excel(
    completas: list[SolicitudSalud],
    parametria: Parametria,
    *,
    incompletas: list[tuple[SolicitudSalud, ResultadoCompletitud]] | None = None,
    duplicados: list[SolicitudSalud] | None = None,
    output_path: Path | None = None,
    template_path: Path | None = None,
    fecha_propuesta: date | None = None,
) -> Path:
    """Escribe ExcelModelo, Incompletos y Duplicados (misma grilla del modelo CE)."""
    incompletas = incompletas or []
    duplicados = duplicados or []
    fecha_propuesta = fecha_propuesta or date.today()
    template_path = Path(template_path) if template_path else template_xlsx()
    if not template_path.exists():
        raise FileNotFoundError(f"No se encontró el template Excel: {template_path}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"emision_plan_familia_{timestamp}.xlsx"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp = output_path.with_name(output_path.stem + ".tmp.xlsx")
    shutil.copy2(template_path, tmp)

    wb = openpyxl.load_workbook(tmp)
    ws_ok = wb[_SHEET_COMPLETAS] if _SHEET_COMPLETAS in wb.sheetnames else wb.active
    if ws_ok.title != _SHEET_COMPLETAS:
        ws_ok.title = _SHEET_COMPLETAS
    headers = _read_headers(ws_ok)

    for sheet_name in list(wb.sheetnames):
        if sheet_name != _SHEET_COMPLETAS:
            wb.remove(wb[sheet_name])

    filas_ok: list[dict[str, Any]] = []
    for solicitud in completas:
        filas_ok.extend(_filas_solicitud(solicitud, parametria))
    _escribir_filas(ws_ok, headers, filas_ok, fecha_propuesta=fecha_propuesta)

    ws_inc = wb.create_sheet(_SHEET_INCOMPLETOS)
    for col_idx, header in enumerate(headers, start=1):
        ws_inc.cell(row=1, column=col_idx, value=header)

    filas_inc: list[dict[str, Any]] = []
    for solicitud, resultado in incompletas:
        filas_inc.extend(_filas_solicitud(solicitud, parametria, resultado))
    _escribir_filas(ws_inc, headers, filas_inc, fecha_propuesta=fecha_propuesta)

    ws_dup = wb.create_sheet(_SHEET_DUPLICADOS)
    for col_idx, header in enumerate(headers, start=1):
        ws_dup.cell(row=1, column=col_idx, value=header)
    filas_dup: list[dict[str, Any]] = []
    for solicitud in duplicados:
        filas_dup.extend(_filas_solicitud(solicitud, parametria))
    _escribir_filas(ws_dup, headers, filas_dup, fecha_propuesta=fecha_propuesta)

    wb.save(tmp)
    wb.close()
    os.replace(tmp, output_path)
    return output_path
