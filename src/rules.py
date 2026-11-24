"""Motor de reglas — mapeo Anexo 3.3 (Especificación V2.0)."""

from __future__ import annotations

from typing import Any

from .models import Asegurado, FormaPago, SolicitudSalud
from .settings import Parametria


def _format_tipo_doc(tipo: str) -> str:
    base = (tipo or "DNI").strip().upper()
    if base not in {"DNI", "LE", "LC", "CI"}:
        base = "DNI"
    return f"{base:<3}  "


def _resolve_tarjeta_codigo(nombre: str, tarjetas: dict[str, int]) -> int | None:
    if not nombre:
        return None
    upper = nombre.strip().upper()
    for key, codigo in tarjetas.items():
        if upper in key or key in upper:
            return codigo
    if "VISA" in upper:
        return tarjetas.get("VISA", 5)
    if "MASTERCARD" in upper or "MASTER" in upper:
        return tarjetas.get("CORDOBESA - MASTERCARD", 20)
    if "NARANJA" in upper:
        return tarjetas.get("NARANJA", 12)
    return None


def _relacion_titular_label(relacion: str) -> str:
    r = (relacion or "").strip()
    low = r.lower().replace("ó", "o")
    if low == "titular":
        return "Titular"
    if low in {"conyuge", "cónyuge"}:
        return "Cónyuge"
    if low in {"hijo", "hija", "hijos"}:
        return "Hijos"
    return r or "Titular"


def _tipo_relacion_asegurado(asegurado: Asegurado) -> str:
    if (asegurado.relacion or "").strip().lower() == "titular":
        return "Asegurado Titular"
    return "Asegurado Familiar"


def _es_relacion_titular(asegurado: Asegurado) -> bool:
    return (asegurado.relacion or "").strip().lower() == "titular"


def _ordenar_asegurados(asegurados: list[Asegurado]) -> list[Asegurado]:
    titulares = [a for a in asegurados if _es_relacion_titular(a)]
    resto = [a for a in asegurados if not _es_relacion_titular(a)]
    return titulares + resto


_PAGO_VACIO: dict[str, Any] = {
    "TARJETA_CREDITO": None,
    "NRO_TARJETA": None,
    "EFECTIVO": None,
    "CBU": None,
}


def _payment_fields(solicitud: SolicitudSalud, tarjeta_codigo: int | None) -> dict[str, Any]:
    """Datos de pago solo para la fila Titular (como ExcelModelo CE)."""
    base = dict(_PAGO_VACIO)
    if solicitud.forma_pago == FormaPago.EFECTIVO:
        base["EFECTIVO"] = 1
    elif solicitud.forma_pago == FormaPago.TARJETA:
        base["TARJETA_CREDITO"] = tarjeta_codigo
        base["NRO_TARJETA"] = solicitud.tarjeta_numero or None
    elif solicitud.forma_pago == FormaPago.CBU:
        base["CBU"] = solicitud.cbu or None
    return base


def _sexo_celda(valor: str | None) -> str | None:
    s = (valor or "").strip().upper()
    if s in {"M", "F", "X"}:
        return s
    if s in {"MASCULINO", "HOMBRE", "MALE"}:
        return "M"
    if s in {"FEMENINO", "MUJER", "FEMALE"}:
        return "F"
    return None


def _fila_base(
    solicitud: SolicitudSalud,
    parametria: Parametria,
    *,
    tipo_relacion: str,
    tipo_doc_figura: str,
    nro_doc_figura: int | None,
    fecha_nacimiento,
    apellido_nombre_titular: str | None,
    email: str | None,
    sexo: str | None,
    opcion: int | None,
    modulo: int | None,
    tipo_cobertura: str | None,
    relacion_titular: str | None,
    benef: dict[str, Any] | None,
    pago: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "TIPO_DOC_REFERENCIA": _format_tipo_doc(solicitud.tipo_doc_tomador),
        "NRO_DOCUMENTO_REFERENCIA": solicitud.nro_documento_tomador,
        "PAIS_ORIGEN_REFERENCIA": parametria.pais_origen,
        "CERTIF_ROL_REF": None,
        "TIPO_RELACION": tipo_relacion,
        "TIPO_DOC_TITULAR": _format_tipo_doc(tipo_doc_figura),
        "NRO_DOCUMENTO_TITULAR": nro_doc_figura,
        "PAIS_ORIGEN_TITULAR": parametria.pais_origen,
        "APELLIDO_NOMBRE_TITULAR": apellido_nombre_titular,
        "FECHA_NACIMIENTO": fecha_nacimiento,
        "SEXO": _sexo_celda(sexo),
        "DIRECCION": solicitud.direccion or None,
        "CODIGO_POSTAL": solicitud.codigo_postal,
        "LOCALIDAD": solicitud.localidad or None,
        "EMAIL": email,
        "SUMA_ASEGURADA": None,
        "INICIO_VIGENCIA": solicitud.inicio_vigencia,
        "FIN_VIGENCIA": solicitud.fin_vigencia,
        "MODULO": modulo,
        "PROPUESTA": None,
        # Solo si el PDF trajo nro numérico; si no, celda vacía.
        "ORGANIZADOR": int(solicitud.organizador) if (solicitud.organizador or "").isdigit() else None,
        "PRODUCTOR": int(solicitud.productor) if (solicitud.productor or "").isdigit() else None,
        "OPCION_COBERTURA": opcion,
        "TIPO_COBERTURA": tipo_cobertura,
        "RELACIÓN_TITULAR": relacion_titular,
        "GRUPO_ESTADISTICO": parametria.grupo_estadistico,
        "TIPO_DOC_BENEF": None,
        "NRO_DOCUMENTO_BENEF": None,
        "PAIS_ORIGEN_BENEF": None,
        "APELLIDO_NOMBRE_BENEF": None,
    }
    row.update(pago)
    if benef:
        row.update(benef)
    return row


def solicitud_a_filas(solicitud: SolicitudSalud, parametria: Parametria) -> list[dict[str, Any]]:
    """Emite Fila Titular (tomador) + una fila por cada figura de ASEGURABLES."""
    solicitud.asegurar_titular_por_defecto()

    tarjeta_codigo = _resolve_tarjeta_codigo(solicitud.tarjeta_nombre, parametria.tarjetas)
    pago = _payment_fields(solicitud, tarjeta_codigo)
    opcion = parametria.opcion_cobertura_por_plan.get(str(solicitud.plan or ""))
    modulo = solicitud.modulo
    tipo_cobertura = "Grupo Familiar" if solicitud.es_grupo_familiar else "Individual"

    email = solicitud.email or None
    sexo_tomador = solicitud.sexo or None
    filas: list[dict[str, Any]] = []

    # 1) Fila Titular = Tomador
    # Operativa real (Hoja1 CE): nombre y email se repiten en Titular y Asegurado.
    filas.append(
        _fila_base(
            solicitud,
            parametria,
            tipo_relacion="Titular",
            tipo_doc_figura=solicitud.tipo_doc_tomador,
            nro_doc_figura=solicitud.nro_documento_tomador,
            fecha_nacimiento=solicitud.fecha_nacimiento_tomador
            or (solicitud.asegurados[0].fecha_nacimiento if solicitud.asegurados else None),
            apellido_nombre_titular=solicitud.apellido_nombre_tomador or None,
            email=email,
            sexo=sexo_tomador,
            opcion=opcion,
            modulo=modulo,
            tipo_cobertura=None,
            relacion_titular=None,
            benef=None,
            pago=pago,
        )
    )

    # 2) Filas Asegurado Titular / Asegurado Familiar (titular de ASEGURABLES primero)
    for asegurado in _ordenar_asegurados(solicitud.asegurados):
        tipo_rel = _tipo_relacion_asegurado(asegurado)
        nombre_figura = (asegurado.nombre or "").strip() or None
        filas.append(
            _fila_base(
                solicitud,
                parametria,
                tipo_relacion=tipo_rel,
                tipo_doc_figura=asegurado.tipo_doc,
                nro_doc_figura=asegurado.nro_documento,
                fecha_nacimiento=asegurado.fecha_nacimiento,
                # Misma columna I que Titular: nombre de la figura (puede repetirse).
                apellido_nombre_titular=nombre_figura,
                # Email del tomador repetido en asegurados (como Hoja1 de referencia).
                email=email,
                # Solo el sexo de esa figura si vino en el PDF; no heredar del tomador.
                sexo=asegurado.sexo or None,
                opcion=opcion,
                modulo=modulo,
                tipo_cobertura=tipo_cobertura,
                relacion_titular=_relacion_titular_label(asegurado.relacion),
                benef={
                    "TIPO_DOC_BENEF": _format_tipo_doc(asegurado.tipo_doc),
                    "NRO_DOCUMENTO_BENEF": asegurado.nro_documento,
                    "PAIS_ORIGEN_BENEF": parametria.pais_origen,
                    "APELLIDO_NOMBRE_BENEF": nombre_figura
                    or (asegurado.beneficiario or None),
                },
                # Pago solo en fila Titular (patrón ExcelModelo CE).
                pago=_PAGO_VACIO,
            )
        )

    return filas
