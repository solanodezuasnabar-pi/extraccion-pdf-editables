#!/usr/bin/env python3
"""
Filtra PDFs editables desde el mirror SharePoint y replica la estructura.

Origen típico:
  SOLICITUDES SALUD VAVI-RETIRO/
    <ASESOR>/
      SOLICITUDES ESCANEADAS/
        <NN VTAS MES AÑO>/
          *.pdf

Destino:
  SOLICITUDES SALUD VAVI-RETIRO_EDITABLES/
    (misma estructura, solo PDFs con campos de formulario útiles para N1)

Uso (desde la raíz del repo):
  .\\.venv\\Scripts\\python.exe scripts\\filtrar_editables_sharepoint.py

  # Dry-run (no copia):
  ... filtrar_editables_sharepoint.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import fitz

WORKSPACE = Path(__file__).resolve().parent.parent.parent
_V2_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = WORKSPACE / "SOLICITUDES SALUD VAVI-RETIRO"
DEFAULT_DST = WORKSPACE / "SOLICITUDES SALUD VAVI-RETIRO_EDITABLES"
CARPETA_SOLICITUDES = "SOLICITUDES ESCANEADAS"

_NO_VALORES = {"Off", "On", "On1", "On2", "On5", ""}


@dataclass
class Resultado:
    origen: Path
    destino: Path | None
    tipo: str
    widgets_total: int
    widgets_rellenos: int
    accion: str  # copiado | omitido | error | dry-run
    detalle: str = ""


def _widget_relleno(valor) -> bool:
    texto = str(valor).strip() if valor is not None else ""
    return bool(texto) and texto not in _NO_VALORES


def _contar_widgets(pdf_path: Path) -> tuple[int, int]:
    """Conteo rápido de campos (sin clasificar escaneos por imagen)."""
    doc = fitz.open(pdf_path)
    total = 0
    rellenos = 0
    try:
        for page in doc:
            for widget in page.widgets() or []:
                total += 1
                if _widget_relleno(widget.field_value):
                    rellenos += 1
    finally:
        doc.close()
    return total, rellenos


def _tipo_desde_widgets(widgets_total: int, widgets_rellenos: int) -> str:
    if widgets_total > 0 and widgets_rellenos >= 3:
        return "formulario_editable"
    if widgets_total > 0 and widgets_rellenos > 0:
        return "formulario_parcial"
    if widgets_total > 0:
        return "formulario_vacio"
    return "sin_widgets"


def _iter_pdfs_en_solicitudes(src_root: Path) -> list[Path]:
    """PDF bajo <asesor>/SOLICITUDES ESCANEADAS/**."""
    pdfs: list[Path] = []
    if not src_root.is_dir():
        return pdfs
    for asesor in sorted(p for p in src_root.iterdir() if p.is_dir()):
        escaneadas = asesor / CARPETA_SOLICITUDES
        if not escaneadas.is_dir():
            continue
        pdfs.extend(sorted(escaneadas.rglob("*.pdf")))
    return pdfs


def procesar(
    src_root: Path,
    dst_root: Path,
    *,
    dry_run: bool,
    min_rellenos: int,
) -> list[Resultado]:
    resultados: list[Resultado] = []
    pdfs = _iter_pdfs_en_solicitudes(src_root)
    total = len(pdfs)

    for i, pdf in enumerate(pdfs, start=1):
        rel = pdf.relative_to(src_root)
        dest = dst_root / rel
        if i == 1 or i % 25 == 0 or i == total:
            print(f"[{i}/{total}] …", flush=True)

        try:
            widgets_total, widgets_rellenos = _contar_widgets(pdf)
            tipo = _tipo_desde_widgets(widgets_total, widgets_rellenos)
        except Exception as exc:  # noqa: BLE001 — lote: un PDF no debe abortar todo
            resultados.append(
                Resultado(
                    origen=pdf,
                    destino=None,
                    tipo="error",
                    widgets_total=0,
                    widgets_rellenos=0,
                    accion="error",
                    detalle=str(exc),
                )
            )
            continue

        if widgets_total == 0 or widgets_rellenos < min_rellenos:
            resultados.append(
                Resultado(
                    origen=pdf,
                    destino=None,
                    tipo=tipo,
                    widgets_total=widgets_total,
                    widgets_rellenos=widgets_rellenos,
                    accion="omitido",
                    detalle=(
                        "Sin campos de formulario"
                        if widgets_total == 0
                        else f"Pocos campos rellenos ({widgets_rellenos} < {min_rellenos})"
                    ),
                )
            )
            continue

        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf, dest)

        resultados.append(
            Resultado(
                origen=pdf,
                destino=dest,
                tipo=tipo,
                widgets_total=widgets_total,
                widgets_rellenos=widgets_rellenos,
                accion="copiado" if not dry_run else "dry-run",
                detalle=f"Editable con {widgets_rellenos}/{widgets_total} campos rellenos",
            )
        )

    return resultados


def _escribir_reporte(dst_root: Path, resultados: list[Resultado], dry_run: bool) -> Path:
    dst_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = dst_root / f"_reporte_filtro_editables_{stamp}.csv"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(
            [
                "accion",
                "tipo",
                "widgets_total",
                "widgets_rellenos",
                "ruta_relativa",
                "detalle",
            ]
        )
        for r in resultados:
            try:
                rel = str(r.origen.relative_to(WORKSPACE))
            except ValueError:
                rel = str(r.origen)
            writer.writerow(
                [r.accion, r.tipo, r.widgets_total, r.widgets_rellenos, rel, r.detalle]
            )

    resumen_path = dst_root / f"_resumen_filtro_editables_{stamp}.txt"
    copiados = sum(1 for r in resultados if r.accion in {"copiado", "dry-run"})
    omitidos = sum(1 for r in resultados if r.accion == "omitido")
    errores = sum(1 for r in resultados if r.accion == "error")
    por_tipo: dict[str, int] = {}
    for r in resultados:
        por_tipo[r.tipo] = por_tipo.get(r.tipo, 0) + 1

    lineas = [
        f"Fecha: {datetime.now().isoformat(timespec='seconds')}",
        f"Dry-run: {dry_run}",
        f"Total PDFs evaluados: {len(resultados)}",
        f"Editables {'a copiar' if dry_run else 'copiados'}: {copiados}",
        f"Omitidos: {omitidos}",
        f"Errores: {errores}",
        "",
        "Por tipo de clasificación:",
        *[f"  {k}: {v}" for k, v in sorted(por_tipo.items(), key=lambda x: (-x[1], x[0]))],
        "",
        f"CSV: {csv_path.name}",
    ]
    resumen_path.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas), flush=True)
    return resumen_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replica la estructura SharePoint dejando solo PDFs editables (N1)."
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=DEFAULT_SRC,
        help=f"Carpeta origen (default: {DEFAULT_SRC.name})",
    )
    parser.add_argument(
        "--dst",
        type=Path,
        default=DEFAULT_DST,
        help=f"Carpeta destino (default: {DEFAULT_DST.name})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Clasifica y reporta sin copiar archivos",
    )
    parser.add_argument(
        "--min-rellenos",
        type=int,
        default=3,
        help=(
            "Mínimo de campos de formulario con valor (default: 3, igual que "
            "formulario_editable del clasificador). Usá 1 para incluir parciales."
        ),
    )
    args = parser.parse_args()

    src = args.src.resolve()
    dst = args.dst.resolve()
    if not src.is_dir():
        print(f"ERROR: no existe origen: {src}", file=sys.stderr)
        return 1

    print(f"Origen:       {src}")
    print(f"Destino:      {dst}")
    print(f"Min rellenos: {args.min_rellenos}")
    print(f"Dry-run:      {args.dry_run}")
    print()

    resultados = procesar(
        src, dst, dry_run=args.dry_run, min_rellenos=args.min_rellenos
    )
    _escribir_reporte(dst, resultados, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
