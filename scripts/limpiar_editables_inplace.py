#!/usr/bin/env python3
"""Deja en EDITABLES solo PDFs con campos de formulario útiles (N1).

Los no editables se mueven a _DESCARTADOS_NO_EDITABLES/ (misma estructura).
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

import fitz

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "SOLICITUDES SALUD VAVI-RETIRO"
QUARANTINE = "_DESCARTADOS_NO_EDITABLES"
CARPETA_SOLICITUDES = "SOLICITUDES ESCANEADAS"
_NO_VALORES = {"Off", "On", "On1", "On2", "On5", ""}


def _widget_relleno(valor) -> bool:
    texto = str(valor).strip() if valor is not None else ""
    return bool(texto) and texto not in _NO_VALORES


def _contar_widgets(pdf_path: Path) -> tuple[int, int]:
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


def _iter_pdfs(root: Path) -> list[Path]:
    pdfs: list[Path] = []
    for asesor in sorted(p for p in root.iterdir() if p.is_dir() and p.name != QUARANTINE):
        escaneadas = asesor / CARPETA_SOLICITUDES
        if not escaneadas.is_dir():
            # también PDFs sueltos bajo el asesor
            pdfs.extend(sorted(asesor.rglob("*.pdf")))
            continue
        pdfs.extend(sorted(escaneadas.rglob("*.pdf")))
    return pdfs


def main() -> int:
    parser = argparse.ArgumentParser(description="Limpia EDITABLES dejando solo PDFs editables.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--min-rellenos", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Borra en vez de mover a cuarentena (irreversible).",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"ERROR: no existe {root}", file=sys.stderr)
        return 1

    pdfs = _iter_pdfs(root)
    print(f"Root: {root}")
    print(f"PDFs: {len(pdfs)}")
    print(f"Min rellenos: {args.min_rellenos}")
    print(f"Dry-run: {args.dry_run}")
    print(f"Modo: {'borrar' if args.delete else 'mover a ' + QUARANTINE}")
    print()

    keep = 0
    drop = 0
    errors = 0
    rows: list[list[str]] = []

    for i, pdf in enumerate(pdfs, start=1):
        if i == 1 or i % 25 == 0 or i == len(pdfs):
            print(f"[{i}/{len(pdfs)}] …", flush=True)
        rel = pdf.relative_to(root)
        try:
            total, rellenos = _contar_widgets(pdf)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            rows.append(["error", "0", "0", str(rel), str(exc)])
            continue

        if total > 0 and rellenos >= args.min_rellenos:
            keep += 1
            rows.append(["keep", str(total), str(rellenos), str(rel), "editable"])
            continue

        drop += 1
        detalle = "sin_widgets" if total == 0 else f"pocos_rellenos ({rellenos}<{args.min_rellenos})"
        if args.dry_run:
            rows.append(["would_drop", str(total), str(rellenos), str(rel), detalle])
            continue

        if args.delete:
            pdf.unlink(missing_ok=True)
            rows.append(["deleted", str(total), str(rellenos), str(rel), detalle])
        else:
            dest = root / QUARANTINE / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest.unlink()
            shutil.move(str(pdf), str(dest))
            rows.append(["moved", str(total), str(rellenos), str(rel), detalle])

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = root / f"_reporte_limpieza_editables_{stamp}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["accion", "widgets_total", "widgets_rellenos", "ruta", "detalle"])
        w.writerows(rows)

    print()
    print(f"Keep:   {keep}")
    print(f"Drop:   {drop}")
    print(f"Error:  {errors}")
    print(f"CSV:    {csv_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
