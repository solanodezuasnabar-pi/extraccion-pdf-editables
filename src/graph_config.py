"""Configuración del conector Microsoft Graph (Etapa 3)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "si", "sí"}


def _publicar_todo_en_salida(raw: str | None) -> bool:
    """Default True: emisión y reporte van a GRAPH_SALIDA. Solo False explícito restaura el split."""
    if raw is None or not str(raw).strip():
        return True
    return _flag(raw)


@dataclass(frozen=True)
class GraphConfig:
    tenant_id: str
    client_id: str
    thumbprint: str = ""
    cert_path: str = ""
    site_id: str = ""
    list_id: str = ""
    vavi_root: str = "SOLICITUDES SALUD VAVI-RETIRO"
    salida: str = "_salida"
    publicar_todo_en_salida: bool = True

    @property
    def completo(self) -> bool:
        return bool(
            self.tenant_id
            and self.client_id
            and self.site_id
            and self.list_id
            and (self.cert_path or self.thumbprint)
        )


def graph_enabled(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return _flag(env.get("GRAPH_ENABLED"))


def cargar_graph_config(environ: dict[str, str] | None = None) -> GraphConfig:
    env = environ if environ is not None else os.environ
    return GraphConfig(
        tenant_id=(env.get("GRAPH_TENANT_ID") or "").strip(),
        client_id=(env.get("GRAPH_CLIENT_ID") or "").strip(),
        thumbprint=(env.get("GRAPH_THUMBPRINT") or "").strip(),
        cert_path=(env.get("GRAPH_CERT_PATH") or "").strip(),
        site_id=(env.get("GRAPH_SITE_ID") or "").strip(),
        list_id=(env.get("GRAPH_LIST_ID") or "").strip(),
        vavi_root=(env.get("GRAPH_VAVI_ROOT") or "SOLICITUDES SALUD VAVI-RETIRO").strip(),
        salida=(env.get("GRAPH_SALIDA") or "_salida").strip().lstrip("/"),
        publicar_todo_en_salida=_publicar_todo_en_salida(env.get("GRAPH_PUBLICAR_TODO_EN_SALIDA")),
    )
