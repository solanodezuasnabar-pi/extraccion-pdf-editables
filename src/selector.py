"""Selector de PDFs — solicitud Plan Familia Salud vs otros editables/adjuntos.

Capas (en orden):
1. Nombre: excluir adjuntos / basura obvia.
2. Huella de widgets: debe parecer formulario Plan 4 o Asesores (Ramo Salud).
3. Marcadores de texto (refuerzo / escaneos).

Un PDF editable que no sea Plan Familia se **ignora** (no se extrae).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz

from .classifier import clasificar_doc, PerfilDocumento

# --- Capa 1: exclusión por nombre -------------------------------------------------

_EXCLUIR_NOMBRE = re.compile(
    r"(?i)("
    r"cbu|"
    r"medio[\s_-]*de[\s_-]*pago|"
    r"\balias\b|"
    r"constancia|"
    r"conformidad|"
    r"\bdni\b|dni\s|dnifrente|dnidorso|"
    r"frente|dorso|"
    r"debito|d[eé]bito|"
    r"aceptaci[oó]n|aceptacion|"
    r"camscanner|instructivo|"
    r"tarjeta|"
    r"declaraci[oó]n\s*_?jurada|declaracion_jurada|"
    r"pr[_\s-]?formulario|"
    r"vida\s*\+\s*salud|vida\s+y\s+salud"
    r")"
)

_INCLUIR_NOMBRE = re.compile(
    r"(?i)("
    r"solicitud|seguro\s+ramo|"
    r"seg\.?\s*salud|s\.?\s*s\.?\s|"
    r"ssalud|plan\s*familia|plan\s*4|plan\s*100|"
    r"propuesta[_\s-]?salud|"
    r"salud(\s|\.|$|_|-)"
    r")"
)

# --- Capa 2: huella de widgets Plan Familia --------------------------------------

# Campos presentes en Plan 4 y Asesores (muestras reales).
_HUELLA_NUCLEO = frozenset(
    {
        "APELLIDO Y NOMBRES",
        "APELLIDO Y NOMBRES DEL TITULARRow1",
        "CALLE",
        "LOCALIDAD",
        "NRO DE DOCUMENTORow1",
        "FECHA DE NACIMIENTORow1",
        "ORGANIZADOR NRORow1",
        "PRODUCTOR NRORow1",
    }
)

# Señal de cobertura/plan (al menos una).
_HUELLA_PLAN = frozenset({"APORTE", "DOCM", "TIPO PLAN", "COBERTURA", "PAGO"})

_MIN_NUCLEO = 5  # de 8; Plan 4/Asesores suelen tener 7–8

_MARCADORES_CONTENIDO = (
    "PLAN FAMILIA",
    "RAMO SALUD",
    "ASEGURABLES",
    "SOLICITUD DE SEGURO",
)


@dataclass(frozen=True)
class SeleccionPdf:
    path: Path
    decision: str  # procesar | ignorar | revisar
    categoria: str  # solicitud_editable | solicitud_escaneada | adjunto | otro_formulario | no_clasificado
    motivo: str
    perfil: PerfilDocumento | None = None


def _nombre_excluido(nombre: str) -> bool:
    return bool(_EXCLUIR_NOMBRE.search(nombre))


def _nombre_sugiere_solicitud(nombre: str) -> bool:
    return bool(_INCLUIR_NOMBRE.search(nombre))


def _nombres_widgets(doc: fitz.Document) -> set[str]:
    nombres: set[str] = set()
    for page in doc:
        for widget in page.widgets() or []:
            nombre = (widget.field_name or "").strip()
            if nombre:
                nombres.add(nombre)
    return nombres


def es_formulario_plan_familia(nombres: set[str]) -> tuple[bool, str]:
    """True si la huella de campos coincide con Plan 4 / Asesores."""
    if not nombres:
        return False, "sin widgets"

    nucleo = len(_HUELLA_NUCLEO & nombres)
    plan = _HUELLA_PLAN & nombres
    if nucleo >= _MIN_NUCLEO and plan:
        return True, f"huella OK (núcleo={nucleo}/{len(_HUELLA_NUCLEO)}, plan={sorted(plan)})"
    if "APELLIDO Y NOMBRES DEL TITULARRow1" in nombres and plan and nucleo >= 4:
        return True, f"huella OK débil (núcleo={nucleo}, plan={sorted(plan)})"
    return (
        False,
        f"huella no Plan Familia (núcleo={nucleo}/{len(_HUELLA_NUCLEO)}, plan={sorted(plan) or '∅'})",
    )


def _texto_tiene_marcador(doc: fitz.Document, max_chars: int = 8000) -> tuple[bool, str]:
    texto = ""
    for page in doc:
        texto += page.get_text()
        if len(texto) >= max_chars:
            break
    upper = texto.upper()
    for m in _MARCADORES_CONTENIDO:
        if m in upper:
            return True, m
    return False, ""


def seleccionar_pdf(pdf_path: Path) -> SeleccionPdf:
    """Aplica capas de selección sobre un PDF individual."""
    nombre = pdf_path.name

    # Capa 1: exclusión por nombre
    if _nombre_excluido(nombre):
        return SeleccionPdf(
            path=pdf_path,
            decision="ignorar",
            categoria="adjunto",
            motivo=f"Nombre indica adjunto u otro formulario: {nombre}",
        )

    # Una sola apertura del PDF para clasificar, leer widgets y buscar marcadores
    doc = fitz.open(pdf_path)
    try:
        perfil = clasificar_doc(doc)
        nombres = _nombres_widgets(doc)
        tiene_marcador, marcador = _texto_tiene_marcador(doc)
    finally:
        doc.close()
    es_pf, detalle_huella = es_formulario_plan_familia(nombres)

    # Editable / parcial: exigir huella Plan Familia antes de extraer
    if perfil.tipo in ("formulario_editable", "formulario_parcial"):
        if es_pf:
            return SeleccionPdf(
                path=pdf_path,
                decision="procesar",
                categoria="solicitud_editable",
                motivo=(
                    f"Solicitud Plan Familia editable ({detalle_huella}"
                    + (f"; marcador '{marcador}'" if marcador else "")
                    + ")"
                ),
                perfil=perfil,
            )
        return SeleccionPdf(
            path=pdf_path,
            decision="ignorar",
            categoria="otro_formulario",
            motivo=(
                "PDF editable pero no es solicitud Plan Familia Salud / Ramo 2500. "
                f"{detalle_huella}"
            ),
            perfil=perfil,
        )

    # Escaneado: solo si nombre o marcadores sugieren solicitud Salud
    # (en Fase 1 igual irá a E1; sirve para el reporte)
    if perfil.tipo.startswith("escaneado"):
        if tiene_marcador or _nombre_sugiere_solicitud(nombre):
            return SeleccionPdf(
                path=pdf_path,
                decision="procesar",
                categoria="solicitud_escaneada",
                motivo=(
                    "Solicitud escaneada detectada por "
                    + (f"marcador '{marcador}'" if marcador else "nombre")
                    + f" ({perfil.tipo})"
                ),
                perfil=perfil,
            )
        return SeleccionPdf(
            path=pdf_path,
            decision="revisar",
            categoria="no_clasificado",
            motivo=f"Escaneo sin señales claras de solicitud: {perfil.tipo}",
            perfil=perfil,
        )

    if perfil.tipo == "formulario_vacio":
        return SeleccionPdf(
            path=pdf_path,
            decision="ignorar",
            categoria="adjunto",
            motivo="Plantilla PDF vacía (sin datos)",
            perfil=perfil,
        )

    return SeleccionPdf(
        path=pdf_path,
        decision="revisar",
        categoria="no_clasificado",
        motivo=f"No clasificado ({perfil.tipo})",
        perfil=perfil,
    )


def seleccionar_lote(pdfs: list[Path]) -> dict[str, list[SeleccionPdf]]:
    """Clasifica un lote en procesar / ignorar / revisar."""
    resultado: dict[str, list[SeleccionPdf]] = {
        "procesar": [],
        "ignorar": [],
        "revisar": [],
    }
    for pdf in pdfs:
        sel = seleccionar_pdf(pdf)
        resultado[sel.decision].append(sel)
    return resultado
