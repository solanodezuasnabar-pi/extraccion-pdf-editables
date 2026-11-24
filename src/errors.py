"""Construcción de errores enriquecidos para el reporte."""

from __future__ import annotations

from .classifier import PerfilDocumento
from .labels import etiqueta_tipo_documento, etiquetas_campos
from .models import ErrorProceso, SolicitudSalud


def _datos_parciales(solicitud: SolicitudSalud) -> str:
    partes: list[str] = []
    if solicitud.apellido_nombre_tomador:
        partes.append(f"Tomador: {solicitud.apellido_nombre_tomador}")
    if solicitud.nro_documento_tomador:
        partes.append(f"DNI: {solicitud.nro_documento_tomador}")
    if solicitud.plan:
        partes.append(f"Plan: {solicitud.plan}")
    if solicitud.modulo is not None:
        partes.append(f"Módulo: {'A' if solicitud.modulo == 1 else 'B'}")
    if solicitud.forma_pago.value != "desconocido":
        partes.append(f"Pago: {solicitud.forma_pago.value}")
    if solicitud.asegurados:
        partes.append(f"Asegurados detectados: {len(solicitud.asegurados)}")
    return " | ".join(partes) if partes else "Sin datos útiles extraídos"


def error_extraccion(
    archivo: str,
    perfil: PerfilDocumento,
    detalle_extra: str = "",
) -> ErrorProceso:
    if perfil.tipo == "formulario_editable":
        motivo = "Error de extracción (E1): el PDF es editable pero no se pudieron leer los datos."
        detalle = detalle_extra or "Falló la extracción N1 (PyMuPDF) pese a tener campos rellenados."
        accion = perfil.accion_sugerida
    elif perfil.tipo in ("escaneado_imagen", "escaneado_manuscrito"):
        motivo = "Error de extracción (E1): documento escaneado o manuscrito sin campos editables."
        detalle = perfil.descripcion
        if detalle_extra:
            detalle = f"{detalle} {detalle_extra}".strip()
        accion = perfil.accion_sugerida
    elif perfil.tipo == "escaneado_texto":
        motivo = "Error de extracción (E1): escaneo con texto; no soportado aún en Bloque A."
        detalle = perfil.descripcion
        accion = perfil.accion_sugerida
    elif perfil.tipo == "formulario_vacio":
        motivo = "Error de extracción (E1): plantilla PDF sin completar."
        detalle = perfil.descripcion
        accion = perfil.accion_sugerida
    elif perfil.tipo == "formulario_parcial":
        motivo = "Error de extracción (E1): formulario editable con datos insuficientes."
        detalle = perfil.descripcion
        accion = perfil.accion_sugerida
    else:
        motivo = f"Error de extracción (E1): {perfil.descripcion}"
        detalle = detalle_extra or perfil.descripcion
        accion = perfil.accion_sugerida

    return ErrorProceso(
        archivo=archivo,
        codigo="E1",
        detalle=detalle,
        tipo_documento=perfil.tipo,
        tipo_documento_legible=etiqueta_tipo_documento(perfil.tipo),
        motivo_exclusion=motivo,
        accion_sugerida=accion,
        datos_parciales=(
            f"Páginas: {perfil.paginas} | Widgets: {perfil.widgets_rellenos}/{perfil.widgets_total} | "
            f"Texto embebido: {perfil.caracteres_texto} caracteres"
        ),
    )


def error_validacion(
    solicitud: SolicitudSalud,
    perfil: PerfilDocumento,
    campos_faltantes: list[str],
) -> ErrorProceso:
    legibles = etiquetas_campos(campos_faltantes)
    return ErrorProceso(
        archivo=solicitud.archivo_origen,
        codigo="E2",
        detalle=f"Faltan {len(campos_faltantes)} campo(s) obligatorio(s) para la emisión masiva.",
        campos_faltantes=campos_faltantes,
        campos_faltantes_legibles=legibles,
        tipo_documento=perfil.tipo,
        tipo_documento_legible=etiqueta_tipo_documento(perfil.tipo),
        motivo_exclusion=(
            "Error de datos faltantes (E2): la extracción fue parcial pero no alcanza para emitir."
        ),
        accion_sugerida=(
            "En el PDF, completar: "
            + "; ".join(legibles)
            + ". Guardar y re-procesar el mes (o emitir esa solicitud fuera del lote)."
        ),
        datos_parciales=_datos_parciales(solicitud),
    )


def error_excepcion(archivo: str, perfil: PerfilDocumento, exc: Exception) -> ErrorProceso:
    err = error_extraccion(archivo, perfil, detalle_extra=str(exc))
    err.motivo_exclusion = f"Error de extracción (E1): excepción durante el procesamiento ({type(exc).__name__})."
    return err
