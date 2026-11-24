#!/usr/bin/env python3
"""
Emisión Plan Familia VAVI — script RPA local.

Arquitectura alineada a template-rpa-main (sin Selenium; notificaciones SMTP).

Uso:
    # Mes en curso por calendario (INPUTS o Graph)
    python main.py --env dev

    # Mes / año explícitos
    python main.py --env dev --mes 5 --anio 2026

    # Carpeta puntual (legacy)
    python main.py --env dev --input "..\\documentos\\solicitudes\\09 VTAS SEPTIEMBRE 25"
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _venv_python() -> Path | None:
    if sys.platform == "win32":
        candidate = _ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = _ROOT / ".venv" / "bin" / "python"
    return candidate if candidate.is_file() else None


def _ensure_venv() -> None:
    if getattr(sys, "frozen", False):
        return
    venv_py = _venv_python()
    if not venv_py:
        return
    if Path(sys.executable).resolve() == venv_py.resolve():
        return
    os.execv(str(venv_py), [str(venv_py), *sys.argv])


def _ensure_dependencies() -> None:
    if getattr(sys, "frozen", False):
        return
    requeridos = [
        ("yaml", "PyYAML"),
        ("fitz", "pymupdf"),
        ("openpyxl", "openpyxl"),
        ("dateutil", "python-dateutil"),
        ("dotenv", "python-dotenv"),
        ("jinja2", "jinja2"),
    ]
    faltantes = []
    for mod, pkg in requeridos:
        try:
            __import__(mod)
        except ImportError:
            faltantes.append(pkg)
    if not faltantes:
        return
    print("Faltan dependencias:", ", ".join(faltantes), file=sys.stderr)
    print("Instalá con: .venv\\Scripts\\pip install -r requirements.txt", file=sys.stderr)
    raise SystemExit(1)


_ensure_venv()
_ensure_dependencies()

import argparse

from src.libs import config_manager, log_manager, notification_manager
from src.process_manager import process


def main() -> int:
    if getattr(sys, "frozen", False):
        working_dir = Path(sys.executable).resolve().parent
    else:
        working_dir = _ROOT
    os.chdir(working_dir)

    parser = argparse.ArgumentParser(description="Emisión Plan Familia VAVI (RPA local)")
    parser.add_argument("--env", default="dev", help="Entorno de configuración (dev, tst, pro)")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Carpeta puntual de PDFs (si se omite, usa el repo de solicitudes)",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Raíz multi-asesor (default: SOLICITUDES SALUD VAVI-RETIRO)",
    )
    parser.add_argument("--mes", type=int, default=None, help="Mes 1-12 (requiere --anio)")
    parser.add_argument(
        "--anio",
        type=int,
        default=None,
        help="Año (2025 o 25). Sin --mes/--anio: mes en curso por calendario",
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="Salida (solo modo --input)")
    parser.add_argument("--recursive", action="store_true", help="Buscar PDFs en subcarpetas (modo --input)")
    parser.add_argument(
        "--excel-asesor",
        type=Path,
        default=None,
        help="Excel VENTAS SALUD ASESORES para cruce opcional en el reporte",
    )
    parser.add_argument(
        "--sin-filtro",
        action="store_true",
        help="Procesar todos los PDF sin selector (no recomendado)",
    )
    args = parser.parse_args()

    if (args.mes is None) ^ (args.anio is None):
        print("ERROR: usá --mes y --anio juntos, o ninguno.", file=sys.stderr)
        return 2

    try:
        config_manager.read_config(args.env)
        logger = log_manager.get_logger()
    except Exception:
        print("Error al cargar la configuración", file=sys.stderr)
        traceback.print_exc()
        return 1

    error_code = 0
    try:
        log_manager.info_file("Inicio %s", config_manager.config.get("PROCESS_NAME"))
        notification_manager.send_process_start()
        rc = process(
            input_dir=args.input,
            output_dir=args.output_dir,
            recursive=args.recursive,
            excel_asesor=args.excel_asesor,
            sin_filtro=args.sin_filtro,
            usar_excel_asesor=args.excel_asesor is not None,
            mes=args.mes,
            anio=args.anio,
            repo_root=args.repo,
        )
        if rc == 0:
            notification_manager.send_process_success()
        else:
            notification_manager.send_process_error(
                Exception("Lote sin solicitudes OK"),
                etapa="procesamiento del lote (sin solicitudes OK)",
            )
            error_code = rc
        log_manager.info("")
        log_manager.info(
            "Fin → código %s%s",
            error_code,
            "" if error_code == 0 else " (sin emisiones OK o con error)",
        )
        log_manager.info_file("%s ha finalizado", config_manager.config.get("PROCESS_NAME"))
    except Exception as exc:
        logger.error("Error en el proceso", exc_info=True)
        notification_manager.send_process_error(exception=exc, etapa="ejecución del proceso")
        error_code = 1
        log_manager.info("Fin → código 1 (error)")

    return error_code


if __name__ == "__main__":
    raise SystemExit(main())
