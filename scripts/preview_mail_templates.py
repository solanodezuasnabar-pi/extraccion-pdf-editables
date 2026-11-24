"""Genera HTML de muestra de las plantillas de correo (abrir en navegador)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
PLANTILLAS = ROOT / "Plantillas"
OUT = ROOT / "output" / "muestras_correo"

SAMPLES = [
    (
        "CorreoInicioProceso.html",
        "muestra_01_inicio_proceso.html",
        {
            "nombre_proceso": "Emision Plan Familia VAVI",
            "hora_inicio": "13:00:05",
            "fecha_inicio": "26/01/2026",
            "FECHA_FIN": "26/01/2026",
        },
    ),
    (
        "CorreoFinProceso1.html",
        "muestra_02_fin_proceso_ok.html",
        {
            "nombre_proceso": "Emision Plan Familia VAVI",
            "HORA_FIN": "13:04:32",
            "FECHA_FIN": "26/01/2026",
        },
    ),
    (
        "CorreoErrorProceso.html",
        "muestra_03_error_proceso.html",
        {
            "nombre_proceso": "Emision Plan Familia VAVI",
            "etapa_excepcion": "ejecución del proceso",
            "horario_ejecucion": "13:01:18",
            "fecha_ejecucion": "26/01/2026",
        },
    ),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(PLANTILLAS)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    now = datetime.now().strftime("%Y-%m-%d")
    for template, out_name, data in SAMPLES:
        html = env.get_template(template).render(**data)
        path = OUT / out_name
        path.write_text(html, encoding="utf-8")
        print(path)
    readme = OUT / "LEEME.txt"
    readme.write_text(
        f"Muestras generadas {now}\n\n"
        "Abrir en Chrome/Edge:\n"
        "  muestra_01_inicio_proceso.html  — mail al arrancar (Control-M 26 13:00)\n"
        "  muestra_02_fin_proceso_ok.html  — mail si termina bien\n"
        "  muestra_03_error_proceso.html   — mail si falla\n\n"
        "Asunto fin OK: Proceso Emision Plan Familia VAVI completado exitosamente\n"
        "Plantillas fuente: Plantillas/Correo*.html\n",
        encoding="utf-8",
    )
    print(readme)
    return 0


if __name__ == "__main__":
    sys.exit(main())
