"""Carga de configuración por entorno (estilo template-rpa-main)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

from ..paths import app_root, resolve_existing, resource_root

config: dict = {}

_ENV_KEYS = [
    "PROCESS_ENV",
    "PROCESS_NAME",
    "SMTP_SERVER",
    "SMTP_PORT",
    "PROCESS_EMAIL",
    "PROCESS_ERROR_EMAILS",
    "PROCESS_SUCCESS_EMAILS",
    "LOGS",
    "INPUTS",
    "OUTPUTS",
    "TEMPLATES",
    "MAIL_TEMPLATES",
    "NOTIFY_ENABLED",
    "MAIL_SAVE_LOCAL",
]


def _ensure_configs_alongside_exe() -> None:
    """Si el .exe no tiene configs/ editables al lado, copia las embebidas una vez."""
    dest = app_root() / "configs"
    if dest.is_dir() and any(dest.glob("*.env")):
        return
    src = resource_root() / "configs"
    if not src.is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for env_file in src.glob("*.env"):
        target = dest / env_file.name
        if not target.exists():
            shutil.copy2(env_file, target)


def _dotenv_path(env: str | None) -> Path:
    name = f".{env}.env" if env else ".env"
    found = resolve_existing("configs", name)
    if found is None:
        raise FileNotFoundError(
            f"No se encontró configuración: configs/{name} "
            f"(buscado en {app_root()} y recursos embebidos)"
        )
    return found


def read_config(env: str | None = None) -> dict:
    """Carga `configs/.{env}.env` (junto al exe o embebido)."""
    global config

    _ensure_configs_alongside_exe()
    dotenv_file = _dotenv_path(env)
    project = app_root()

    if not load_dotenv(dotenv_path=dotenv_file, override=False):
        raise RuntimeError(f"Error al cargar el archivo de configuración: {dotenv_file}")
    if not os.getenv("PROCESS_NAME") or not os.getenv("PROCESS_ENV"):
        if not load_dotenv(dotenv_path=dotenv_file, override=True):
            raise RuntimeError(f"Error al cargar el archivo de configuración: {dotenv_file}")

    config = {key: os.getenv(key) for key in _ENV_KEYS}
    config["WORKING_DIR"] = str(project)
    config["NOTIFY_ENABLED"] = (config.get("NOTIFY_ENABLED") or "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "si",
        "sí",
    }
    config["MAIL_SAVE_LOCAL"] = (config.get("MAIL_SAVE_LOCAL") or "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "si",
        "sí",
    }

    # Resolver rutas relativas a la carpeta del exe / proyecto
    for key in ("LOGS", "INPUTS", "OUTPUTS", "TEMPLATES", "MAIL_TEMPLATES"):
        raw = config.get(key)
        if not raw:
            if key == "MAIL_TEMPLATES":
                raw = "./Plantillas"
            else:
                raw = f"./{key.lower()}"
        path = Path(raw)
        if not path.is_absolute():
            path = project / path
        # INPUTS puede apuntar a un repo que aún no existe en la máquina de build;
        # solo forzar mkdir en carpetas de trabajo del bot.
        if key in ("LOGS", "OUTPUTS", "TEMPLATES"):
            path.mkdir(parents=True, exist_ok=True)
        config[key] = str(path)

    return config
