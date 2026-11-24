"""Utilidades de parseo compartidas."""

from __future__ import annotations

import re
from datetime import datetime

_FECHA_FORMATOS = ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y")


def solo_digitos(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def parse_int(value: str) -> int | None:
    digits = solo_digitos(value)
    return int(digits) if digits else None


def parse_fecha(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in _FECHA_FORMATOS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    partes = re.split(r"[/\-\s]+", value)
    if len(partes) == 3:
        try:
            d, m, y = (int(p) for p in partes)
            if y < 100:
                y += 2000 if y < 50 else 1900
            return datetime(y, m, d)
        except ValueError:
            pass
    return None


def parse_fecha_partes(dia: str, mes: str, anio: str) -> datetime | None:
    if not (dia and mes and anio):
        return None
    return parse_fecha(f"{dia}/{mes}/{anio}")
