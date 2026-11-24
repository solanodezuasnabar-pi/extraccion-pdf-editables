"""Validación de completitud — clasifica completa vs incompleta (no excluye del Excel)."""

from __future__ import annotations

from .completitud import ResultadoCompletitud, evaluar_completitud
from .models import SolicitudSalud

# Re-export para callers existentes.
__all__ = ["evaluar_completitud_solicitud", "ResultadoCompletitud"]


def evaluar_completitud_solicitud(solicitud: SolicitudSalud) -> ResultadoCompletitud:
    return evaluar_completitud(solicitud)
