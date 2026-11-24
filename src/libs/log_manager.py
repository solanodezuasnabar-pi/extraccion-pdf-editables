"""Logging de proceso: consola legible + archivo técnico detalle."""

from __future__ import annotations

import logging
from pathlib import Path

from . import config_manager

_CHANNEL_KEY = "channel"  # both | console | file


class _ChannelFilter(logging.Filter):
    """Filtra registros según destino: consola, archivo o ambos."""

    def __init__(self, channel: str) -> None:
        super().__init__()
        self.channel = channel

    def filter(self, record: logging.LogRecord) -> bool:
        target = getattr(record, _CHANNEL_KEY, "both")
        if target == "both":
            return True
        return target == self.channel


def get_logger(name: str | None = None) -> logging.Logger:
    if name is None:
        name = config_manager.config.get("PROCESS_NAME") or "emision-plan-familia-vavi"

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        logs_dir = Path(config_manager.config.get("LOGS") or "./logs")
        logs_dir.mkdir(parents=True, exist_ok=True)

        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_formatter = logging.Formatter("%(message)s")

        file_handler = logging.FileHandler(logs_dir / "process.log", encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(_ChannelFilter("file"))
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(_ChannelFilter("console"))
        logger.addHandler(console_handler)

        logger.propagate = False

    return logger


def _emit(level: int, msg: str, *args, channel: str = "both") -> None:
    get_logger().log(level, msg, *args, extra={_CHANNEL_KEY: channel})


def info(msg: str, *args, channel: str = "both") -> None:
    _emit(logging.INFO, msg, *args, channel=channel)


def warning(msg: str, *args, channel: str = "both") -> None:
    _emit(logging.WARNING, msg, *args, channel=channel)


def error(msg: str, *args, channel: str = "both") -> None:
    _emit(logging.ERROR, msg, *args, channel=channel)


def info_file(msg: str, *args) -> None:
    """Solo archivo (detalle técnico / ruido)."""
    info(msg, *args, channel="file")


def warning_file(msg: str, *args) -> None:
    warning(msg, *args, channel="file")


def short_path(path: Path | str, *, keep: int = 3) -> str:
    """Ruta relativa al cwd si se puede; si no, últimas N partes."""
    p = Path(path)
    try:
        return str(p.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        parts = p.parts
        if len(parts) <= keep:
            return str(p)
        return str(Path(*parts[-keep:]))
