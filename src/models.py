"""Modelos de datos para solicitudes Plan Familia VAVI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class FormaPago(str, Enum):
    EFECTIVO = "efectivo"
    TARJETA = "tarjeta"
    CBU = "cbu"
    DESCONOCIDO = "desconocido"


@dataclass
class Asegurado:
    nombre: str
    tipo_doc: str = "DNI"
    nro_documento: Optional[int] = None
    fecha_nacimiento: Optional[datetime] = None
    sexo: str = ""  # "M" | "F" solo si el PDF trae el campo; si no, vacío
    beneficiario: str = ""
    relacion: str = "Titular"  # Titular | Conyuge | Hijo


@dataclass
class SolicitudSalud:
    archivo_origen: str = ""
    asesor_origen: str = ""
    ruta_origen: str = ""
    apellido_nombre_tomador: str = ""
    tipo_doc_tomador: str = "DNI"
    nro_documento_tomador: Optional[int] = None
    fecha_nacimiento_tomador: Optional[datetime] = None
    calle: str = ""
    nro: str = ""
    piso: str = ""
    dto: str = ""
    codigo_postal: Optional[int] = None
    localidad: str = ""
    provincia: str = ""
    telefono: str = ""
    email: str = ""
    sexo: str = ""  # "M" | "F" solo si el PDF trae el campo; si no, vacío
    actividad: str = ""
    cbu: str = ""
    tarjeta_nombre: str = ""
    tarjeta_numero: str = ""
    forma_pago: FormaPago = FormaPago.DESCONOCIDO
    plan: Optional[str] = None  # "4" | "5" | "6" | "100"
    modulo: Optional[int] = None  # 1 = A, 2 = B
    cantidad_personas: int = 1
    organizador: str = ""
    productor: str = ""
    inicio_vigencia: Optional[datetime] = None
    fin_vigencia: Optional[datetime] = None
    fecha_firma: Optional[datetime] = None
    asegurados: list[Asegurado] = field(default_factory=list)
    metodo_extraccion: str = "desconocido"
    variante_formulario: str = ""  # plan4 | asesores
    tipo_documento: str = ""
    tipo_documento_legible: str = ""

    @property
    def direccion(self) -> str:
        partes = [self.calle.strip(), self.nro.strip(), self.piso.strip(), self.dto.strip()]
        return " ".join(p for p in partes if p)

    @property
    def es_grupo_familiar(self) -> bool:
        return self.cantidad_personas > 1 or len(self.asegurados) > 1

    def asegurar_titular_por_defecto(self) -> None:
        if self.asegurados or not self.apellido_nombre_tomador:
            return
        self.asegurados.append(
            Asegurado(
                nombre=self.apellido_nombre_tomador,
                tipo_doc=self.tipo_doc_tomador,
                nro_documento=self.nro_documento_tomador,
                fecha_nacimiento=self.fecha_nacimiento_tomador,
                sexo=self.sexo,
                beneficiario=self.apellido_nombre_tomador,
                relacion="Titular",
            )
        )


@dataclass
class ErrorProceso:
    archivo: str
    codigo: str  # E1 | E2
    detalle: str
    campos_faltantes: list[str] = field(default_factory=list)
    tipo_documento: str = ""
    tipo_documento_legible: str = ""
    motivo_exclusion: str = ""
    accion_sugerida: str = ""
    campos_faltantes_legibles: list[str] = field(default_factory=list)
    datos_parciales: str = ""
