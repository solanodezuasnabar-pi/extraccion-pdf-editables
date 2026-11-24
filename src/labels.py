"""Etiquetas legibles para campos y errores del reporte."""

from __future__ import annotations

ETIQUETAS_CAMPO: dict[str, str] = {
    "nro_documento_tomador": "NRO. DE DOCUMENTO (Tomador)",
    "apellido_nombre_tomador": "APELLIDO Y NOMBRES (Tomador)",
    "email": "EMAIL (Titular/Tomador)",
    "inicio_vigencia": "VIGENCIA DESDE",
    "fin_vigencia": "VIGENCIA HASTA",
    "forma_pago": "FORMA DE PAGO",
    "nro_tarjeta": "NÚMERO de tarjeta",
    "codigo_tarjeta": "Tipo de tarjeta (código CE / parametría)",
    "cbu": "CBU / NÚMERO débito",
    "plan": "Plan (MÓDULOS / TIPO PLAN)",
    "modulo": "Módulo de cobertura (A/B)",
    "asegurados": "Sección ASEGURABLES (al menos un asegurado)",
    "direccion": "DIRECCIÓN (Calle / Nro / Piso / Dto)",
    "localidad": "LOCALIDAD",
    "codigo_postal": "CÓD. POSTAL",
    "nro_documento_titular": "NRO. DE DOCUMENTO (Titular)",
    "fecha_nacimiento_titular": "FECHA DE NACIMIENTO (Titular)",
    "productor": "N° PRODUCTOR",
    "organizador": "N° ORGANIZADOR",
}

ETIQUETAS_TIPO_DOCUMENTO: dict[str, str] = {
    "formulario_editable": "Formulario editable (PDF digital)",
    "formulario_parcial": "Formulario editable incompleto",
    "formulario_vacio": "Plantilla vacía (sin datos)",
    "escaneado_texto": "Escaneado con texto",
    "escaneado_imagen": "Escaneado / imagen",
    "escaneado_manuscrito": "Escaneado / posible manuscrito",
    "escaneado_mixto": "Escaneado mixto / baja calidad",
}


# Columna CE → dónde corregir en el PDF de solicitud (formulario Plan Familia).
ACCION_CAMPO_CE: dict[str, str] = {
    "TIPO_DOC_REFERENCIA": "PDF → datos del Tomador: marcar TIPO DE DOC.",
    "NRO_DOCUMENTO_REFERENCIA": "PDF → datos del Tomador: completar NRO. DE DOCUMENTO.",
    "TIPO_DOC_TITULAR": "PDF → fila de esa figura en ASEGURABLES: marcar TIPO DE DOC.",
    "NRO_DOCUMENTO_TITULAR": "PDF → fila de esa figura en ASEGURABLES: completar NRO. DE DOCUMENTO.",
    "APELLIDO_NOMBRE_TITULAR": "PDF → ASEGURABLES: completar APELLIDO Y NOMBRES de esa figura.",
    "FECHA_NACIMIENTO": "PDF → ASEGURABLES: completar FECHA DE NACIMIENTO de esa figura.",
    "DIRECCION": "PDF → domicilio del Tomador: CALLE / NRO / PISO / DTO.",
    "CODIGO_POSTAL": "PDF → domicilio del Tomador: CÓD. POSTAL.",
    "LOCALIDAD": "PDF → domicilio del Tomador: LOCALIDAD.",
    "EMAIL": "PDF → completar EMAIL del Tomador/Titular.",
    "TIPO_DOC_BENEF": "PDF → ASEGURABLES, fila de esa figura: marcar TIPO DE DOC.",
    "NRO_DOCUMENTO_BENEF": "PDF → ASEGURABLES, fila de esa figura: completar NRO. DE DOCUMENTO.",
    "APELLIDO_NOMBRE_BENEF": "PDF → ASEGURABLES: completar APELLIDO Y NOMBRES (o beneficiario) de esa figura.",
    "PAIS_ORIGEN_BENEF": "Dato de parametría del bot (no se carga a mano en el PDF).",
    "INICIO_VIGENCIA": "PDF → completar VIGENCIA DESDE.",
    "FIN_VIGENCIA": "PDF → completar VIGENCIA HASTA (o dejar que el bot derive desde DESDE).",
    "MODULO": "PDF → marcar Módulo A o B (cobertura).",
    "OPCION_COBERTURA": "PDF → marcar el Plan (4 / 5 / 6 / 100) en TIPO PLAN o COBERTURA.",
    "TIPO_COBERTURA": "Se deriva de la cantidad de asegurables; revisar que el grupo familiar esté completo en el PDF.",
    "RELACIÓN_TITULAR": "PDF → ASEGURABLES: asegurar que la fila sea Titular / Cónyuge / Hijo.",
    "TARJETA_CREDITO": "PDF → forma de pago: marcar tipo de tarjeta.",
    "NRO_TARJETA": "PDF → forma de pago: completar NÚMERO de tarjeta.",
    "CBU": "PDF → forma de pago: completar CBU / débito.",
    "EFECTIVO": "PDF → forma de pago: marcar efectivo si corresponde.",
    "ORGANIZADOR": "PDF → completar N° ORGANIZADOR si figura en el formulario.",
    "PRODUCTOR": "PDF → completar N° PRODUCTOR si figura en el formulario.",
    "GRUPO_ESTADISTICO": "Parametría del bot (no se corrige en el PDF).",
}


def etiquetas_campos(codigos: list[str]) -> list[str]:
    out: list[str] = []
    for c in codigos:
        if c.startswith("nro_documento_asegurado:"):
            idx = c.split(":", 1)[1]
            try:
                n = int(idx) + 1
            except ValueError:
                n = idx
            out.append(f"NRO. DE DOCUMENTO (Asegurable #{n})")
        else:
            out.append(ETIQUETAS_CAMPO.get(c, c))
    return out


def etiqueta_tipo_documento(tipo: str) -> str:
    return ETIQUETAS_TIPO_DOCUMENTO.get(tipo, tipo)


def accion_para_campo_ce(campo: str, *, excel_fila: str = "") -> str:
    """Acción concreta para corregir un faltante de columna CE en el PDF."""
    base = ACCION_CAMPO_CE.get(
        campo,
        f"Completar/corregir «{campo}» en el PDF indicado y re-procesar el mes.",
    )
    if excel_fila:
        return f"{base} (revisar Excel de emisión fila {excel_fila})."
    return f"{base} Luego re-procesar el mes."
