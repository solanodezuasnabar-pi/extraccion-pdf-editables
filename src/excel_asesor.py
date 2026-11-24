"""Lectura opcional del Excel de ventas del asesor (cruce suave con el lote).

Estructura observada en `VENTAS SALUD ASESORES - <ASESOR>.xlsx`:
- Una hoja por mes: `VTAS SEPTIEMBRE25`, `VTAS ENERO26`, etc.
- Columnas: ASESOR, GE, Nº DOCUMENTO, APELLIDO Y NOMBRE, DETALLE DE TITULAR/FAMILIAR, ...

No se usa como fuente primaria de emisión (flujo V2.0 toma los PDF).
Sirve para: contar titulares esperados y detectar faltantes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl


@dataclass(frozen=True)
class TitularAsesor:
    nombre: str
    nro_documento: str
    detalle: str
    ge: str | None = None
    plan: str | None = None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())


def _resolver_hoja(wb, mes_hint: str | None) -> str | None:
    """Busca hoja tipo VTAS SEPTIEMBRE25 a partir de un hint de carpeta."""
    if not mes_hint:
        return None
    hint = _norm(mes_hint)
    # "09 VTAS SEPTIEMBRE 25" -> tokens SEPTIEMBRE, 25
    for name in wb.sheetnames:
        n = _norm(name)
        if not n.startswith("VTAS"):
            continue
        # match month word + year digits present in hint
        meses = (
            "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
            "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
        )
        mes = next((m for m in meses if m in hint and m in n), None)
        if not mes:
            continue
        # year: 25 / 26 / 2025
        anios = re.findall(r"\b(20)?(\d{2})\b", hint)
        anio_ok = not anios or any(a[1] in n for a in anios)
        if anio_ok:
            return name
    return None


def leer_titulares(
    excel_path: Path,
    mes_hint: str | None = None,
    hoja: str | None = None,
) -> tuple[str, list[TitularAsesor]]:
    """Devuelve (nombre_hoja, titulares) del Excel del asesor."""
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    try:
        sheet_name = hoja or _resolver_hoja(wb, mes_hint)
        if not sheet_name or sheet_name not in wb.sheetnames:
            raise ValueError(
                f"No se encontró hoja para mes='{mes_hint}'. Hojas: {wb.sheetnames}"
            )
        ws = wb[sheet_name]
        headers = [c for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
        idx = {
            _norm(str(h).replace("\n", " ")): i
            for i, h in enumerate(headers)
            if h is not None
        }

        def col(*cands: str) -> int | None:
            for c in cands:
                for k, i in idx.items():
                    if c in k:
                        return i
            return None

        i_nombre = col("APELLIDO")
        i_doc = col("DOCUMENTO")
        i_det = col("DETALLE")
        i_ge = col("GE")
        i_plan = col("TIPO DE PLAN", "PLAN")
        if i_nombre is None or i_doc is None:
            raise ValueError(f"Columnas esperadas no encontradas en {sheet_name}: {list(idx)}")

        titulares: list[TitularAsesor] = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            nombre = row[i_nombre]
            if not nombre:
                continue
            det = str(row[i_det] or "").strip() if i_det is not None else ""
            if det and "titular" not in det.lower():
                continue
            titulares.append(
                TitularAsesor(
                    nombre=str(nombre).strip(),
                    nro_documento=str(row[i_doc] or "").strip(),
                    detalle=det,
                    ge=str(row[i_ge]).strip() if i_ge is not None and row[i_ge] is not None else None,
                    plan=str(row[i_plan]).strip() if i_plan is not None and row[i_plan] is not None else None,
                )
            )
        return sheet_name, titulares
    finally:
        wb.close()


def cruzar_con_seleccion(
    titulares: list[TitularAsesor],
    selecciones_procesar: list,
) -> dict[str, list[str]]:
    """Cruce suave por apellido (tokens). No es matching 1:1 perfecto."""
    nombres_pdf = " | ".join(_norm(s.path.name) for s in selecciones_procesar)

    cubiertos: list[str] = []
    faltantes: list[str] = []
    for t in titulares:
        tokens = [tok for tok in _norm(t.nombre).split() if len(tok) >= 4]
        if tokens and any(tok in nombres_pdf for tok in tokens):
            cubiertos.append(f"{t.nombre} ({t.nro_documento})")
        else:
            faltantes.append(f"{t.nombre} ({t.nro_documento})")

    return {"cubiertos": cubiertos, "faltantes": faltantes}
