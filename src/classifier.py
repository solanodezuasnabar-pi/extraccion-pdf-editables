"""Clasificación del tipo de PDF para enrutar extracción y enriquecer el reporte."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

_NO_VALORES = {"Off", "On", "On1", "On2", "On5", ""}


@dataclass(frozen=True)
class PerfilDocumento:
    tipo: str
    descripcion: str
    widgets_total: int
    widgets_rellenos: int
    caracteres_texto: int
    paginas: int
    accion_sugerida: str


def _widget_relleno(valor) -> bool:
    texto = str(valor).strip() if valor is not None else ""
    return bool(texto) and texto not in _NO_VALORES


def clasificar_pdf(pdf_path: Path) -> PerfilDocumento:
    doc = fitz.open(pdf_path)
    try:
        return clasificar_doc(doc)
    finally:
        doc.close()


def clasificar_doc(doc: fitz.Document) -> PerfilDocumento:
    """Clasifica un documento ya abierto (permite reusar la misma apertura)."""
    widgets_total = 0
    widgets_rellenos = 0
    caracteres_texto = 0
    area_imagen = 0.0
    area_pagina = 0.0

    paginas = doc.page_count
    for page in doc:
        area_pagina += page.rect.width * page.rect.height
        caracteres_texto += len(page.get_text().strip())

        for img in page.get_images(full=True):
            try:
                bbox = page.get_image_bbox(img)
                area_imagen += abs(bbox.width * bbox.height)
            except Exception:
                area_imagen += page.rect.width * page.rect.height * 0.5

        for widget in page.widgets() or []:
            widgets_total += 1
            if _widget_relleno(widget.field_value):
                widgets_rellenos += 1

    ratio_imagen = (area_imagen / area_pagina) if area_pagina else 0.0

    if widgets_total > 0 and widgets_rellenos >= 3:
        return PerfilDocumento(
            tipo="formulario_editable",
            descripcion="PDF con campos de formulario rellenados (extracción directa N1)",
            widgets_total=widgets_total,
            widgets_rellenos=widgets_rellenos,
            caracteres_texto=caracteres_texto,
            paginas=paginas,
            accion_sugerida="Revisar por qué falló la extracción N1; el documento parece editable.",
        )

    if widgets_total > 0 and widgets_rellenos > 0:
        return PerfilDocumento(
            tipo="formulario_parcial",
            descripcion=(
                f"PDF editable con pocos campos completados ({widgets_rellenos}/{widgets_total}). "
                "Puede estar incompleto o ser un escaneo insertado en plantilla."
            ),
            widgets_total=widgets_total,
            widgets_rellenos=widgets_rellenos,
            caracteres_texto=caracteres_texto,
            paginas=paginas,
            accion_sugerida="Completar la solicitud o procesar manualmente; faltan datos en el formulario.",
        )

    if widgets_total > 0 and widgets_rellenos == 0:
        return PerfilDocumento(
            tipo="formulario_vacio",
            descripcion="PDF plantilla con campos de formulario pero sin datos cargados",
            widgets_total=widgets_total,
            widgets_rellenos=0,
            caracteres_texto=caracteres_texto,
            paginas=paginas,
            accion_sugerida="No es una solicitud vendida; descartar o solicitar al asesor el PDF completado.",
        )

    # Sin campos de formulario: escaneo / imagen
    if caracteres_texto >= 300:
        return PerfilDocumento(
            tipo="escaneado_texto",
            descripcion=(
                "PDF escaneado con capa de texto detectable "
                f"({caracteres_texto} caracteres). No tiene campos editables."
            ),
            widgets_total=0,
            widgets_rellenos=0,
            caracteres_texto=caracteres_texto,
            paginas=paginas,
            accion_sugerida="Emitir a mano. El bot no lee escaneos.",
        )

    if ratio_imagen >= 0.4 or caracteres_texto < 80:
        detalle = "PDF escaneado o fotografiado"
        if caracteres_texto < 30:
            detalle += "; probable contenido manuscrito o imagen sin texto embebido"
            tipo = "escaneado_manuscrito"
        else:
            tipo = "escaneado_imagen"
        accion = "Emitir a mano. El bot no lee escaneos."

        return PerfilDocumento(
            tipo=tipo,
            descripcion=(
                f"{detalle}. Sin campos editables; "
                f"texto extraíble={caracteres_texto} chars, "
                f"cobertura imagen≈{ratio_imagen:.0%}."
            ),
            widgets_total=0,
            widgets_rellenos=0,
            caracteres_texto=caracteres_texto,
            paginas=paginas,
            accion_sugerida=accion,
        )

    return PerfilDocumento(
        tipo="escaneado_mixto",
        descripcion=(
            f"PDF sin formulario editable; texto limitado ({caracteres_texto} chars). "
            "Puede ser escaneo de baja calidad o documento mixto."
        ),
        widgets_total=0,
        widgets_rellenos=0,
        caracteres_texto=caracteres_texto,
        paginas=paginas,
        accion_sugerida="Emitir a mano. El bot no lee escaneos.",
    )
