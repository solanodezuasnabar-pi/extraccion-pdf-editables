"""Lista de completitud: completa vs incompleta (hoja Incompletos)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import SolicitudSalud
from .settings import Parametria, cargar_parametria


@dataclass
class ResultadoCompletitud:
    """Resultado de evaluar la lista de completitud sobre una solicitud."""

    faltantes: list[str] = field(default_factory=list)
    blank_tomador_dni: bool = False
    blank_dni_figuras: list[int] = field(default_factory=list)  # índices en asegurados
    blank_direccion: bool = False
    blank_codigo_postal: bool = False
    blank_modulo: bool = False
    blank_plan: bool = False
    blank_inicio_vigencia: bool = False
    blank_fin_vigencia: bool = False
    blank_productor: bool = False
    blank_organizador: bool = False

    @property
    def completa(self) -> bool:
        return not self.faltantes


def evaluar_completitud(
    solicitud: SolicitudSalud,
    parametria: Parametria | None = None,
) -> ResultadoCompletitud:
    """
    Solo la lista acordada decide completa vs incompleta.
    Email / localidad / fecha nac. no integran esta lista.
    Plan y módulo sí. El pago no: inválido o faltante se emite como efectivo.
    """
    if parametria is None:
        parametria = cargar_parametria()
    solicitud.asegurar_titular_por_defecto()
    r = ResultadoCompletitud()

    if not solicitud.nro_documento_tomador:
        r.faltantes.append("nro_documento_tomador")
        r.blank_tomador_dni = True

    if not solicitud.asegurados:
        r.faltantes.append("asegurados")
    else:
        for idx, aseg in enumerate(solicitud.asegurados):
            if not aseg.nro_documento:
                r.faltantes.append(f"nro_documento_asegurado:{idx}")
                r.blank_dni_figuras.append(idx)

    if not solicitud.direccion:
        r.faltantes.append("direccion")
        r.blank_direccion = True

    if not solicitud.codigo_postal:
        r.faltantes.append("codigo_postal")
        r.blank_codigo_postal = True

    if solicitud.modulo is None:
        r.faltantes.append("modulo")
        r.blank_modulo = True

    plan_key = str(solicitud.plan or "").strip()
    if not plan_key or plan_key not in parametria.opcion_cobertura_por_plan:
        r.faltantes.append("plan")
        r.blank_plan = True

    if not solicitud.inicio_vigencia:
        r.faltantes.append("inicio_vigencia")
        r.blank_inicio_vigencia = True

    if not solicitud.fin_vigencia:
        r.faltantes.append("fin_vigencia")
        r.blank_fin_vigencia = True

    if not (solicitud.productor or "").strip():
        r.faltantes.append("productor")
        r.blank_productor = True

    if not (solicitud.organizador or "").strip():
        r.faltantes.append("organizador")
        r.blank_organizador = True

    return r


def aplicar_blancos_completitud(
    filas: list[dict],
    resultado: ResultadoCompletitud,
) -> list[dict]:
    """Deja en blanco solo los campos de la lista que faltan (carga manual).

    Marca en cada fila la clave interna ``_celdas_faltantes`` (set de headers)
    para que el Excel pueda colorear esas celdas.
    """
    if resultado.completa:
        return filas

    out: list[dict] = []
    for i, fila in enumerate(filas):
        row = dict(fila)
        faltantes: set[str] = set()

        def _blank(header: str) -> None:
            row[header] = None
            faltantes.add(header)

        if resultado.blank_tomador_dni:
            _blank("NRO_DOCUMENTO_REFERENCIA")
            if row.get("TIPO_RELACION") == "Titular":
                _blank("NRO_DOCUMENTO_TITULAR")

        if i >= 1:
            aseg_idx = i - 1
            if aseg_idx in resultado.blank_dni_figuras:
                _blank("NRO_DOCUMENTO_TITULAR")
                _blank("NRO_DOCUMENTO_BENEF")

        if resultado.blank_direccion:
            _blank("DIRECCION")
        if resultado.blank_codigo_postal:
            _blank("CODIGO_POSTAL")
        if resultado.blank_modulo:
            _blank("MODULO")
        if resultado.blank_plan:
            _blank("OPCION_COBERTURA")
        if resultado.blank_inicio_vigencia:
            _blank("INICIO_VIGENCIA")
        if resultado.blank_fin_vigencia:
            _blank("FIN_VIGENCIA")
        if resultado.blank_productor:
            _blank("PRODUCTOR")
        if resultado.blank_organizador:
            _blank("ORGANIZADOR")

        row["_celdas_faltantes"] = faltantes
        out.append(row)
    return out
