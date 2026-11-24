"""Prueba de envío de correo con la configuración de un entorno (dev/tst/pro).

Lee configs/.{env}.env igual que el bot, verifica conectividad con el relay
SMTP y envía los mails de inicio y fin (mismas plantillas que usa el proceso).
Muestra la respuesta real del relay (id de cola) para poder reclamar a IT.

Uso (desde la raíz del proyecto):
  .\\.venv\\Scripts\\python.exe scripts\\probar_correo_resumen.py --env tst
  .\\.venv\\Scripts\\python.exe scripts\\probar_correo_resumen.py --env tst --a otra@casilla.com
  .\\.venv\\Scripts\\python.exe scripts\\probar_correo_resumen.py --env pro --solo-conexion
  .\\.venv\\Scripts\\python.exe scripts\\probar_correo_resumen.py --env tst --error

El dump SMTP crudo está en scripts/probar_correo.py.
Envía aunque NOTIFY_ENABLED sea false (es una prueba); lo avisa por pantalla.
"""

from __future__ import annotations

import argparse
import smtplib
import socket
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


def _sep(titulo: str) -> None:
    print(f"\n{'=' * 8} {titulo} {'=' * 8}")


def _conectar(server: str, port: int) -> smtplib.SMTP | None:
    _sep("Conexión")
    try:
        ip = socket.gethostbyname(server)
        print(f"DNS      {server} -> {ip}")
    except socket.gaierror as exc:
        print(f"DNS      FALLÓ: {exc}")
        print("         Revisá VPN / DNS corporativo.")
        return None
    try:
        smtp = smtplib.SMTP(server, port, timeout=TIMEOUT)
    except (TimeoutError, OSError) as exc:
        print(f"TCP      {server}:{port} NO ALCANZABLE ({exc})")
        print(
            "         Este relay no acepta conexiones desde esta red.\n"
            "         Si es smtp-pro: es esperado desde la PC de desarrollo;\n"
            "         hay que correr esta prueba desde el servidor RPA."
        )
        return None
    code, banner = smtp.ehlo()
    print(f"EHLO     {code} {banner.decode(errors='replace').splitlines()[0]}")
    ext = [e for e in ("dsn", "starttls", "auth", "size") if smtp.has_extn(e)]
    print(f"Soporta  {', '.join(ext) or '-'}")
    return smtp


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
    """Envía paso a paso para mostrar la respuesta del relay (id de cola)."""
    print(f"\n-> {msg['Subject']}")
    smtp.rset()
    code, resp = smtp.mail(remitente)
    print(f"   MAIL FROM {remitente:45} {code} {resp.decode(errors='replace')}")
    if code != 250:
        return False
    ok = True
    for d in destinos:
        code, resp = smtp.rcpt(d)
        print(f"   RCPT TO   {d:45} {code} {resp.decode(errors='replace')}")
        ok = ok and code in (250, 251)
    if not ok:
        smtp.rset()
        return False
    code, resp = smtp.data(msg.as_bytes())
    print(f"   DATA      {'':45} {code} {resp.decode(errors='replace')}")
    return code == 250


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", default="tst", choices=["dev", "tst", "pro"], help="entorno (configs/.{env}.env)")
    ap.add_argument("--a", dest="destino", help="destinatario alternativo (ignora PROCESS_*_EMAILS)")
    ap.add_argument("--error", action="store_true", help="enviar también el mail de error")
    ap.add_argument("--solo-conexion", action="store_true", help="no enviar; solo probar DNS/TCP/EHLO")
    args = ap.parse_args()

    config_manager.read_config(args.env)
    log_manager.get_logger()
    cfg = config_manager.config

    server = (cfg.get("SMTP_SERVER") or "").strip()
    port = int(cfg.get("SMTP_PORT") or 25)
    remitente = (cfg.get("PROCESS_EMAIL") or "").strip()
    ok_dest = [args.destino] if args.destino else nm._split_emails(cfg.get("PROCESS_SUCCESS_EMAILS"))
    err_dest = [args.destino] if args.destino else nm._split_emails(cfg.get("PROCESS_ERROR_EMAILS"))

    _sep(f"Configuración .{args.env}.env")
    print(f"SMTP_SERVER            {server}:{port}")
    print(f"PROCESS_EMAIL (from)   {remitente}")
    print(f"PROCESS_SUCCESS_EMAILS {', '.join(ok_dest) or '(vacío)'}")
    print(f"PROCESS_ERROR_EMAILS   {', '.join(err_dest) or '(vacío)'}")
    print(f"NOTIFY_ENABLED         {cfg.get('NOTIFY_ENABLED')}")
    if not cfg.get("NOTIFY_ENABLED"):
        print("  AVISO: con NOTIFY_ENABLED=false el bot NO envía en este entorno.")
        print("         Esta prueba envía igual; para que el bot lo haga, ponelo en true.")

    faltan = [k for k, v in (("SMTP_SERVER", server), ("PROCESS_EMAIL", remitente)) if not v]
    if faltan or not ok_dest:
        print(f"\nERROR: faltan variables: {', '.join(faltan + ([] if ok_dest else ['PROCESS_SUCCESS_EMAILS']))}")
        return 2

    smtp = _conectar(server, port)
    if smtp is None:
        return 1
    if args.solo_conexion:
        smtp.quit()
        print("\nConexión OK. No se envió nada (--solo-conexion).")
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

    _sep("Envío")
    resultados = []
    with smtp:
        for subject, html, destinos in envios:
            msg = _armar(subject, html, remitente, destinos)
            resultados.append(_enviar(smtp, msg, remitente, destinos))

    _sep("Resultado")
    aceptados = sum(resultados)
    print(f"{aceptados}/{len(resultados)} mensajes aceptados por {server}.")
    if aceptados:
        print(
            "Un 250 con 'Queued' significa que el RELAY lo tomó, no que llegó.\n"
            f"Revisá la casilla (Inbox y Spam) en 2-3 minutos: {', '.join(sorted(set(ok_dest + err_dest)))}\n"
            
        )
    return 0 if aceptados == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
