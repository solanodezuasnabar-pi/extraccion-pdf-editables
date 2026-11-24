"""Resolución de rutas para script y ejecutable PyInstaller."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Carpeta operable: junto al .exe (frozen) o raíz del proyecto (script)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """Recursos embebidos (_MEIPASS) o raíz del proyecto."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return app_root()


def resolve_existing(*parts: str) -> Path | None:
    """Busca un archivo/carpeta primero junto al exe, luego en el bundle."""
    for root in (app_root(), resource_root()):
        candidate = root.joinpath(*parts)
        if candidate.exists():
            return candidate
    return None


def workspace_root() -> Path:
    """Raíz del workspace (hermana de la carpeta del bot / del .exe)."""
    return app_root().parent
