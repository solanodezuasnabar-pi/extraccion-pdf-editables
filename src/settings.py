"""Carga de configuración y parametría de negocio."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import app_root, resolve_existing, workspace_root

PROJECT_ROOT = app_root()
WORKSPACE_ROOT = workspace_root()

DOCUMENTOS_DIR = WORKSPACE_ROOT / "documentos"
EJEMPLOS_DIR = DOCUMENTOS_DIR / "muestras"
EXCEL_ASESORES_DIR = DOCUMENTOS_DIR / "excel-asesores"
SOLICITUDES_DIR = DOCUMENTOS_DIR / "solicitudes"
REPO_EDITABLES_DIR = PROJECT_ROOT / "SOLICITUDES SALUD VAVI-RETIRO"
OUTPUT_DIR = PROJECT_ROOT / "output"


def template_xlsx() -> Path:
    bundled = resolve_existing("templates", "Modelo salud CE.xlsx")
    if bundled is not None:
        return bundled
    return DOCUMENTOS_DIR / "templates" / "Modelo salud CE.xlsx"


def parametria_path() -> Path:
    bundled = resolve_existing("config", "parametria.yaml")
    if bundled is not None:
        return bundled
    return PROJECT_ROOT / "config" / "parametria.yaml"


# Compat: rutas resueltas al import (también se re-resuelven al usar).
TEMPLATE_XLSX = template_xlsx()
PARAMETRIA_PATH = parametria_path()


@dataclass(frozen=True)
class ModuloFormConfig:
    campo: str | None = None
    campos_a: tuple[str, ...] = ()
    campos_b: tuple[str, ...] = ()
    por_export: dict[str, str] = field(default_factory=dict)  # export → A|B
    por_orden_y: tuple[str, ...] = ()
    usar_posicion_xy: bool = True


@dataclass(frozen=True)
class PlanFormConfig:
    campo: str = "TIPO PLAN"
    por_export: dict[str, str] = field(default_factory=dict)
    por_orden_y: tuple[str, ...] = ()


@dataclass(frozen=True)
class VarianteFormConfig:
    marcas_encabezado: tuple[str, ...] = ()
    plan_default: str | None = None
    plan: PlanFormConfig | None = None
    modulo: ModuloFormConfig = field(default_factory=ModuloFormConfig)


@dataclass(frozen=True)
class FormulariosConfig:
    modulo_excel: dict[str, int]
    variantes: dict[str, VarianteFormConfig]

    def valor_modulo(self, etiqueta: str | None) -> int | None:
        if etiqueta is None:
            return None
        key = str(etiqueta).strip().upper()
        if key in self.modulo_excel:
            return int(self.modulo_excel[key])
        # Permitir "1"/"2" directo si alguien configura números en por_export
        if key.isdigit():
            return int(key)
        return None


@dataclass(frozen=True)
class Parametria:
    pais_origen: int
    grupo_estadistico: int
    opcion_cobertura_por_plan: dict[str, int]
    tarjetas: dict[str, int]
    formularios: FormulariosConfig


def default_formularios() -> FormulariosConfig:
    """Equivalente al hardcode histórico de n1_formfields."""
    return FormulariosConfig( 
        modulo_excel={"A": 1, "B": 2},
        variantes={
            "plan4": VarianteFormConfig(
                marcas_encabezado=("PLAN FAMILIA", "PLAN 4"),
                plan_default="4",
                modulo=ModuloFormConfig(
                    campos_a=("APORTE", "DOCM"),
                    campos_b=("APORTE1", "DOCM1"),
                    usar_posicion_xy=True,
                ),
            ),
            "asesores": VarianteFormConfig(
                marcas_encabezado=("ASESORES",),
                plan=PlanFormConfig(
                    campo="TIPO PLAN",
                    por_export={"On": "5", "On1": "6", "On2": "100"},
                    por_orden_y=("5", "6", "100"),
                ),
                modulo=ModuloFormConfig(
                    campo="COBERTURA",
                    por_export={"On": "A", "On1": "B"},
                    por_orden_y=("A", "B"),
                ),
            ),
        },
    )


def _yaml_export_key(key: Any) -> str:
    """PyYAML 1.1 trata On/Off/Yes/No como bool; normalizar a string de export PDF."""
    if key is True:
        return "On"
    if key is False:
        return "Off"
    return str(key)


def _parse_modulo_form(data: dict[str, Any] | None) -> ModuloFormConfig:
    data = data or {}
    por_export = {_yaml_export_key(k): str(v) for k, v in (data.get("por_export") or {}).items()}
    por_orden = tuple(str(x) for x in (data.get("por_orden_y") or []))
    campos_a = tuple(str(x) for x in (data.get("campos_a") or []))
    campos_b = tuple(str(x) for x in (data.get("campos_b") or []))
    return ModuloFormConfig(
        campo=str(data["campo"]) if data.get("campo") else None,
        campos_a=campos_a,
        campos_b=campos_b,
        por_export=por_export,
        por_orden_y=por_orden,
        usar_posicion_xy=bool(data.get("usar_posicion_xy", True)),
    )


def _parse_plan_form(data: dict[str, Any] | None) -> PlanFormConfig | None:
    if not data:
        return None
    return PlanFormConfig(
        campo=str(data.get("campo") or "TIPO PLAN"),
        por_export={_yaml_export_key(k): str(v) for k, v in (data.get("por_export") or {}).items()},
        por_orden_y=tuple(str(x) for x in (data.get("por_orden_y") or [])),
    )


def _parse_formularios(data: dict[str, Any] | None, planes_ce: dict[str, int]) -> FormulariosConfig:
    if not data:
        return default_formularios()

    modulo_excel_raw = data.get("modulo_excel") or {"A": 1, "B": 2}
    modulo_excel = {str(k).strip().upper(): int(v) for k, v in modulo_excel_raw.items()}
    if "A" not in modulo_excel or "B" not in modulo_excel:
        raise ValueError("formularios.modulo_excel debe definir al menos A y B")

    variantes: dict[str, VarianteFormConfig] = {}
    for nombre, raw in (data.get("variantes") or {}).items():
        raw = raw or {}
        plan_cfg = _parse_plan_form(raw.get("plan"))
        if plan_cfg:
            for plan in plan_cfg.por_export.values():
                if str(plan) not in planes_ce:
                    raise ValueError(
                        f"formularios.variantes.{nombre}.plan.por_export → plan {plan!r} "
                        f"no está en opcion_cobertura_por_plan"
                    )
            for plan in plan_cfg.por_orden_y:
                if str(plan) not in planes_ce:
                    raise ValueError(
                        f"formularios.variantes.{nombre}.plan.por_orden_y → plan {plan!r} "
                        f"no está en opcion_cobertura_por_plan"
                    )

        mod_cfg = _parse_modulo_form(raw.get("modulo"))
        for etiqueta in list(mod_cfg.por_export.values()) + list(mod_cfg.por_orden_y):
            key = str(etiqueta).strip().upper()
            if key not in modulo_excel and not key.isdigit():
                raise ValueError(
                    f"formularios.variantes.{nombre}.modulo referencia etiqueta {etiqueta!r} "
                    f"ausente en modulo_excel"
                )

        variantes[str(nombre)] = VarianteFormConfig(
            marcas_encabezado=tuple(str(x) for x in (raw.get("marcas_encabezado") or [])),
            plan_default=str(raw["plan_default"]) if raw.get("plan_default") is not None else None,
            plan=plan_cfg,
            modulo=mod_cfg,
        )

    # Completar variantes faltantes con defaults (compat)
    defaults = default_formularios()
    for key, var in defaults.variantes.items():
        variantes.setdefault(key, var)

    return FormulariosConfig(modulo_excel=modulo_excel, variantes=variantes)


def cargar_parametria(path: Path | None = None) -> Parametria:
    path = path or parametria_path()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    opcion = {str(k): int(v) for k, v in data["opcion_cobertura_por_plan"].items()}
    return Parametria(
        pais_origen=int(data["pais_origen"]),
        grupo_estadistico=int(data["grupo_estadistico"]),
        opcion_cobertura_por_plan=opcion,
        tarjetas={str(k).upper(): int(v) for k, v in data["tarjetas"].items()},
        formularios=_parse_formularios(data.get("formularios"), opcion),
    )
