"""Descarga de SharePoint los PDFs editables que el bot toma para un mes.

Usa Graph (misma biblioteca que el RPA) y el mismo selector que `process_manager`:
solo `solicitud_editable` (Plan Familia). Incluye incompletos; excluye escaneos,
adjuntos (DNI/CBU) y otros formularios.

Uso (desde la raíz del repo):
  .\\.venv\\Scripts\\python.exe scripts\\descargar_editables.py
  .\\.venv\\Scripts\\python.exe scripts\\descargar_editables.py --mes 2 --anio 2026
  .\\.venv\\Scripts\\python.exe scripts\\descargar_editables.py --dest D:\\vavi\\feb
  .\\.venv\\Scripts\\python.exe scripts\\descargar_editables.py --solo-faltantes

Junto a los PDFs escribe faltantes.txt (qué campo falta en cada archivo).
"""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.completitud import evaluar_completitud  # noqa: E402
from src.graph_auth import acquire_token  # noqa: E402
from src.graph_config import GraphConfig, cargar_graph_config  # noqa: E402
from src.graph_conector import listar_pdfs_periodo, materializar_lote  # noqa: E402
from src.graph_http import GraphError, GraphHttp  # noqa: E402
from src.labels import etiquetas_campos  # noqa: E402
from src.libs import config_manager  # noqa: E402
from src.normalizer import extraer_pdf  # noqa: E402
from src.periodo import Periodo, periodo_desde_flags  # noqa: E402
from src.selector import seleccionar_pdf  # noqa: E402
from src.settings import Parametria, cargar_parametria  # noqa: E402

_PS_TOKEN = Path(__file__).resolve().parent / "graph_token_windows.ps1"


def _sep(titulo: str) -> None:
    print(f"\n{'=' * 8} {titulo} {'=' * 8}")


def _token_store(cfg: GraphConfig) -> str:
    if not _PS_TOKEN.is_file():
        raise GraphError(f"No está {_PS_TOKEN}")
    if not cfg.thumbprint:
        raise GraphError("GRAPH_THUMBPRINT vacío (hace falta para el store de Windows)")
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(_PS_TOKEN),
        "-TenantId",
        cfg.tenant_id,
        "-ClientId",
        cfg.client_id,
        "-Thumbprint",
        cfg.thumbprint,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    token = (proc.stdout or "").strip()
    if proc.returncode != 0 or not token:
        err = (proc.stderr or proc.stdout or "sin detalle").strip()
        raise GraphError(f"No se obtuvo token del store de Windows: {err}")
    return token


def _http(cfg: GraphConfig, cert: str | None) -> GraphHttp:
    pem = (cert or cfg.cert_path or "").strip()
    if pem:
        return GraphHttp(acquire_token(replace(cfg, cert_path=pem)))
    print("GRAPH_CERT_PATH vacío — token con certificado del store de Windows.")
    return GraphHttp(_token_store(cfg))


def _faltantes_de_pdf(pdf: Path, parametria: Parametria) -> tuple[str, str, list[str]]:
    """Devuelve (tomador, estado, etiquetas de faltantes)."""
    try:
        solicitud = extraer_pdf(pdf)
    except Exception as exc:  # noqa: BLE001
        return "(no se pudo leer)", f"ERROR de extracción: {exc}", []
    if solicitud is None:
        return "(no se pudo leer)", "ERROR de extracción (E1): PDF editable sin datos leíbles", []
    tomador = (solicitud.apellido_nombre_tomador or "").strip() or "(sin tomador)"
    resultado = evaluar_completitud(solicitud, parametria)
    if resultado.completa:
        return tomador, "COMPLETA", []
    return tomador, "INCOMPLETA", etiquetas_campos(resultado.faltantes)


def _escribir_faltantes(
    dest: Path,
    periodo: Periodo,
    filas: list[tuple[str, str, str, Path]],
    parametria: Parametria,
) -> Path:
    """filas: asesor, carpeta, archivo, path local."""
    out = dest / "faltantes.txt"
    lineas = [
        f"Faltantes de completitud — {periodo.etiqueta}",
        "Solo PDFs editables descargados (los que el bot extrae).",
        "Campos: DNI tomador/asegurados, dirección, CP, plan, módulo, vigencias,",
        "N° productor, N° organizador. El pago no incompleta: si falta o está mal se emite efectivo.",
        "",
    ]
    ok = 0
    inc = 0
    err = 0
    for i, (asesor, carpeta, archivo, path) in enumerate(filas, start=1):
        tomador, estado, faltan = _faltantes_de_pdf(path, parametria)
        lineas.append(f"{i}. {archivo}")
        lineas.append(f"   Asesor:  {asesor}")
        lineas.append(f"   Carpeta: {carpeta}")
        lineas.append(f"   Tomador: {tomador}")
        lineas.append(f"   Estado:  {estado}")
        if estado == "COMPLETA":
            ok += 1
            lineas.append("   Faltan:  (nada)")
        elif faltan:
            inc += 1
            lineas.append("   Faltan:")
            for campo in faltan:
                lineas.append(f"     - {campo}")
        else:
            err += 1
        lineas.append("")
    lineas.append("---")
    lineas.append(f"Total: {len(filas)}  |  completas: {ok}  |  incompletas: {inc}  |  error: {err}")
    out.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--env", default="tst", choices=["dev", "tst", "pro"])
    ap.add_argument("--mes", type=int, default=2, help="Mes 1-12 (default: 2 = febrero)")
    ap.add_argument("--anio", type=int, default=2026, help="Año (default: 2026)")
    ap.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Carpeta local de destino (default: output/editables_MM_YYYY)",
    )
    ap.add_argument("--cert", type=Path, default=None, help="PEM del certificado Graph")
    ap.add_argument(
        "--listar",
        action="store_true",
        help="Solo lista los PDF remotos del mes; no descarga ni filtra",
    )
    ap.add_argument(
        "--solo-faltantes",
        action="store_true",
        help="No descarga: arma faltantes.txt sobre PDFs ya bajados en --dest",
    )
    args = ap.parse_args()

    config_manager.read_config(args.env)
    cfg = cargar_graph_config()
    faltan = [
        k
        for k, v in (
            ("GRAPH_TENANT_ID", cfg.tenant_id),
            ("GRAPH_CLIENT_ID", cfg.client_id),
            ("GRAPH_SITE_ID", cfg.site_id),
            ("GRAPH_LIST_ID", cfg.list_id),
        )
        if not v
    ]
    if faltan:
        print("ERROR: faltan en configs: " + ", ".join(faltan), file=sys.stderr)
        return 2

    periodo: Periodo = periodo_desde_flags(mes=args.mes, anio=args.anio)
    dest = Path(args.dest) if args.dest else ROOT / "output" / f"editables_{periodo.slug}"
    dest = dest.resolve()

    _sep(f"{periodo.etiqueta}  ({cfg.vavi_root})")
    print(f"Sitio    {cfg.site_id.split(',')[0]}")
    print(f"Destino  {dest}")

    parametria = cargar_parametria()
    if args.solo_faltantes:
        pdfs = sorted(p for p in dest.rglob("*.pdf") if p.is_file())
        if not pdfs:
            print(f"ERROR: no hay PDFs en {dest}. Corré primero sin --solo-faltantes.", file=sys.stderr)
            return 1
        filas: list[tuple[str, str, str, Path]] = []
        for pdf in pdfs:
            rel = pdf.relative_to(dest)
            partes = rel.parts
            asesor = partes[0] if partes else ""
            carpeta = partes[-2] if len(partes) >= 2 else ""
            filas.append((asesor, carpeta, pdf.name, pdf))
        txt = _escribir_faltantes(dest, periodo, filas, parametria)
        print(f"PDFs      {len(filas)}")
        print(f"Faltantes {txt}")
        return 0

    try:
        http = _http(cfg, str(args.cert) if args.cert else None)
    except GraphError as exc:
        print(f"ERROR auth Graph: {exc}", file=sys.stderr)
        print(
            "Probá --cert ruta\\al\\vavi.pem  (exportá el cert del store; ver RUNBOOK-ENTRA-APP-REGISTRATION.md).",
            file=sys.stderr,
        )
        return 1

    _sep("Listado remoto")
    items = listar_pdfs_periodo(http, cfg, periodo)
    print(f"{len(items)} PDF(s) en carpetas canónicas NNN VTAS MES AA")
    if not items:
        print("No hay PDFs de ese mes en SharePoint (o ninguna carpeta con el formato acordado).")
        return 1
    por_asesor: dict[str, int] = {}
    for it in items:
        por_asesor[it.asesor] = por_asesor.get(it.asesor, 0) + 1
    for nombre, n in sorted(por_asesor.items()):
        print(f"  {n:4d}  {nombre}")
    if args.listar:
        return 0

    staging = Path(tempfile.mkdtemp(prefix=f"vavi_editables_{periodo.slug}_"))
    copiados = 0
    omitidos = 0
    descargados: list[tuple[str, str, str, Path]] = []
    try:
        _sep("Descarga")
        print(f"Staging  {staging}")
        materializar_lote(http, cfg, items, staging)

        _sep("Filtro del bot (solo solicitud_editable)")
        dest.mkdir(parents=True, exist_ok=True)
        manifesto = dest / "seleccion.csv"
        with manifesto.open("w", encoding="utf-8", newline="") as fh:
            wr = csv.writer(fh, delimiter=";")
            wr.writerow(["asesor", "carpeta", "archivo", "decision", "categoria", "motivo", "destino"])
            for it in items:
                local = staging / it.asesor / "SOLICITUDES ESCANEADAS" / it.carpeta_mes / it.nombre
                if not local.is_file():
                    wr.writerow([it.asesor, it.carpeta_mes, it.nombre, "error", "", "no se descargó", ""])
                    omitidos += 1
                    continue
                sel = seleccionar_pdf(local)
                tomar = sel.categoria == "solicitud_editable"
                destino_rel = ""
                if tomar:
                    destino = dest / it.asesor / "SOLICITUDES ESCANEADAS" / it.carpeta_mes / it.nombre
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(local, destino)
                    destino_rel = str(destino)
                    descargados.append((it.asesor, it.carpeta_mes, it.nombre, destino))
                    copiados += 1
                    print(f"  + {it.asesor} / {it.nombre}")
                else:
                    omitidos += 1
                    print(f"  - [{sel.categoria}] {it.asesor} / {it.nombre} — {sel.motivo}")
                wr.writerow(
                    [
                        it.asesor,
                        it.carpeta_mes,
                        it.nombre,
                        sel.decision,
                        sel.categoria,
                        sel.motivo,
                        destino_rel,
                    ]
                )
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    txt = None
    if descargados:
        txt = _escribir_faltantes(dest, periodo, descargados, parametria)

    _sep("Resultado")
    print(f"Remotos     {len(items)}")
    print(f"Editables   {copiados}  (los que el bot extrae, completos o incompletos)")
    print(f"Omitidos    {omitidos}  (escaneo / adjunto / otro formulario)")
    print(f"Carpeta     {dest}")
    print(f"Detalle     {dest / 'seleccion.csv'}")
    if txt:
        print(f"Faltantes   {txt}")
    return 0 if copiados else 1


if __name__ == "__main__":
    sys.exit(main())
