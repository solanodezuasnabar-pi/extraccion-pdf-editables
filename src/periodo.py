"""Resolución de períodos mensuales en la estructura tipo SharePoint."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

CARPETA_SOLICITUDES = "SOLICITUDES ESCANEADAS"

_MESES: dict[str, int] = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

_MESES_PATTERN = "|".join(_MESES.keys())

# Formato operativo acordado: "002 VTAS FEBRERO 26"
_RE_MES_CANONICO = re.compile(
    rf"^\d{{2,3}}\s+VTAS\s+(?P<mes>{_MESES_PATTERN})\s+(?P<anio>\d{{2}})$",
    re.IGNORECASE,
)

# Detección laxa (legacy) para avisar carpetas mal nombradas
_RE_MES_LAXO = re.compile(
    r"(?i)(?P<mes>" + _MESES_PATTERN + r")\s*(?P<anio>\d{2,4})\b"
)


@dataclass(frozen=True)
class Periodo:
    anio: int
    mes: int

    @property
    def etiqueta(self) -> str:
        nombre = next(
            (k.title() for k, v in _MESES.items() if v == self.mes and k != "SETIEMBRE"),
            str(self.mes),
        )
        return f"{nombre} {self.anio}"

    @property
    def slug(self) -> str:
        return f"{self.mes:02d}_{self.anio}"

    def __lt__(self, other: Periodo) -> bool:
        return (self.anio, self.mes) < (other.anio, other.mes)


@dataclass(frozen=True)
class AvisoCarpetaMes:
    nombre_carpeta: str
    motivo: str
    periodo_aproximado: str | None = None


def _normalizar_anio(raw: str | int) -> int:
    n = int(raw)
    if n < 100:
        return 2000 + n
    return n


def parse_periodo_carpeta(nombre: str) -> Periodo | None:
    """Obtiene (año, mes) solo si el nombre cumple formato canónico NNN VTAS MES AA."""
    m = _RE_MES_CANONICO.match(nombre.replace("_", " ").strip())
    if not m:
        return None
    mes = _MESES[m.group("mes").upper()]
    anio = _normalizar_anio(m.group("anio"))
    return Periodo(anio=anio, mes=mes)


def parse_periodo_carpeta_laxo(nombre: str) -> Periodo | None:
    """Regex legacy para detectar carpetas que parecen mes pero no son canónicas."""
    m = _RE_MES_LAXO.search(nombre.replace("_", " "))
    if not m:
        return None
    mes = _MESES[m.group("mes").upper()]
    anio = _normalizar_anio(m.group("anio"))
    return Periodo(anio=anio, mes=mes)


def periodo_calendario_actual(fecha_ref: date | datetime | None = None) -> Periodo:
    if fecha_ref is None:
        hoy = date.today()
    elif isinstance(fecha_ref, datetime):
        hoy = fecha_ref.date()
    else:
        hoy = fecha_ref
    return Periodo(anio=hoy.year, mes=hoy.month)


def listar_asesores(repo_root: Path) -> list[Path]:
    if not repo_root.is_dir():
        return []
    return sorted(
        p
        for p in repo_root.iterdir()
        if p.is_dir() and not p.name.startswith("_") and (p / CARPETA_SOLICITUDES).is_dir()
    )


def carpetas_canonicas_para_periodo(asesor_dir: Path, periodo: Periodo) -> list[Path]:
    escaneadas = asesor_dir / CARPETA_SOLICITUDES
    if not escaneadas.is_dir():
        return []
    out: list[Path] = []
    for d in escaneadas.iterdir():
        if not d.is_dir():
            continue
        p = parse_periodo_carpeta(d.name)
        if p == periodo:
            out.append(d)
    return sorted(out, key=lambda x: x.name)


def carpetas_mes_asesor(asesor_dir: Path) -> list[tuple[Periodo, Path]]:
    escaneadas = asesor_dir / CARPETA_SOLICITUDES
    if not escaneadas.is_dir():
        return []
    out: list[tuple[Periodo, Path]] = []
    for d in escaneadas.iterdir():
        if not d.is_dir():
            continue
        periodo = parse_periodo_carpeta(d.name)
        if periodo is None:
            continue
        if not any(d.rglob("*.pdf")):
            continue
        out.append((periodo, d))
    return out


def detectar_carpetas_mal_nombradas(asesor_dir: Path) -> list[AvisoCarpetaMes]:
    """Carpetas bajo SOLICITUDES ESCANEADAS que parecen mes pero no cumplen formato canónico."""
    escaneadas = asesor_dir / CARPETA_SOLICITUDES
    if not escaneadas.is_dir():
        return []
    avisos: list[AvisoCarpetaMes] = []
    for d in escaneadas.iterdir():
        if not d.is_dir():
            continue
        nombre = d.name
        if parse_periodo_carpeta(nombre) is not None:
            continue
        laxo = parse_periodo_carpeta_laxo(nombre)
        if laxo is not None:
            avisos.append(
                AvisoCarpetaMes(
                    nombre_carpeta=nombre,
                    motivo="Formato no canónico (use NNN VTAS MES AA)",
                    periodo_aproximado=laxo.slug,
                )
            )
            continue
        upper = nombre.upper().replace("_", " ")
        if " VTAS " in f" {upper} " or any(mes in upper for mes in _MESES):
            avisos.append(
                AvisoCarpetaMes(
                    nombre_carpeta=nombre,
                    motivo="No se reconoce como carpeta de mes canónica",
                    periodo_aproximado=None,
                )
            )
    return avisos


def periodos_disponibles(repo_root: Path) -> list[Periodo]:
    vistos: set[tuple[int, int]] = set()
    periodos: list[Periodo] = []
    for asesor in listar_asesores(repo_root):
        for periodo, _ in carpetas_mes_asesor(asesor):
            key = (periodo.anio, periodo.mes)
            if key not in vistos:
                vistos.add(key)
                periodos.append(periodo)
    return sorted(periodos)


def validar_repo_periodo(repo_root: Path, periodo: Periodo) -> None:
    asesores = listar_asesores(repo_root)
    if not asesores:
        raise ValueError(f"No se encontraron carpetas de asesor en: {repo_root}")

    con_carpeta = 0
    for asesor in asesores:
        duplicados = carpetas_canonicas_para_periodo(asesor, periodo)
        if len(duplicados) > 1:
            nombres = ", ".join(p.name for p in duplicados)
            raise ValueError(
                f"{asesor.name}: carpetas duplicadas para {periodo.slug}: {nombres}"
            )
        if duplicados:
            con_carpeta += 1

    if con_carpeta == 0:
        raise ValueError(
            f"Ningún asesor tiene carpeta canónica para {periodo.etiqueta} ({periodo.slug}). "
            f"Formato esperado: NNN VTAS MES AA"
        )


def periodo_desde_flags(
    mes: int | None = None,
    anio: int | None = None,
    fecha_ref: date | datetime | None = None,
) -> Periodo:
    """Resuelve el período sin validar que el repo local tenga la carpeta."""
    if mes is None and anio is None:
        return periodo_calendario_actual(fecha_ref)
    if mes is None or anio is None:
        raise ValueError(
            "Debés indicar --mes y --anio juntos, o ninguno para usar el mes en curso."
        )
    if not (1 <= mes <= 12):
        raise ValueError(f"Mes inválido: {mes}")
    return Periodo(anio=_normalizar_anio(anio), mes=mes)


def resolver_periodo(
    repo_root: Path,
    mes: int | None = None,
    anio: int | None = None,
    fecha_ref: date | datetime | None = None,
) -> Periodo:
    periodo = periodo_desde_flags(mes=mes, anio=anio, fecha_ref=fecha_ref)
    validar_repo_periodo(repo_root, periodo)
    return periodo


def carpeta_mes_para_periodo(asesor_dir: Path, periodo: Periodo) -> Path | None:
    matches = carpetas_canonicas_para_periodo(asesor_dir, periodo)
    if not matches:
        return None
    if len(matches) > 1:
        nombres = ", ".join(p.name for p in matches)
        raise ValueError(
            f"{asesor_dir.name}: carpetas duplicadas para {periodo.slug}: {nombres}"
        )
    return matches[0]


def nombre_excel_emision(periodo: Periodo) -> str:
    return f"emision_{periodo.slug}.xlsx"


def nombre_reporte(periodo: Periodo) -> str:
    return f"reporte_{periodo.slug}.xlsx"
