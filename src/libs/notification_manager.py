"""Notificaciones SMTP con plantillas HTML (Plantillas/)."""

from __future__ import annotations

import mimetypes
import smtplib
import socket
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..paths import resolve_existing
from . import config_manager, log_manager

_TEMPLATE_INICIO = "CorreoInicioProceso.html"
_TEMPLATE_FIN = "CorreoFinProceso1.html"
_TEMPLATE_ERROR = "CorreoErrorProceso.html"
_NETWORK_WINERRORS = {10051, 10053, 10054, 10060, 10061, 10065}

_run_dir: Path | None = None


def _logger():
    return log_manager.get_logger()


def _notify_enabled() -> bool:
    return bool(config_manager.config.get("NOTIFY_ENABLED"))


def _mail_save_enabled() -> bool:
    return bool(config_manager.config.get("MAIL_SAVE_LOCAL"))


def _plantillas_dir() -> Path:
    raw = (config_manager.config.get("MAIL_TEMPLATES") or "").strip()
    if raw:
        path = Path(raw)
        if path.is_dir():
            return path
    found = resolve_existing("Plantillas")
    if found and found.is_dir():
        return found
    raise FileNotFoundError(
        "No se encontró la carpeta Plantillas/ (mails). "
        "Definí MAIL_TEMPLATES o incluí Plantillas junto al proyecto/.exe."
    )


def _mail_output_dir() -> Path:
    global _run_dir
    if _run_dir is None:
        base = Path(config_manager.config.get("OUTPUTS") or "output")
        correos = base / "correos"
        correos.mkdir(parents=True, exist_ok=True)
        stamp = _ahora().strftime("%Y-%m-%d_%H%M%S")
        _run_dir = correos / stamp
        _run_dir.mkdir(parents=True, exist_ok=True)
    return _run_dir


def _split_emails(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.replace(",", ";").split(";") if p.strip()]


def _ahora() -> datetime:
    return datetime.now()


def _fmt_fecha(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y")


def _fmt_hora(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")


def _render_mail(mail_template: str, data: dict) -> str:
    templates_path = _plantillas_dir()
    env = Environment(
        loader=FileSystemLoader(str(templates_path)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    return env.get_template(mail_template).render(**data)


def _save_mail_local(slug: str, subject: str, html: str) -> Path:
    out_dir = _mail_output_dir()
    path = out_dir / f"{slug}.html"
    path.write_text(html, encoding="utf-8")
    meta = out_dir / "asuntos.txt"
    with meta.open("a", encoding="utf-8") as fh:
        fh.write(f"{slug}.html\t{subject}\n")
    return path


def _send_smtp(
    to: list[str],
    subject: str,
    html_content: str,
    attachment: str | Path | None = None,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config_manager.config.get("PROCESS_EMAIL") or ""
    msg["To"] = ", ".join(to)
    msg.set_content("Este correo requiere un cliente compatible con HTML.")
    msg.add_alternative(html_content, subtype="html")

    if attachment is not None:
        att = Path(attachment)
        if att.is_file():
            mime_type, _ = mimetypes.guess_type(str(att))
            if mime_type is None:
                mime_type = "application/octet-stream"
            main_type, sub_type = mime_type.split("/", 1)
            msg.add_attachment(
                att.read_bytes(),
                maintype=main_type,
                subtype=sub_type,
                filename=att.name,
            )

    server = config_manager.config.get("SMTP_SERVER") or ""
    port = int(config_manager.config.get("SMTP_PORT") or 25)
    if not server:
        raise RuntimeError("SMTP_SERVER no configurado")

    with smtplib.SMTP(server, port, timeout=10) as smtp:
        smtp.send_message(msg)
    _logger().info("Mail enviado a %s — %s", to, subject)


def send_mail(
    to: list[str] | str,
    subject: str,
    mail_template: str,
    data: dict,
    attachment: str | Path | None = None,
    *,
    save_slug: str | None = None,
) -> None:
    if isinstance(to, str):
        to = _split_emails(to)

    html_content = _render_mail(mail_template, data)

    if save_slug and _mail_save_enabled():
        path = _save_mail_local(save_slug, subject, html_content)
        _logger().info("Mail guardado: %s — %s", path, subject)

    if not _notify_enabled():
        if not (save_slug and _mail_save_enabled()):
            _logger().info("NOTIFY_ENABLED=false — omitido envío SMTP (%s)", subject)
        return

    if not to:
        _logger().warning("Envío SMTP omitido: sin destinatarios (%s)", subject)
        return

    _send_smtp(to, subject, html_content, attachment)


def _log_fallo_mail(contexto: str, exc: BaseException) -> None:
    """Red/DNS: warning corto en consola; detalle en archivo. Otros: traceback."""
    es_error_red = isinstance(
        exc,
        (TimeoutError, socket.gaierror, socket.herror, ConnectionError),
    ) or (
        isinstance(exc, OSError)
        and getattr(exc, "winerror", None) in _NETWORK_WINERRORS
    )
    if es_error_red:
        server = config_manager.config.get("SMTP_SERVER") or "?"
        port = config_manager.config.get("SMTP_PORT") or "?"
        log_manager.warning(
            "Mail %s omitido (SMTP no alcanzable). Detalle en logs/process.log.",
            contexto,
            channel="console",
        )
        log_manager.warning_file(
            "Mail %s omitido (SMTP %s:%s no alcanzable: %s). Revisá VPN / DNS. El lote sigue.",
            contexto,
            server,
            port,
            exc,
        )
        return
    _logger().exception("No se pudo enviar mail de %s", contexto)


def send_process_start() -> None:
    """Mail de inicio (plantilla CorreoInicioProceso)."""
    if not _notify_enabled() and not _mail_save_enabled():
        _logger().info("NOTIFY_ENABLED=false — omitido mail de inicio")
        return
    try:
        now = _ahora()
        nombre = config_manager.config.get("PROCESS_NAME") or "Proceso"
        send_mail(
            to=_split_emails(config_manager.config.get("PROCESS_SUCCESS_EMAILS")),
            subject=f"Inicio proceso {nombre}",
            mail_template=_TEMPLATE_INICIO,
            data={
                "nombre_proceso": nombre,
                "hora_inicio": _fmt_hora(now),
                "fecha_inicio": _fmt_fecha(now),
                "FECHA_FIN": _fmt_fecha(now),
            },
            save_slug="01_inicio",
        )
    except Exception as exc:
        _log_fallo_mail("inicio", exc)


def send_process_success(summary: str | None = None) -> None:
    """Mail de fin OK (plantilla CorreoFinProceso1)."""
    if not _notify_enabled() and not _mail_save_enabled():
        _logger().info("NOTIFY_ENABLED=false — omitido mail de éxito%s", f": {summary}" if summary else "")
        return
    try:
        now = _ahora()
        nombre = config_manager.config.get("PROCESS_NAME") or "Proceso"
        send_mail(
            to=_split_emails(config_manager.config.get("PROCESS_SUCCESS_EMAILS")),
            subject=f"Proceso {nombre} completado exitosamente",
            mail_template=_TEMPLATE_FIN,
            data={
                "nombre_proceso": nombre,
                "HORA_FIN": _fmt_hora(now),
                "FECHA_FIN": _fmt_fecha(now),
            },
            save_slug="02_fin_ok",
        )
    except Exception as exc:
        _log_fallo_mail("éxito", exc)


def send_process_error(exception, etapa: str = "ejecución del proceso") -> None:
    """Mail de error (plantilla CorreoErrorProceso)."""
    if not _notify_enabled() and not _mail_save_enabled():
        _logger().error("Proceso con error (notify off): %s", exception)
        return
    try:
        now = _ahora()
        nombre = config_manager.config.get("PROCESS_NAME") or "Proceso"
        send_mail(
            to=_split_emails(config_manager.config.get("PROCESS_ERROR_EMAILS")),
            subject=f"Error en el proceso {nombre}",
            mail_template=_TEMPLATE_ERROR,
            data={
                "nombre_proceso": nombre,
                "etapa_excepcion": etapa,
                "horario_ejecucion": _fmt_hora(now),
                "fecha_ejecucion": _fmt_fecha(now),
            },
            save_slug="02_error",
        )
    except Exception as exc:
        _log_fallo_mail("error", exc)
