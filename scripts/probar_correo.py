"""Prueba de envío SMTP. Imprime el diálogo crudo del servidor (debug smtplib).

Uso (desde la raíz del proyecto):
  .\\.venv\\Scripts\\python.exe scripts\\probar_correo.py --env tst
  .\\.venv\\Scripts\\python.exe scripts\\probar_correo.py --env tst --a otra@casilla.com
  .\\.venv\\Scripts\\python.exe scripts\\probar_correo.py --env pro --solo-conexion
  .\\.venv\\Scripts\\python.exe scripts\\probar_correo.py --env tst --error
"""

from __future__ import annotations

import argparse
import smtplib
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.libs import config_manager, log_manager, notification_manager as nm  # noqa: E402

TIMEOUT = 15
_TEMPLATE_INICIO = "CorreoInicioProceso_sin_fotos.html"
_TEMPLATE_FIN = "CorreoFinProceso1_sin_fotos.html"
_TEMPLATE_ERROR = "CorreoErrorProceso_sin_fotos.html"


def _armar(subject: str, html: str, remitente: str, destinos: list[str]) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = remitente
    msg["To"] = ", ".join(destinos)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=remitente.split("@")[-1] or None)
    msg.set_content("Este correo requiere un cliente compatible con HTML.")
    msg.add_alternative(html, subtype="html")
    return msg


def _enviar(smtp: smtplib.SMTP, msg: EmailMessage, remitente: str, destinos: list[str]) -> bool:
    smtp.rset()
    code, _resp = smtp.mail(remitente)
    if code != 250:
        return False
    for d in destinos:
        code, _resp = smtp.rcpt(d)
        if code not in (250, 251):
            smtp.rset()
            return False
    code, _resp = smtp.data(msg.as_bytes())
    return code == 250


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", default="tst", choices=["dev", "tst", "pro"])
    ap.add_argument("--a", dest="destino")
    ap.add_argument("--error", action="store_true")
    ap.add_argument("--solo-conexion", action="store_true")
    args = ap.parse_args()

    config_manager.read_config(args.env)
    log_manager.get_logger()
    cfg = config_manager.config

    server = (cfg.get("SMTP_SERVER") or "").strip()
    port = int(cfg.get("SMTP_PORT") or 25)
    remitente = (cfg.get("PROCESS_EMAIL") or "").strip()
    ok_dest = [args.destino] if args.destino else nm._split_emails(cfg.get("PROCESS_SUCCESS_EMAILS"))
    err_dest = [args.destino] if args.destino else nm._split_emails(cfg.get("PROCESS_ERROR_EMAILS"))

    if not server or not remitente or not ok_dest:
        return 2

    smtp = smtplib.SMTP(timeout=TIMEOUT)
    smtp.set_debuglevel(1)
    smtp.connect(server, port)
    smtp.ehlo()
    if args.solo_conexion:
        smtp.quit()
        return 0

    nombre = cfg.get("PROCESS_NAME") or "Proceso"
    now = nm._ahora()
    envios = [
        (
            f"[PRUEBA {args.env.upper()}] Inicio proceso {nombre}",
            nm._render_mail(
                _TEMPLATE_INICIO,
                {
                    "nombre_proceso": nombre,
                    "hora_inicio": nm._fmt_hora(now),
                    "fecha_inicio": nm._fmt_fecha(now),
                    "FECHA_FIN": nm._fmt_fecha(now),
                },
            ),
            ok_dest,
        ),
        (
            f"[PRUEBA {args.env.upper()}] Proceso {nombre} completado exitosamente",
            nm._render_mail(
                _TEMPLATE_FIN,
                {"nombre_proceso": nombre, "HORA_FIN": nm._fmt_hora(now), "FECHA_FIN": nm._fmt_fecha(now)},
            ),
            ok_dest,
        ),
    ]
    if args.error and err_dest:
        envios.append(
            (
                f"[PRUEBA {args.env.upper()}] Error en el proceso {nombre}",
                nm._render_mail(
                    _TEMPLATE_ERROR,
                    {
                        "nombre_proceso": nombre,
                        "etapa_excepcion": "prueba de envío",
                        "horario_ejecucion": nm._fmt_hora(now),
                        "fecha_ejecucion": nm._fmt_fecha(now),
                        "exception": "Excepción simulada por scripts/probar_correo.py",
                    },
                ),
                err_dest,
            )
        )

    resultados = []
    with smtp:
        for subject, html, destinos in envios:
            msg = _armar(subject, html, remitente, destinos)
            resultados.append(_enviar(smtp, msg, remitente, destinos))

    return 0 if resultados and all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
