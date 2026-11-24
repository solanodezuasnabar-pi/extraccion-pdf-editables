"""Lote de corrida: snapshot, duplicados ambiguos y publicación atómica."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .periodo import (
    AvisoCarpetaMes,
    Periodo,
    carpeta_mes_para_periodo,
    detectar_carpetas_mal_nombradas,
    listar_asesores,
)
from .models import SolicitudSalud


@dataclass(frozen=True)
class ItemLote:
    asesor: str
    mes_dir: Path
    pdf: Path


@dataclass(frozen=True)
class LoteCorrida:
    periodo: Periodo
    items: tuple[ItemLote, ...] = ()
    avisos: tuple[AvisoCarpetaMes, ...] = ()


def tomar_snapshot(repo_root: Path, periodo: Periodo) -> LoteCorrida:
    """Foto de asesores / carpetas canónicas / PDFs al inicio de la corrida."""
    items: list[ItemLote] = []
    avisos: list[AvisoCarpetaMes] = []
    root = Path(repo_root)
    for asesor in listar_asesores(root):
        avisos.extend(detectar_carpetas_mal_nombradas(asesor))
        mes_dir = carpeta_mes_para_periodo(asesor, periodo)
        if mes_dir is None:
            continue
        pdfs = sorted(mes_dir.glob("**/*.pdf"))
        for pdf in pdfs:
            items.append(ItemLote(asesor=asesor.name, mes_dir=mes_dir, pdf=pdf))
    return LoteCorrida(
        periodo=periodo,
        items=tuple(items),
        avisos=tuple(avisos),
    )


def _dni_clave(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def separar_duplicados_ambiguos(
    solicitudes: list[SolicitudSalud],
    periodo_slug: str,
) -> tuple[list[SolicitudSalud], list[list[SolicitudSalud]]]:
    """Misma clave período+asesor+DNI en 2+ PDFs: ninguno es emitible."""
    grupos: dict[tuple[str, str, int], list[SolicitudSalud]] = {}
    sin_clave: list[SolicitudSalud] = []
    for s in solicitudes:
        dni = _dni_clave(s.nro_documento_tomador)
        asesor = (s.asesor_origen or "").strip()
        if dni is None or not asesor:
            sin_clave.append(s)
            continue
        grupos.setdefault((periodo_slug, asesor, dni), []).append(s)

    emitibles = list(sin_clave)
    ambiguos: list[list[SolicitudSalud]] = []
    for sols in grupos.values():
        if len(sols) >= 2:
            ambiguos.append(sols)
        else:
            emitibles.extend(sols)
    return emitibles, ambiguos


def publicar_archivo(origen: Path, destino: Path) -> Path:
    """Copia origen → destino vía archivo temporal en el mismo directorio."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.stem + ".tmp" + destino.suffix)
    shutil.copy2(origen, tmp)
    os.replace(tmp, destino)
    return destino
