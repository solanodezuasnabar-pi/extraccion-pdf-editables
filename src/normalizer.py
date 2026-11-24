"""Normalización post-extracción."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta

from .extractors.n1_formfields import extract_from_form_fields
from .models import FormaPago, SolicitudSalud
from .periodo import parse_periodo_carpeta
from .rules import _resolve_tarjeta_codigo
from .settings import Parametria, cargar_parametria
from .utils import solo_digitos


def _vigencia_desde_periodo(periodo_ref: datetime) -> tuple[datetime, datetime]:
    """Inicio = día 1 del mes siguiente a la carpeta de ventas; fin = ese día al año siguiente."""
    inicio = datetime(periodo_ref.year, periodo_ref.month, 1) + relativedelta(months=1)
    return inicio, inicio + relativedelta(years=1)


def aplicar_pago_o_efectivo(
    solicitud: SolicitudSalud,
    parametria: Parametria | None = None,
) -> SolicitudSalud:
    """CBU/tarjeta válidos se copian; cualquier error o faltante → efectivo."""
    parametria = parametria or cargar_parametria()
    valido = False
    if solicitud.forma_pago == FormaPago.EFECTIVO:
        valido = True
    elif solicitud.forma_pago == FormaPago.CBU:
        valido = len((solicitud.cbu or "").strip()) == 22
    elif solicitud.forma_pago == FormaPago.TARJETA:
        nro = (solicitud.tarjeta_numero or "").strip()
        valido = (
            13 <= len(nro) <= 19
            and _resolve_tarjeta_codigo(solicitud.tarjeta_nombre, parametria.tarjetas) is not None
        )
    if valido:
        return solicitud
    solicitud.forma_pago = FormaPago.EFECTIVO
    solicitud.cbu = ""
    solicitud.tarjeta_numero = ""
    solicitud.tarjeta_nombre = ""
    return solicitud


def normalizar(
    solicitud: SolicitudSalud,
    periodo_ref: datetime | None = None,
    parametria: Parametria | None = None,
) -> SolicitudSalud:
    if solicitud.inicio_vigencia and not solicitud.fin_vigencia:
        solicitud.fin_vigencia = solicitud.inicio_vigencia + relativedelta(years=1)
    elif (
        not solicitud.inicio_vigencia
        and not solicitud.fin_vigencia
        and periodo_ref is not None
    ):
        solicitud.inicio_vigencia, solicitud.fin_vigencia = _vigencia_desde_periodo(periodo_ref)

    solicitud.apellido_nombre_tomador = solicitud.apellido_nombre_tomador.strip().upper()
    solicitud.calle = solicitud.calle.strip().upper()
    solicitud.nro = solicitud.nro.strip().upper()
    solicitud.piso = solicitud.piso.strip().upper()
    solicitud.dto = solicitud.dto.strip().upper()
    solicitud.localidad = solicitud.localidad.strip().upper()
    solicitud.provincia = solicitud.provincia.strip().upper()
    solicitud.email = solicitud.email.strip().lower()

    solicitud.cbu = solo_digitos(solicitud.cbu)
    solicitud.tarjeta_numero = solo_digitos(solicitud.tarjeta_numero)

    # Inferir forma de pago si quedó desconocida tras la extracción
    if solicitud.forma_pago == FormaPago.DESCONOCIDO:
        if len(solicitud.cbu) == 22:
            solicitud.forma_pago = FormaPago.CBU
        elif 13 <= len(solicitud.tarjeta_numero) <= 19:
            solicitud.forma_pago = FormaPago.TARJETA
        elif len(solicitud.tarjeta_numero) == 22 and not solicitud.cbu:
            # CBU pegado en el campo de tarjeta
            solicitud.cbu = solicitud.tarjeta_numero
            solicitud.tarjeta_numero = ""
            solicitud.forma_pago = FormaPago.CBU
        elif 13 <= len(solicitud.cbu) <= 19 and not solicitud.tarjeta_numero:
            solicitud.tarjeta_numero = solicitud.cbu
            solicitud.cbu = ""
            solicitud.forma_pago = FormaPago.TARJETA
        elif solicitud.tarjeta_nombre.strip():
            solicitud.forma_pago = FormaPago.TARJETA

    if solicitud.forma_pago == FormaPago.CBU and not solicitud.cbu:
        solicitud.forma_pago = FormaPago.DESCONOCIDO
    if solicitud.forma_pago == FormaPago.TARJETA and not solicitud.tarjeta_numero and not solicitud.tarjeta_nombre:
        solicitud.forma_pago = FormaPago.DESCONOCIDO

    aplicar_pago_o_efectivo(solicitud, parametria)

    solicitud.cantidad_personas = max(solicitud.cantidad_personas, len(solicitud.asegurados), 1)

    for asegurado in solicitud.asegurados:
        asegurado.nombre = asegurado.nombre.strip().upper()
        asegurado.beneficiario = (asegurado.beneficiario or asegurado.nombre).strip().upper()
        asegurado.tipo_doc = (asegurado.tipo_doc or "DNI").strip().upper()

    return solicitud


def extraer_pdf(
    pdf_path: Path,
    periodo_ref: datetime | None = None,
) -> SolicitudSalud | None:
    solicitud = extract_from_form_fields(pdf_path)
    if not solicitud:
        return None
    if periodo_ref is None:
        periodo = parse_periodo_carpeta(pdf_path.parent.name)
        if periodo is None:
            periodo = parse_periodo_carpeta(pdf_path.parent.parent.name)
        if periodo is not None:
            periodo_ref = datetime(periodo.anio, periodo.mes, 1)
    return normalizar(solicitud, periodo_ref=periodo_ref)
