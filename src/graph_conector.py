"""Capa Graph: snapshot remoto → staging local → publicar _salida/."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from typing import Any

from .graph_config import GraphConfig
from .graph_http import GRAPH_ROOT, GraphError, GraphHttp
from .libs import log_manager
from .periodo import CARPETA_SOLICITUDES, Periodo, parse_periodo_carpeta


@dataclass(frozen=True)
class ItemRemoto:
    asesor: str
    carpeta_mes: str
    nombre: str
    item_id: str
    subcarpeta: str = ""


def _enc_path(path: str) -> str:
    return "/".join(quote(part, safe=" ") for part in path.split("/") if part)


def _drive_id(http: Any, cfg: GraphConfig) -> str:
    data = http.request_json(
        "GET",
        f"{GRAPH_ROOT}/sites/{cfg.site_id}/lists/{cfg.list_id}/drive",
    )
    drive = data.get("id")
    if not drive:
        raise GraphError("Graph no devolvió drive id")
    return drive


def _children(http: Any, drive_id: str, path: str) -> list[dict]:
    url = f"{GRAPH_ROOT}/drives/{drive_id}/root:/{_enc_path(path)}:/children"
    out: list[dict] = []
    while url:
        data = http.request_json("GET", url)
        out.extend(data.get("value") or [])
        url = data.get("@odata.nextLink") or ""
    return out


def listar_pdfs_periodo(http: Any, cfg: GraphConfig, periodo: Periodo) -> list[ItemRemoto]:
    drive = _drive_id(http, cfg)
    items: list[ItemRemoto] = []
    for asesor in _children(http, drive, cfg.vavi_root):
        if "folder" not in asesor:
            continue
        nombre = (asesor.get("name") or "").strip()
        if not nombre or nombre.startswith("_"):
            continue
        try:
            meses = _children(http, drive, f"{cfg.vavi_root}/{nombre}/{CARPETA_SOLICITUDES}")
        except GraphError as exc:
            if exc.status_code == 404:
                continue
            raise
        for mes in meses:
            if "folder" not in mes:
                continue
            carpeta = (mes.get("name") or "").strip()
            if parse_periodo_carpeta(carpeta) != periodo:
                continue
            mes_path = f"{cfg.vavi_root}/{nombre}/{CARPETA_SOLICITUDES}/{carpeta}"
            try:
                archivos = _children(http, drive, mes_path)
            except GraphError as exc:
                if exc.status_code == 404:
                    continue
                raise
            for archivo in archivos:
                fname = (archivo.get("name") or "").strip()
                if not fname:
                    continue
                if "folder" in archivo:
                    try:
                        hijos = _children(http, drive, f"{mes_path}/{fname}")
                    except GraphError as exc:
                        if exc.status_code == 404:
                            continue
                        raise
                    for hijo in hijos:
                        hname = (hijo.get("name") or "").strip()
                        if "file" not in hijo or not hname.lower().endswith(".pdf"):
                            continue
                        items.append(
                            ItemRemoto(
                                asesor=nombre,
                                carpeta_mes=carpeta,
                                nombre=hname,
                                item_id=str(hijo.get("id") or ""),
                                subcarpeta=fname,
                            )
                        )
                    continue
                if "file" not in archivo or not fname.lower().endswith(".pdf"):
                    continue
                items.append(
                    ItemRemoto(
                        asesor=nombre,
                        carpeta_mes=carpeta,
                        nombre=fname,
                        item_id=str(archivo.get("id") or ""),
                    )
                )
    sueltos = sum(1 for i in items if not i.subcarpeta)
    anidados = len(items) - sueltos
    log_manager.info(
        "Graph: %s PDF del mes (%s sueltos, %s en carpeta de persona)",
        len(items),
        sueltos,
        anidados,
    )
    return items


def materializar_lote(http: Any, cfg: GraphConfig, items: list[ItemRemoto], dest: Path) -> Path:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    drive = _drive_id(http, cfg)
    for item in items:
        carpeta = dest / item.asesor / CARPETA_SOLICITUDES / item.carpeta_mes
        if item.subcarpeta:
            carpeta = carpeta / item.subcarpeta
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / item.nombre
        contenido = http.request_bytes(
            "GET",
            f"{GRAPH_ROOT}/drives/{drive}/items/{item.item_id}/content",
        )
        destino.write_bytes(contenido)
    return dest


def _ruta_publicacion(cfg: GraphConfig, nombre: str) -> str:
    """Emisión y reporte en GRAPH_SALIDA (default `_salida`), bajo la raíz VAVI.

    GRAPH_PUBLICAR_TODO_EN_SALIDA=false restaura el split viejo (emisión en la raíz VAVI).
    """
    dest = (cfg.salida or "").strip("/")
    emision_en_raiz = (
        nombre.lower().startswith("emision_")
        and not cfg.publicar_todo_en_salida
    )
    if emision_en_raiz:
        return f"{cfg.vavi_root}/{nombre}"
    if dest:
        return f"{cfg.vavi_root}/{dest}/{nombre}"
    return f"{cfg.vavi_root}/{nombre}"


def publicar_salida(http: Any, cfg: GraphConfig, archivos: list[Path]) -> list[str]:
    drive = _drive_id(http, cfg)
    publicados: list[str] = []
    for archivo in archivos:
        path = Path(archivo)
        if not path.is_file():
            continue
        remoto = _ruta_publicacion(cfg, path.name)
        url = f"{GRAPH_ROOT}/drives/{drive}/root:/{_enc_path(remoto)}:/content"
        try:
            http.put_bytes(
                url,
                path.read_bytes(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except GraphError as exc:
            if exc.status_code == 423:
                log_manager.warning(
                    "SharePoint bloqueó %s (HTTP 423). Cerrá el archivo en Excel/el navegador y reintentá. El lote local sí se generó.",
                    remoto,
                )
                continue
            raise
        publicados.append(remoto)
    return publicados


def preparar_repo_desde_graph(
    http: Any,
    cfg: GraphConfig,
    periodo: Periodo,
    staging_parent: Path | None = None,
) -> Path:
    """Lista, baja y deja un repo local. Si falla, borra el staging."""
    parent = Path(staging_parent) if staging_parent else Path(tempfile.gettempdir())
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="vavi_graph_", dir=str(parent)))
    try:
        items = listar_pdfs_periodo(http, cfg, periodo)
        materializar_lote(http, cfg, items, staging)
        return staging
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def limpiar_staging(path: Path | None) -> None:
    if path is None:
        return
    shutil.rmtree(path, ignore_errors=True)


def process_via_graph(
    periodo: Periodo,
    *,
    output_dir: Path,
    http: Any | None = None,
    cfg: GraphConfig | None = None,
    process_repo_fn=None,
) -> int:
    """Baja el mes, corre process_repo y publica los dos Excel."""
    from .graph_auth import acquire_token
    from .graph_config import cargar_graph_config
    from .periodo import nombre_excel_emision, nombre_reporte
    from .process_manager import process_repo

    cfg = cfg or cargar_graph_config()
    if not cfg.completo:
        raise GraphError("GRAPH_ENABLED pero faltan GRAPH_TENANT_ID / CLIENT_ID / CERT_PATH / SITE_ID / LIST_ID")
    if http is None:
        http = GraphHttp(acquire_token(cfg))
    runner = process_repo_fn or process_repo
    staging = None
    try:
        staging = preparar_repo_desde_graph(http, cfg, periodo)
        rc = runner(staging, periodo, output_dir=output_dir)
        candidatos = [
            Path(output_dir) / nombre_excel_emision(periodo),
            Path(output_dir) / nombre_reporte(periodo),
        ]
        publicar_salida(http, cfg, candidatos)
        return rc
    finally:
        limpiar_staging(staging)
