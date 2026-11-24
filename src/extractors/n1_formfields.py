"""Extracción N1: campos de formulario PDF (PyMuPDF)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz

from ..models import Asegurado, FormaPago, SolicitudSalud
from ..settings import FormulariosConfig, default_formularios
from ..utils import parse_fecha, parse_fecha_partes, parse_int, solo_digitos

_NO_VALORES = {"Off", "On", "On1", "On2", "On5"}

_TIPOS_DOC = ["DNI", "LE", "LC", "CI"]

# Encabezado tipico: "PLAN FAMILIA - PLAN 4" (Anexo 3.5 / variantes del form).
_RE_PLAN_FAMILIA = re.compile(
    r"PLAN\s+FAMILIA\s*[-–—]?\s*PLAN\s*(4|5|6|100)\b",
    re.IGNORECASE,
)
_RE_PLAN_SOLO = re.compile(r"\bPLAN\s*(4|5|6|100)\b", re.IGNORECASE)

# (relacion, nombre, tipo_doc, nro_doc, fecha_nac, beneficiario_keys, sexo_keys)
_FILAS_ASEGURADOS = [
    ("Titular", "APELLIDO Y NOMBRES DEL TITULARRow1", "TIPO DE DOCRow1",
     "NRO DE DOCUMENTORow1", "FECHA DE NACIMIENTORow1",
     ("BENEFICIARIO Apellido Nombre Tipo y Nro de DocRow1", "beneficiario 1"),
     ("Sexo",)),
    ("Conyuge", "APELLIDO Y NOMBRES DEL CÓNYUGERow1", "TIPO DE DOCRow1_2",
     "NRO DE DOCUMENTORow1_2", "FECHA DE NACIMIENTORow1_2",
     ("BENEFICIARIO Apellido Nombre Tipo y Nro de DocRow1_2", "beneficiario 2"),
     ("Sexo_2",)),
    ("Hijo", "APELLIDO Y NOMBRE DE LOS HIJOSRow1", "TIPO DE DOCRow1_3",
     "NRO DE DOCUMENTORow1_3", "FECHA DE NACIMIENTORow1_3", (),
     ("Sexo_3",)),
    ("Hijo", "APELLIDO Y NOMBRE DE LOS HIJOSRow2", "TIPO DE DOCRow2",
     "NRO DE DOCUMENTORow2", "FECHA DE NACIMIENTORow2", (), ()),
    ("Hijo", "APELLIDO Y NOMBRE DE LOS HIJOSRow3", "TIPO DE DOCRow3",
     "NRO DE DOCUMENTORow3", "FECHA DE NACIMIENTORow3", (), ()),
]


@dataclass
class WidgetInfo:
    nombre: str
    valor: str
    x0: float
    y0: float
    # Valor "encendido" de este casillero (grupos radio/check con On/On1/On2).
    on_state: str = ""


def _on_state_de_widget(widget) -> str:
    """Valor que identifica a este casillero dentro de un grupo (PyMuPDF button_states)."""
    try:
        states = widget.button_states() or {}
    except Exception:
        return ""
    normal = states.get("normal") or []
    for estado in normal:
        if estado and str(estado) != "Off":
            return str(estado).strip()
    return ""


def _widget_marcado(w: WidgetInfo) -> bool:
    """True si este casillero es el seleccionado del grupo.

    En grupos TIPO PLAN/COBERTURA todos los widgets reportan el mismo field_value
    (ej. On2). Solo está marcado el cuyo on_state coincide con ese valor.
    """
    if not w.valor or w.valor == "Off":
        return False
    if w.on_state:
        return w.valor == w.on_state
    return True


def _leer_pdf(pdf_path: Path) -> tuple[list[WidgetInfo], str]:
    """Una sola apertura del PDF: widgets del formulario + texto completo."""
    widgets: list[WidgetInfo] = []
    textos: list[str] = []
    doc = fitz.open(pdf_path)
    try:
        for page in doc:
            textos.append(page.get_text("text") or "")
            for widget in page.widgets() or []:
                nombre = (widget.field_name or "").strip()
                if not nombre:
                    continue
                valor = str(widget.field_value).strip() if widget.field_value is not None else ""
                widgets.append(
                    WidgetInfo(
                        nombre,
                        valor,
                        widget.rect.x0,
                        widget.rect.y0,
                        on_state=_on_state_de_widget(widget),
                    )
                )
    finally:
        doc.close()
    return widgets, "\n".join(textos)


def _plan_desde_encabezado(texto: str) -> str | None:
    """Plan 4/5/6/100 desde el título impreso del formulario (prioridad alta)."""
    if not texto:
        return None
    m = _RE_PLAN_FAMILIA.search(texto)
    if m:
        return m.group(1)
    # Fallback: primer "PLAN N" en la zona de encabezado de las primeras páginas.
    m = _RE_PLAN_SOLO.search(texto[:3000])
    if m:
        return m.group(1)
    return None


def _campos_por_nombre(widgets: list[WidgetInfo]) -> dict[str, list[str]]:
    campos: dict[str, list[str]] = {}
    for w in widgets:
        if w.valor and w.valor not in _NO_VALORES:
            campos.setdefault(w.nombre, []).append(w.valor)
    return campos


def _primero(campos: dict[str, list[str]], *nombres: str, default: str = "") -> str:
    for nombre in nombres:
        for valor in campos.get(nombre, []):
            if valor:
                return valor
    return default


def _normalizar_sexo(valor: str) -> str:
    """Devuelve M/F si el PDF trae sexo reconocible; si no, cadena vacía."""
    s = (valor or "").strip().upper()
    if s in {"M", "F", "X"}:
        return s
    if s in {"MASCULINO", "HOMBRE", "MALE"}:
        return "M"
    if s in {"FEMENINO", "MUJER", "FEMALE"}:
        return "F"
    return ""


def _codigo_asesor(valor: str) -> str:
    """Solo dígitos del nro organizador/productor (ej. '221403 (Lopez)' → '221403')."""
    return solo_digitos(valor)


def _tipo_doc_desde_checkboxes(widgets: list[WidgetInfo], prefijo: str = "DNI") -> str:
    """Detecta DNI/LE/LC/CI por nombre de checkbox marcado (no por posición)."""
    for tipo in _TIPOS_DOC:
        if any(w.nombre.upper() == tipo and w.valor not in ("", "Off") for w in widgets):
            return tipo
    # Fallback: widgets del grupo nombrados como el prefijo (habitualmente DNI)
    if any(w.nombre.upper() == prefijo.upper() and w.valor not in ("", "Off") for w in widgets):
        return prefijo.upper() if prefijo.upper() in _TIPOS_DOC else "DNI"
    return "DNI"


def _detectar_variante(widgets: list[WidgetInfo], plan_texto: str | None = None) -> str:
    """Plan 4 vs Asesores.

    Prioriza el plan del encabezado. Un COBERTURA marcado suelto no fuerza Asesores
    si el título dice PLAN 4 (caso típico de PDF mergeados).
    """
    if plan_texto == "4":
        return "plan4"
    if plan_texto in {"5", "6", "100"}:
        return "asesores"

    nombres = {w.nombre for w in widgets}
    if "TIPO PLAN" in nombres:
        return "asesores"
    if any(w.nombre == "COBERTURA" and _widget_marcado(w) for w in widgets):
        return "asesores"
    return "plan4"


def _detectar_forma_pago(widgets: list[WidgetInfo]) -> FormaPago:
    pago = [w for w in widgets if w.nombre == "PAGO"]
    marcados = [w for w in pago if _widget_marcado(w)]
    if not marcados and not any(w.valor and w.valor != "Off" for w in pago):
        return FormaPago.DESCONOCIDO

    # Valor de export del grupo (On/On1/On2), si existe.
    valores = {w.valor for w in pago if w.valor and w.valor != "Off"}
    if "On2" in valores:
        return FormaPago.CBU
    if "On1" in valores:
        return FormaPago.TARJETA
    if "On" in valores:
        if marcados:
            marcados.sort(key=lambda w: w.x0)
            # Posición entre los tres casilleros PAGO (izq→der).
            grupo = sorted(pago, key=lambda w: w.x0)
            for i, w in enumerate(grupo[:3]):
                if _widget_marcado(w):
                    return [FormaPago.EFECTIVO, FormaPago.TARJETA, FormaPago.CBU][i]
        return FormaPago.TARJETA
    return FormaPago.DESCONOCIDO


def _clasificar_numero_pago(digitos: str) -> FormaPago | None:
    """Clasifica un número por longitud: CBU (22) vs tarjeta (13–19, típ. 15–16)."""
    n = len(digitos)
    if n == 0:
        return None
    if n == 22:
        return FormaPago.CBU
    if 13 <= n <= 19:
        return FormaPago.TARJETA
    return None


def _inferir_forma_pago_por_numeros(
    tarjeta_numero: str,
    cbu: str,
    tarjeta_nombre: str = "",
) -> tuple[FormaPago, str, str]:
    """
    Cuando el checkbox PAGO está vacío, deduce forma de pago por los números cargados.

    Returns:
        (forma_pago, tarjeta_numero_normalizado, cbu_normalizado)
    """
    tarjeta_numero = solo_digitos(tarjeta_numero)
    cbu = solo_digitos(cbu)

    tipo_campo_tarjeta = _clasificar_numero_pago(tarjeta_numero)
    tipo_campo_cbu = _clasificar_numero_pago(cbu)

    # Caso ideal: cada campo tiene el tipo esperado
    if tipo_campo_cbu == FormaPago.CBU and tipo_campo_tarjeta != FormaPago.CBU:
        return FormaPago.CBU, "" if tipo_campo_tarjeta != FormaPago.TARJETA else tarjeta_numero, cbu
    if tipo_campo_tarjeta == FormaPago.TARJETA and tipo_campo_cbu != FormaPago.TARJETA:
        return FormaPago.TARJETA, tarjeta_numero, "" if tipo_campo_cbu != FormaPago.CBU else cbu

    # Número en el campo "equivocado" (ej. CBU pegado en NÚMERO de tarjeta)
    if tipo_campo_tarjeta == FormaPago.CBU and not cbu:
        return FormaPago.CBU, "", tarjeta_numero
    if tipo_campo_cbu == FormaPago.TARJETA and not tarjeta_numero:
        return FormaPago.TARJETA, cbu, ""

    # Ambos campos con algo: priorizar CBU de 22 dígitos, luego tarjeta
    if tipo_campo_cbu == FormaPago.CBU:
        return FormaPago.CBU, tarjeta_numero if tipo_campo_tarjeta == FormaPago.TARJETA else "", cbu
    if tipo_campo_tarjeta == FormaPago.TARJETA:
        return FormaPago.TARJETA, tarjeta_numero, cbu if tipo_campo_cbu == FormaPago.CBU else ""

    # Solo nombre de tarjeta sin número aún
    if tarjeta_nombre.strip() and not tarjeta_numero and not cbu:
        return FormaPago.TARJETA, "", ""

    return FormaPago.DESCONOCIDO, tarjeta_numero, cbu


def _detectar_plan(
    widgets: list[WidgetInfo],
    variante: str,
    plan_texto: str | None = None,
    formularios: FormulariosConfig | None = None,
) -> str | None:
    """Orden: encabezado impreso → TIPO PLAN (Asesores) → default Plan 4."""
    cfg = formularios or default_formularios()
    if plan_texto:
        return plan_texto

    var = cfg.variantes.get(variante)
    if var is None:
        return None

    # plan4 (u otras sin grupo TIPO PLAN): plan_default
    if var.plan is None:
        return str(var.plan_default) if var.plan_default else None

    plan_cfg = var.plan
    tipo_plan = [w for w in widgets if w.nombre == plan_cfg.campo]
    if not tipo_plan:
        return str(var.plan_default) if var.plan_default else None

    for w in tipo_plan:
        if w.valor in plan_cfg.por_export:
            return str(plan_cfg.por_export[w.valor])

    tipo_plan.sort(key=lambda w: w.y0)
    planes = list(plan_cfg.por_orden_y) or ["5", "6", "100"]
    for i, w in enumerate(tipo_plan):
        if _widget_marcado(w):
            return planes[min(i, len(planes) - 1)]
    return str(var.plan_default) if var.plan_default else None


def _detectar_modulo(
    widgets: list[WidgetInfo],
    variante: str,
    formularios: FormulariosConfig | None = None,
) -> int | None:
    cfg = formularios or default_formularios()
    var = cfg.variantes.get(variante)
    if var is None:
        return None
    mod = var.modulo

    # Variante tipo plan4: campos A/B nombrados + fallback posicional
    if mod.campos_a or mod.campos_b:
        nombres_a = set(mod.campos_a)
        nombres_b = set(mod.campos_b)
        checks = [w for w in widgets if w.nombre in nombres_a and _widget_marcado(w)]
        if not checks:
            checks_b = [w for w in widgets if w.nombre in nombres_b and _widget_marcado(w)]
            if checks_b:
                return cfg.valor_modulo("B")
            return cfg.valor_modulo("A")
        if not mod.usar_posicion_xy:
            return cfg.valor_modulo("A")
        checks.sort(key=lambda w: (w.y0, w.x0))
        filas: dict[float, list[WidgetInfo]] = {}
        for w in checks:
            filas.setdefault(round(w.y0, 0), []).append(w)
        for fila in sorted(filas.values(), key=lambda f: f[0].y0):
            fila.sort(key=lambda w: w.x0)
            grupo = sorted(
                [x for x in widgets if x.nombre in nombres_a and round(x.y0, 0) == round(fila[0].y0, 0)],
                key=lambda w: w.x0,
            )
            if not grupo:
                grupo = fila
            for i, w in enumerate(grupo):
                if _widget_marcado(w):
                    etiqueta = "A" if i == 0 else "B"
                    return cfg.valor_modulo(etiqueta)
        return cfg.valor_modulo("A")

    # Variante tipo asesores: un campo (COBERTURA) + export / orden Y
    if not mod.campo:
        return None
    cobertura = [w for w in widgets if w.nombre == mod.campo]
    if not cobertura:
        return None

    for w in cobertura:
        if w.valor in mod.por_export:
            return cfg.valor_modulo(mod.por_export[w.valor])

    cobertura.sort(key=lambda w: w.y0)
    orden = list(mod.por_orden_y) or ["A", "B"]
    for idx, w in enumerate(cobertura):
        if _widget_marcado(w):
            etiqueta = orden[min(idx, len(orden) - 1)]
            return cfg.valor_modulo(etiqueta)
    return None


def _extraer_asegurados(campos: dict[str, list[str]]) -> list[Asegurado]:
    asegurados: list[Asegurado] = []
    for relacion, k_nombre, k_tipo, k_nro, k_fecha, k_benef, k_sexo in _FILAS_ASEGURADOS:
        nombre = _primero(campos, k_nombre).strip().upper()
        if not nombre:
            continue
        asegurados.append(
            Asegurado(
                nombre=nombre,
                tipo_doc=_primero(campos, k_tipo, default="DNI").upper(),
                nro_documento=parse_int(_primero(campos, k_nro)),
                fecha_nacimiento=parse_fecha(_primero(campos, k_fecha)),
                sexo=_normalizar_sexo(_primero(campos, *k_sexo)) if k_sexo else "",
                beneficiario=(_primero(campos, *k_benef) or nombre).upper(),
                relacion=relacion,
            )
        )
    return asegurados


def extract_from_form_fields(
    pdf_path: Path,
    formularios: FormulariosConfig | None = None,
) -> SolicitudSalud | None:
    widgets, texto_pdf = _leer_pdf(pdf_path)
    if not widgets:
        return None

    if formularios is None:
        try:
            from ..settings import cargar_parametria

            formularios = cargar_parametria().formularios
        except Exception:
            formularios = default_formularios()

    campos = _campos_por_nombre(widgets)
    nombre = _primero(campos, "APELLIDO Y NOMBRES")
    documento = _primero(campos, "undefined", "undefined 2")
    if not (nombre or documento):
        return None

    plan_texto = _plan_desde_encabezado(texto_pdf)
    variante = _detectar_variante(widgets, plan_texto=plan_texto)
    solicitud = SolicitudSalud(
        archivo_origen=pdf_path.name,
        metodo_extraccion="formulario_pdf",
        variante_formulario=variante,
    )

    solicitud.apellido_nombre_tomador = nombre.upper()
    solicitud.tipo_doc_tomador = _tipo_doc_desde_checkboxes(widgets, "DNI")
    solicitud.nro_documento_tomador = parse_int(documento)
    solicitud.fecha_nacimiento_tomador = parse_fecha_partes(
        _primero(campos, "Text1"), _primero(campos, "Text1 2"), _primero(campos, "Text1 3")
    )

    solicitud.calle = _primero(campos, "CALLE").upper()
    solicitud.nro = _primero(campos, "NRO").upper()
    solicitud.piso = _primero(campos, "PISO").upper()
    solicitud.dto = _primero(campos, "DTO").upper()
    solicitud.codigo_postal = parse_int(_primero(campos, "CÓD POSTAL", "CÓD. POSTAL"))
    solicitud.localidad = _primero(campos, "LOCALIDAD").upper()
    solicitud.provincia = _primero(campos, "PROVINCIA").upper()
    solicitud.telefono = _primero(campos, "TELÉFONO")
    solicitud.email = _primero(campos, "EMAIL", "EMAIL_2", "EMAIL_3").lower()
    solicitud.actividad = _primero(campos, "ACTIVIDAD PRINCIPAL").upper()

    # Solo si el PDF trae el campo; si no, quedan vacíos (Excel en blanco).
    solicitud.organizador = _codigo_asesor(
        _primero(campos, "ORGANIZADOR NRORow1", "Organizador", "ORGANIZADOR")
    )
    solicitud.productor = _codigo_asesor(
        _primero(campos, "PRODUCTOR NRORow1", "Productor", "PRODUCTOR")
    )
    # Sexo del tomador: Plan Familia suele no traerlo; otras variantes sí (Sexo).
    solicitud.sexo = _normalizar_sexo(_primero(campos, "Sexo", "SEXO"))
    solicitud.inicio_vigencia = parse_fecha_partes(
        _primero(campos, "VIGENCIA DESDERow1"),
        _primero(campos, "VIGENCIA DESDERow1_2"),
        _primero(campos, "VIGENCIA DESDERow1_3"),
    )
    solicitud.fin_vigencia = parse_fecha_partes(
        _primero(campos, "VIGENCIA HASTARow1"),
        _primero(campos, "VIGENCIA HASTARow1_2"),
        _primero(campos, "VIGENCIA HASTARow1_3"),
    )
    # Plan Familia suele usar Fecha/Fecha1/Fecha2 (día/mes/año) al pie;
    # Text5–7 queda como fallback por si aparece en otra variante del form.
    solicitud.fecha_firma = parse_fecha_partes(
        _primero(campos, "Fecha", "Text5"),
        _primero(campos, "Fecha1", "Text6"),
        _primero(campos, "Fecha2", "Text7"),
    )

    solicitud.forma_pago = _detectar_forma_pago(widgets)
    solicitud.tarjeta_nombre = _primero(campos, "NOMBRE TARJETA")
    solicitud.tarjeta_numero = solo_digitos(_primero(campos, "NÚMERO"))
    solicitud.cbu = solo_digitos(_primero(campos, "NÚMERO_2"))

    # Inferencia: checkbox vacío pero hay CBU (22 dígitos) o tarjeta (13–19) cargados
    if solicitud.forma_pago == FormaPago.DESCONOCIDO:
        forma, nro_tj, nro_cbu = _inferir_forma_pago_por_numeros(
            solicitud.tarjeta_numero,
            solicitud.cbu,
            solicitud.tarjeta_nombre,
        )
        solicitud.forma_pago = forma
        solicitud.tarjeta_numero = nro_tj
        solicitud.cbu = nro_cbu
    else:
        # Aun con checkbox, corregir si el número está en el campo equivocado
        if solicitud.forma_pago == FormaPago.CBU and not solicitud.cbu and len(solicitud.tarjeta_numero) == 22:
            solicitud.cbu = solicitud.tarjeta_numero
            solicitud.tarjeta_numero = ""
        elif solicitud.forma_pago == FormaPago.TARJETA and not solicitud.tarjeta_numero and 13 <= len(solicitud.cbu) <= 19:
            solicitud.tarjeta_numero = solicitud.cbu
            solicitud.cbu = ""

    solicitud.plan = _detectar_plan(
        widgets, variante, plan_texto=plan_texto, formularios=formularios
    )
    solicitud.modulo = _detectar_modulo(widgets, variante, formularios=formularios)

    solicitud.cantidad_personas = parse_int(_primero(campos, "indique en numeros cantidad de personas")) or 1
    solicitud.asegurados = _extraer_asegurados(campos)
    solicitud.asegurar_titular_por_defecto()

    return solicitud
