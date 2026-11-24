"""Reporte de resultados del lote (Resumen, Hallazgos, Procesados, Excluidos, Validacion)."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .completitud import ResultadoCompletitud
from .labels import accion_para_campo_ce, etiquetas_campos
from .models import ErrorProceso, SolicitudSalud
from .periodo import AvisoCarpetaMes
from .selector import SeleccionPdf
from .settings import OUTPUT_DIR, Parametria, cargar_parametria
from .validation_builder import ResultadoCheck, filas_checklist_emision


def _dni_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    return "" if not s else s

_EXCLUIDOS_HEADERS = [
    "PDF",
    "Código error",
    "Tipo documento",
    "Motivo de exclusión",
    "Detalle",
    "Campos faltantes (código)",
    "Campos faltantes (descripción)",
    "Datos parcialmente extraídos",
    "Acción sugerida",
]

_PROCESADOS_HEADERS = [
    "PDF",
    "Tipo documento",
    "Tomador",
    "DNI",
    "Plan",
    "Módulo",
    "Forma pago",
    "Método extracción",
    "Figuras",
]

_IGNORADOS_HEADERS = ["PDF", "Categoría", "Decisión", "Motivo"]
_CRUCE_HEADERS = ["Estado", "Titular (Excel asesor)", "Documento"]
_INCOMPLETOS_HEADERS = [
    "PDF",
    "Tomador",
    "DNI",
    "Plan",
    "Módulo",
    "Campos faltantes",
    "Acción sugerida",
]

_POR_PDF_HEADERS = [
    "PDF",
    "Estado",
    "Código",
    "Tomador / DNI",
    "Figuras",
    "N hallazgos",
    "Detalle",
    "Qué hacer",
    "Asesor",
    "Ruta",
]

_HALLAZGOS_HEADERS = [
    "Severidad",
    "Para (Negocio / Técnico)",
    "Tipo",
    "PDF",
    "Tomador / DNI",
    "Figura / detalle",
    "Campo",
    "Qué pasó",
    "Qué hacer",
]

_VALIDACION_HEADERS = [
    "#",
    "Sección",
    "Col",
    "Campo",
    "Regla código",
    "Estado",
    "N filas",
    "N Titular",
    "N Asegurado",
    "N completas",
    "% completas",
    "Esperado",
    "Muestra valores",
    "Detalle técnico",
    "Origen (PDF / figura / fila)",
    "Regla (spec)",
]
_FILLS_ESTADO = {
    "OK": PatternFill("solid", fgColor="C6EFCE"),
    "VACIO_OK": PatternFill("solid", fgColor="DDEBF7"),
    "ERROR": PatternFill("solid", fgColor="FFC7CE"),
    "WARN": PatternFill("solid", fgColor="FFEB9C"),
    "INFO": PatternFill("solid", fgColor="DDEBF7"),
}
# Columna "Estado" en la hoja Validacion (1-based).
_COL_ESTADO_VALIDACION = 6


def _autosize_columns(ws, max_width: int = 60) -> None:
    for col_idx, column_cells in enumerate(ws.columns, start=1):
        length = max(len(str(cell.value or "")) for cell in column_cells)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(length + 2, 12), max_width)


def _pdf_por_dni(exitos: list[SolicitudSalud]) -> dict[str, list[str]]:
    mapa: dict[str, list[str]] = defaultdict(list)
    for s in exitos:
        dni = _dni_str(s.nro_documento_tomador)
        if not dni:
            continue
        nombre = s.archivo_origen or ""
        if nombre and nombre not in mapa[dni]:
            mapa[dni].append(nombre)
    return dict(mapa)


def _parse_origen_linea(linea: str) -> tuple[str, str, str, str]:
    """Devuelve (pdf, tomador_dni, figura, excel_fila) desde una línea de origen."""
    pdf = ""
    tomador = ""
    figura = ""
    excel_fila = ""
    for parte in linea.split(" | "):
        p = parte.strip()
        if p.startswith("PDF:"):
            pdf = p[4:].strip()
        elif p.startswith("Tomador DNI:"):
            tomador = p[len("Tomador DNI:") :].strip()
        elif p.startswith("Excel fila"):
            excel_fila = p.replace("Excel fila", "").strip()
        elif ": " in p and any(
            p.startswith(x) for x in ("Titular", "Asegurado Titular", "Asegurado Familiar")
        ):
            figura = p
    return pdf, tomador, figura, excel_fila


def _campo_ce_puro(campo_label: str) -> str:
    """'NRO_DOCUMENTO_BENEF (V)' → 'NRO_DOCUMENTO_BENEF'."""
    return campo_label.split(" (", 1)[0].strip()


_GLOSARIO_RESUMEN: list[tuple[str, str, str]] = [
    (
        "Completa",
        "La propuesta tiene los datos de la lista de completitud y entró a la hoja ExcelModelo del Excel de emisión.",
        "Listo para enviar al Centro Emisor (CE).",
    ),
    (
        "Incompleta",
        "Falta al menos un dato de la lista de completitud (DNI, dirección, módulo, vigencias, pago, productor, etc.). "
        "No se excluye: va a la hoja Incompletos del Excel de emisión, con celdas en blanco/amarillo.",
        "Completar a mano en Excel de emisión → Incompletos y reenviar al CE. Detalle en hojas Incompletos / Hallazgos.",
    ),
    (
        "Duplicado ambiguo",
        "Dos o más PDF distintos del mismo período, asesor y DNI del tomador. "
        "Van a la hoja Duplicados del Excel de emisión. Ninguno entra a ExcelModelo ni a Incompletos.",
        "Suscripción indica cuál es la versión válida. El bot no elige.",
    ),
    (
        "E1 (excluido)",
        "No se pudo procesar como solicitud editable (escaneo, error de lectura, PDF no válido para este bot). "
        "No entra al Excel de emisión.",
        "Revisar el PDF. Si corresponde, emitir a mano fuera del robot.",
    ),
    (
        "Ignorado",
        "El archivo no es una solicitud Plan Familia Salud / Ramo 2500 (adjunto DNI, Vida+Salud, otro formulario, etc.).",
        "No requiere acción de emisión de este bot.",
    ),
    (
        "Revisar",
        "El selector no pudo clasificarlo con claridad (p. ej. escaneo sin señales claras de solicitud).",
        "Abrir el PDF y decidir si es solicitud, adjunto u otro trámite.",
    ),
    (
        "Nota (E2)",
        "En versiones anteriores, faltantes de datos se llamaban E2 y se excluían. "
        "Hoy esos casos son Incompletos (hoja aparte), no exclusión E1.",
        "Usar la categoría Incompleta de este glosario.",
    ),
]


def _agregar_hoja_resumen(
    wb,
    *,
    exitos: list[SolicitudSalud],
    incompletas: list[tuple[SolicitudSalud, ResultadoCompletitud]],
    errores: list[ErrorProceso],
    ignorados: list[SeleccionPdf] | None,
    revisar: list[SeleccionPdf] | None,
    filas_val: list[ResultadoCheck],
    emision_path: Path | None,
    avisos_carpetas: list[AvisoCarpetaMes] | None = None,
    duplicados_ambiguos: list[list[SolicitudSalud]] | None = None,
) -> None:
    n_ign = len(ignorados or [])
    n_rev = len(revisar or [])
    n_inc = len(incompletas)
    n_avisos = len(avisos_carpetas or [])
    n_amb = sum(len(g) for g in (duplicados_ambiguos or []))
    n_err_val = sum(1 for f in filas_val if f.estado == "ERROR" and f.seccion != "META")
    n_err_meta = sum(1 for f in filas_val if f.estado == "ERROR" and f.seccion == "META")
    if errores or n_err_val or n_err_meta or n_avisos or n_amb:
        veredicto = "CON HALLAZGOS"
    elif n_inc:
        veredicto = "CON INCOMPLETOS"
    else:
        veredicto = "OK"

    ws = wb.create_sheet("Resumen", 0)
    bold = Font(bold=True)
    ws.append(["Concepto", "Valor", ""])
    for cell in ws[1][:2]:
        cell.font = bold

    filas = [
        ("Veredicto", veredicto),
        ("PDFs procesados (completas → ExcelModelo)", len(exitos)),
        ("PDFs incompletas → hoja Incompletos", n_inc),
        ("PDFs duplicados ambiguos (hoja Duplicados)", n_amb),
        ("PDFs excluidos (E1)", len(errores)),
        ("PDFs ignorados", n_ign),
        ("PDFs a revisar", n_rev),
        ("Carpetas mal nombradas (no canónicas)", n_avisos),
        ("Errores de validación (columnas ExcelModelo)", n_err_val),
        ("Excel de emisión", str(emision_path) if emision_path else "(no generado)"),
        ("Responsable Centro Emisor", "Consume y emite únicamente la hoja ExcelModelo."),
        (
            "Responsable Suscripción",
            "Revisa E1, duplicados ambiguos y la hoja Incompletos.",
        ),
        (
            "Cómo usar este reporte",
            "1) Por PDF: tablero por archivo. "
            "2) Glosario abajo: qué significa cada categoría. "
            "3) Hallazgos: filtrar columna Para (Negocio / Técnico). "
            "Negocio = acción CE; Técnico = checklist bot. "
            "4) Incompletos / Hallazgos: completar a mano en Excel de emisión → Incompletos. "
            "5) Excluidos = E1. "
            "6) Validacion = checklist Anexo 3.3 sobre ExcelModelo.",
        ),
    ]
    for concepto, valor in filas:
        ws.append([concepto, valor, ""])
        if concepto == "Veredicto":
            fill = (
                _FILLS_ESTADO["OK"]
                if veredicto == "OK"
                else _FILLS_ESTADO["WARN"]
                if veredicto == "CON INCOMPLETOS"
                else _FILLS_ESTADO["ERROR"]
            )
            ws.cell(row=ws.max_row, column=2).fill = fill

    ws.append(["", "", ""])
    ws.append(["Glosario", "Significa", "Qué hacer"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    glosario_header_row = ws.max_row

    for categoria, significa, accion in _GLOSARIO_RESUMEN:
        ws.append([categoria, significa, accion])
        if categoria.startswith("Completa"):
            ws.cell(row=ws.max_row, column=1).fill = _FILLS_ESTADO["OK"]
        elif categoria.startswith("Incompleta"):
            ws.cell(row=ws.max_row, column=1).fill = _FILLS_ESTADO["WARN"]
        elif categoria.startswith("E1"):
            ws.cell(row=ws.max_row, column=1).fill = _FILLS_ESTADO["ERROR"]

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 62
    ws.column_dimensions["C"].width = 48
    for r in range(glosario_header_row + 1, ws.max_row + 1):
        ws.row_dimensions[r].height = 48
    ws.freeze_panes = "A2"


def _agregar_hoja_por_pdf(
    wb,
    *,
    exitos: list[SolicitudSalud],
    incompletas: list[tuple[SolicitudSalud, ResultadoCompletitud]],
    errores: list[ErrorProceso],
    ignorados: list[SeleccionPdf] | None,
    revisar: list[SeleccionPdf] | None,
    filas_val: list[ResultadoCheck],
    duplicados_ambiguos: list[list[SolicitudSalud]] | None = None,
) -> None:
    """Tablero: una fila por PDF con estado y acción agregada."""
    ws = wb.create_sheet("Por PDF", 1)
    bold = Font(bold=True)
    ws.append(_POR_PDF_HEADERS)
    for cell in ws[1]:
        cell.font = bold

    hallazgos_por_pdf: dict[str, list[str]] = defaultdict(list)
    for f in filas_val:
        if f.estado != "ERROR":
            continue
        for ln in (f.origen or "").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("…"):
                continue
            pdf, _, figura, excel_fila = _parse_origen_linea(ln)
            if not pdf or pdf.startswith("("):
                continue
            for nombre in [p.strip() for p in pdf.split(",")]:
                if not nombre or nombre.startswith("("):
                    continue
                campo = f.campo
                accion = accion_para_campo_ce(campo, excel_fila=excel_fila)
                fig = figura or ""
                hallazgos_por_pdf[nombre].append(
                    f"{campo}" + (f" ({fig})" if fig else "") + f" → {accion}"
                )

    filas: list[list] = []

    for s in exitos:
        pdf = s.archivo_origen or ""
        tomador = f"{s.apellido_nombre_tomador or ''} / {_dni_str(s.nro_documento_tomador)}".strip(" /")
        hall = hallazgos_por_pdf.get(pdf, [])
        if hall:
            estado = "OK con hallazgos"
            detalle = f"{len(hall)} problema(s) de validación en Excel de emisión"
            accion = "Ver hoja Hallazgos filtrando por este PDF"
            fill_key = "WARN"
        else:
            estado = "OK"
            detalle = "Incluido en ExcelModelo (completa)"
            accion = ""
            fill_key = "OK"
        filas.append(
            [
                pdf,
                estado,
                "",
                tomador,
                len(s.asegurados),
                len(hall),
                detalle,
                accion if not hall else "; ".join(hall[:3]) + ("…" if len(hall) > 3 else ""),
                s.asesor_origen or "",
                s.ruta_origen or "",
                fill_key,
            ]
        )

    for s, resultado in incompletas:
        campos = ", ".join(etiquetas_campos(resultado.faltantes))
        tomador = f"{s.apellido_nombre_tomador or ''} / {_dni_str(s.nro_documento_tomador)}".strip(" /")
        filas.append(
            [
                s.archivo_origen or "",
                "Incompleta",
                "",
                tomador,
                len(s.asegurados),
                len(resultado.faltantes),
                f"En hoja Incompletos del Excel de emisión. Faltan: {campos}",
                "Completar a mano los campos en blanco en Excel → hoja Incompletos",
                s.asesor_origen or "",
                s.ruta_origen or "",
                "WARN",
            ]
        )

    for e in errores:
        filas.append(
            [
                e.archivo,
                "Excluido",
                e.codigo,
                e.datos_parciales or "",
                "",
                1,
                e.motivo_exclusion or e.detalle,
                e.accion_sugerida or "Revisar PDF",
                "",
                "",
                "ERROR",
            ]
        )

    for s in ignorados or []:
        filas.append(
            [
                s.path.name,
                "Ignorado",
                "",
                "",
                "",
                0,
                s.motivo,
                "No requiere emisión",
                "",
                "",
                "INFO",
            ]
        )

    for s in revisar or []:
        filas.append(
            [
                s.path.name,
                "Revisar",
                "",
                "",
                "",
                1,
                s.motivo,
                "Revisar manualmente el PDF",
                "",
                "",
                "WARN",
            ]
        )

    for grupo in duplicados_ambiguos or []:
        pdfs = ", ".join(s.archivo_origen or "" for s in grupo)
        for s in grupo:
            tomador = f"{s.apellido_nombre_tomador or ''} / {_dni_str(s.nro_documento_tomador)}".strip(" /")
            filas.append(
                [
                    s.archivo_origen or "",
                    "Duplicado ambiguo",
                    "",
                    tomador,
                    len(s.asegurados),
                    1,
                    f"Mismo período, asesor y DNI que: {pdfs}. Están en la hoja Duplicados.",
                    "Suscripción define cuál es la versión válida; no se elige automático.",
                    s.asesor_origen or "",
                    s.ruta_origen or "",
                    "WARN",
                ]
            )

    filas.sort(key=lambda r: (0 if r[1].startswith("Excluido") or r[1] == "Revisar" else 1 if "hallazgo" in r[1].lower() or "duplicado" in r[1].lower() or r[1] == "Duplicado ambiguo" else 2, r[0] or ""))

    for row in filas:
        fill_key = row.pop()
        ws.append(row)
        ws.cell(row=ws.max_row, column=2).fill = _FILLS_ESTADO.get(fill_key, PatternFill())

    if ws.max_row == 1:
        ws.append(["(sin PDFs en esta corrida)", "", "", "", "", "", "", ""])

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    _autosize_columns(ws, max_width=52)
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["G"].width = 48
    ws.column_dimensions["H"].width = 56
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:J{ws.max_row}"


def _agregar_hoja_hallazgos(
    wb,
    *,
    exitos: list[SolicitudSalud],
    incompletas: list[tuple[SolicitudSalud, ResultadoCompletitud]],
    errores: list[ErrorProceso],
    ignorados: list[SeleccionPdf] | None,
    revisar: list[SeleccionPdf] | None,
    filas_val: list[ResultadoCheck],
    avisos_carpetas: list[AvisoCarpetaMes] | None = None,
    duplicados_ambiguos: list[list[SolicitudSalud]] | None = None,
) -> None:
    ws = wb.create_sheet("Hallazgos", 2)
    bold = Font(bold=True)
    ws.append(_HALLAZGOS_HEADERS)
    for cell in ws[1]:
        cell.font = bold

    def _row(
        sev: str,
        para: str,
        tipo: str,
        pdf: str,
        tomador: str,
        figura: str,
        campo: str,
        que: str,
        accion: str,
    ) -> None:
        ws.append([sev, para, tipo, pdf, tomador, figura, campo, que, accion])
        ws.cell(row=ws.max_row, column=1).fill = _FILLS_ESTADO.get(sev, PatternFill())

    for aviso in avisos_carpetas or []:
        _row(
            "WARN",
            "Negocio",
            "Carpeta mes",
            aviso.nombre_carpeta,
            "",
            aviso.periodo_aproximado or "",
            "",
            aviso.motivo,
            "Renombrar a NNN VTAS MES AA o mover PDFs a la carpeta canónica del mes",
        )

    for grupo in duplicados_ambiguos or []:
        pdfs = ", ".join(s.archivo_origen or "" for s in grupo)
        for s in grupo:
            _row(
                "WARN",
                "Negocio",
                "Duplicado ambiguo",
                s.archivo_origen or "",
                f"{s.apellido_nombre_tomador or ''} / {_dni_str(s.nro_documento_tomador)}".strip(" /"),
                s.asesor_origen or "",
                "DNI tomador",
                f"Mismo período, asesor y DNI que: {pdfs}. Están en la hoja Duplicados.",
                "Suscripción define cuál es la versión válida; no se elige automático.",
            )

    for s, resultado in incompletas:
        campos = ", ".join(etiquetas_campos(resultado.faltantes))
        _row(
            "WARN",
            "Negocio",
            "Incompleta",
            s.archivo_origen or "",
            f"{s.apellido_nombre_tomador or ''} / {_dni_str(s.nro_documento_tomador)}".strip(" /"),
            f"{len(s.asegurados)} figura(s)",
            campos,
            "Propuesta en hoja Incompletos del Excel de emisión (campos faltantes en blanco)",
            "Completar a mano en Excel → Incompletos y reenviar al CE",
        )

    for e in errores:
        campo = ", ".join(e.campos_faltantes_legibles or e.campos_faltantes) if (e.campos_faltantes or e.campos_faltantes_legibles) else ""
        _row(
            "ERROR",
            "Negocio",
            f"Excluido {e.codigo}",
            e.archivo,
            e.datos_parciales or "",
            e.tipo_documento_legible or e.tipo_documento or "",
            campo,
            e.motivo_exclusion or e.detalle,
            e.accion_sugerida or "Revisar PDF y re-procesar",
        )

    for s in ignorados or []:
        _row(
            "INFO",
            "Negocio",
            "Ignorado",
            s.path.name,
            "",
            s.categoria,
            "",
            s.motivo,
            "No requiere emisión (adjunto / fuera de alcance del lote)",
        )

    for s in revisar or []:
        _row(
            "WARN",
            "Negocio",
            "Revisar",
            s.path.name,
            "",
            s.categoria,
            "",
            s.motivo,
            "Revisar manualmente el PDF",
        )

    for f in filas_val:
        if f.estado != "ERROR":
            continue
        campo_label = f"{f.campo} ({f.letra})" if f.letra != "-" else f.campo
        lineas = [ln.strip() for ln in (f.origen or "").splitlines() if ln.strip()]
        if not lineas:
            _row(
                "ERROR",
                "Técnico",
                "Validación Excel",
                "",
                "",
                f.seccion,
                campo_label,
                f.detalle or f.esperado,
                accion_para_campo_ce(_campo_ce_puro(campo_label)),
            )
            continue
        for ln in lineas:
            if ln.startswith("…"):
                _row(
                    "ERROR",
                    "Técnico",
                    "Validación Excel",
                    "",
                    "",
                    ln,
                    campo_label,
                    f.detalle,
                    "Ver filas adicionales en hoja Validacion → columna Origen",
                )
                continue
            pdf, tomador, figura, excel_fila = _parse_origen_linea(ln)
            _row(
                "ERROR",
                "Técnico",
                "Validación Excel",
                pdf,
                tomador,
                figura or ln,
                campo_label,
                f.detalle or f.esperado,
                accion_para_campo_ce(f.campo, excel_fila=excel_fila),
            )

    # Aviso de posibles duplicados de tomador (mismo DNI en 2+ PDFs OK)
    por_dni: dict[str, list[SolicitudSalud]] = defaultdict(list)
    for s in exitos:
        dni = _dni_str(s.nro_documento_tomador)
        if dni:
            por_dni[dni].append(s)
    for dni, sols in sorted(por_dni.items()):
        if len(sols) < 2:
            continue
        ranking = sorted(sols, key=lambda x: len(x.asegurados), reverse=True)
        mas_completo = ranking[0]
        tomador = mas_completo.apellido_nombre_tomador or ""
        pdfs = [s.archivo_origen for s in sols]
        _row(
            "WARN",
            "Negocio",
            "Posible duplicado",
            " | ".join(pdfs),
            f"{tomador} / {dni}",
            f"{len(pdfs)} PDFs; más completo: {mas_completo.archivo_origen} "
            f"({len(mas_completo.asegurados)} figuras)",
            "",
            "Más de un PDF procesado para el mismo tomador (puede ser versión incompleta + completa)",
            f"Conservar «{mas_completo.archivo_origen}» y quitar el/los duplicado(s) del lote",
        )

    if ws.max_row == 1:
        _row(
            "OK",
            "Negocio",
            "Sin hallazgos",
            "",
            "",
            "",
            "",
            "La corrida no registró problemas accionables",
            "",
        )

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    _autosize_columns(ws, max_width=56)
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["D"].width = 42
    ws.column_dimensions["F"].width = 40
    ws.column_dimensions["H"].width = 48
    ws.column_dimensions["I"].width = 52
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:I{ws.max_row}"


def _agregar_hoja_validacion(
    wb,
    emision_path: Path | None,
    parametria: Parametria,
    filas: list[ResultadoCheck],
) -> None:
    """Checklist técnico Anexo 3.3 / columnas CE (OK | VACIO_OK | ERROR)."""
    ws = wb.create_sheet("Validacion")
    bold = Font(bold=True)
    ws.append(_VALIDACION_HEADERS)
    for cell in ws[1]:
        cell.font = bold

    n_ok = sum(1 for f in filas if f.estado == "OK")
    n_vacio = sum(1 for f in filas if f.estado == "VACIO_OK")
    n_err = sum(1 for f in filas if f.estado == "ERROR")
    n_anexo_err = sum(1 for f in filas if f.seccion == "ANEXO_3.3" and f.estado == "ERROR")
    n_extra_err = sum(1 for f in filas if f.seccion == "CE_EXTRA" and f.estado == "ERROR")
    emision_ok = bool(emision_path and Path(emision_path).is_file())
    veredicto = "OK" if n_err == 0 else "ERROR"

    meta_rows = [
        ("META", "-", "CHECK_OK", "META", "OK", n_ok, "-", "-", "-", "-", "conteo estado=OK", "-", "", "Ítems en OK"),
        ("META", "-", "CHECK_VACIO_OK", "META", "VACIO_OK", n_vacio, "-", "-", "-", "-", "conteo estado=VACIO_OK", "-", "", "Ítems vacíos por diseño"),
        (
            "META",
            "-",
            "CHECK_ERROR",
            "META",
            "OK" if n_err == 0 else "ERROR",
            n_err,
            "-",
            "-",
            "-",
            "-",
            "conteo estado=ERROR",
            "-",
            f"total={n_err}; anexo_3.3={n_anexo_err}; ce_extra={n_extra_err}",
            "",
            "Errores de validación de columnas",
        ),
        (
            "META",
            "-",
            "EMISION_PATH",
            "META",
            "OK" if emision_ok else "ERROR",
            "-",
            "-",
            "-",
            "-",
            "-",
            "path emision_MM_YYYY.xlsx",
            "-",
            str(emision_path) if emision_path else "No generado",
            "",
            "Archivo ExcelModelo validado",
        ),
        (
            "META",
            "-",
            "VEREDICTO",
            "META",
            veredicto,
            "-",
            "-",
            "-",
            "-",
            "-",
            "0 ERROR en checklist",
            "-",
            "PASS" if n_err == 0 else "FAIL",
            "Ver hoja Hallazgos para el detalle accionable",
            "Veredicto global de columnas",
        ),
        (
            "META",
            "-",
            "PARAMETRIA",
            "META",
            "OK",
            "-",
            "-",
            "-",
            "-",
            "-",
            f"GE={parametria.grupo_estadistico}; pais={parametria.pais_origen}",
            str(parametria.opcion_cobertura_por_plan),
            f"planes={list(parametria.opcion_cobertura_por_plan.keys())}",
            "",
            "Parametría cargada en la corrida",
        ),
    ]

    row_idx = 2
    for seccion, letra, campo, regla_cod, estado, *rest in meta_rows:
        ws.append([row_idx - 1, seccion, letra, campo, regla_cod, estado, *rest])
        ws.cell(row=row_idx, column=_COL_ESTADO_VALIDACION).fill = _FILLS_ESTADO.get(
            estado, PatternFill()
        )
        row_idx += 1

    for f in filas:
        ws.append(
            [
                row_idx - 1,
                f.seccion,
                f.letra,
                f.campo,
                f.regla_codigo,
                f.estado,
                f.n_filas,
                f.n_titulares,
                f.n_asegurados,
                f.n_completas,
                f.pct_completas,
                f.esperado,
                f.muestra,
                f.detalle,
                f.origen,
                f.regla,
            ]
        )
        ws.cell(row=row_idx, column=_COL_ESTADO_VALIDACION).fill = _FILLS_ESTADO.get(
            f.estado, PatternFill()
        )
        row_idx += 1

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    _autosize_columns(ws, max_width=48)
    ws.column_dimensions["D"].width = 28
    ws.column_dimensions["L"].width = 36
    ws.column_dimensions["M"].width = 40
    ws.column_dimensions["N"].width = 36
    ws.column_dimensions["O"].width = 56
    ws.column_dimensions["P"].width = 42
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:P{ws.max_row}"


def generar_reporte(
    exitos: list[SolicitudSalud],
    errores: list[ErrorProceso],
    output_path: Path | None = None,
    incompletas: list[tuple[SolicitudSalud, ResultadoCompletitud]] | None = None,
    ignorados: list[SeleccionPdf] | None = None,
    revisar: list[SeleccionPdf] | None = None,
    cruce: dict[str, list[str]] | None = None,
    emision_path: Path | None = None,
    parametria: Parametria | None = None,
    avisos_carpetas: list[AvisoCarpetaMes] | None = None,
    duplicados_ambiguos: list[list[SolicitudSalud]] | None = None,
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"reporte_resultados_{timestamp}.xlsx"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    incompletas = incompletas or []
    parametria = parametria or cargar_parametria()
    todas = list(exitos) + [s for s, _ in incompletas]
    pdf_map = _pdf_por_dni(todas)
    filas_val = filas_checklist_emision(emision_path, parametria=parametria, pdf_por_dni=pdf_map)

    wb = openpyxl.Workbook()
    default = wb.active
    wb.remove(default)

    _agregar_hoja_resumen(
        wb,
        exitos=exitos,
        incompletas=incompletas,
        errores=errores,
        ignorados=ignorados,
        revisar=revisar,
        filas_val=filas_val,
        emision_path=emision_path,
        avisos_carpetas=avisos_carpetas,
        duplicados_ambiguos=duplicados_ambiguos,
    )
    _agregar_hoja_por_pdf(
        wb,
        exitos=exitos,
        incompletas=incompletas,
        errores=errores,
        ignorados=ignorados,
        revisar=revisar,
        filas_val=filas_val,
        duplicados_ambiguos=duplicados_ambiguos,
    )
    _agregar_hoja_hallazgos(
        wb,
        exitos=exitos,
        incompletas=incompletas,
        errores=errores,
        ignorados=ignorados,
        revisar=revisar,
        filas_val=filas_val,
        avisos_carpetas=avisos_carpetas,
        duplicados_ambiguos=duplicados_ambiguos,
    )

    ws_ok = wb.create_sheet("Procesados")
    ws_ok.append(_PROCESADOS_HEADERS)
    for s in exitos:
        ws_ok.append([
            s.archivo_origen,
            s.tipo_documento_legible or s.tipo_documento,
            s.apellido_nombre_tomador,
            s.nro_documento_tomador,
            s.plan,
            s.modulo,
            s.forma_pago.value,
            s.metodo_extraccion,
            len(s.asegurados),
        ])
    _autosize_columns(ws_ok)
    ws_ok.freeze_panes = "A2"

    ws_inc = wb.create_sheet("Incompletos")
    ws_inc.append(_INCOMPLETOS_HEADERS)
    for s, resultado in incompletas:
        ws_inc.append([
            s.archivo_origen,
            s.apellido_nombre_tomador,
            s.nro_documento_tomador,
            s.plan,
            s.modulo,
            "; ".join(etiquetas_campos(resultado.faltantes)),
            "Completar a mano en Excel de emisión → hoja Incompletos",
        ])
    _autosize_columns(ws_inc, max_width=60)
    ws_inc.freeze_panes = "A2"

    ws_err = wb.create_sheet("Excluidos")
    ws_err.append(_EXCLUIDOS_HEADERS)
    for e in errores:
        ws_err.append([
            e.archivo,
            e.codigo,
            e.tipo_documento_legible or e.tipo_documento,
            e.motivo_exclusion,
            e.detalle,
            ", ".join(e.campos_faltantes),
            "; ".join(e.campos_faltantes_legibles) if e.campos_faltantes_legibles else "",
            e.datos_parciales,
            e.accion_sugerida,
        ])
    _autosize_columns(ws_err, max_width=80)
    ws_err.freeze_panes = "A2"

    if ignorados:
        ws_ign = wb.create_sheet("Ignorados")
        ws_ign.append(_IGNORADOS_HEADERS)
        for s in ignorados:
            ws_ign.append([s.path.name, s.categoria, s.decision, s.motivo])
        _autosize_columns(ws_ign, max_width=80)
        ws_ign.freeze_panes = "A2"

    if revisar:
        ws_rev = wb.create_sheet("Revisar")
        ws_rev.append(_IGNORADOS_HEADERS)
        for s in revisar:
            ws_rev.append([s.path.name, s.categoria, s.decision, s.motivo])
        _autosize_columns(ws_rev, max_width=80)
        ws_rev.freeze_panes = "A2"

    if cruce:
        ws_cruce = wb.create_sheet("Cruce Excel asesor")
        ws_cruce.append(_CRUCE_HEADERS)
        for item in cruce.get("cubiertos", []):
            nombre, _, doc = item.partition(" (")
            ws_cruce.append(["Cubierto por PDF", nombre, doc.rstrip(")")])
        for item in cruce.get("faltantes", []):
            nombre, _, doc = item.partition(" (")
            ws_cruce.append(["Sin PDF de solicitud detectado", nombre, doc.rstrip(")")])
        _autosize_columns(ws_cruce, max_width=50)
        ws_cruce.freeze_panes = "A2"

    _agregar_hoja_validacion(wb, emision_path, parametria, filas_val)

    tmp = output_path.with_name(output_path.stem + ".tmp.xlsx")
    wb.save(tmp)
    wb.close()
    os.replace(tmp, output_path)
    return output_path
