"""Token app-only de Microsoft Graph (PEM o store de Windows)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .graph_config import GraphConfig
from .graph_http import GraphError
from .paths import resource_root

_PS_TOKEN = resource_root() / "scripts" / "graph_token_windows.ps1"
_PS_TIMEOUT_S = 60


def _token_store_windows(cfg: GraphConfig) -> str:
    if not cfg.thumbprint:
        raise GraphError("GRAPH_THUMBPRINT vacío")
    if not _PS_TOKEN.is_file():
        raise GraphError(f"No está {_PS_TOKEN} (hace falta para el store de Windows)")
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
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=_PS_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise GraphError(
            f"No se obtuvo token del store de Windows (timeout {_PS_TIMEOUT_S}s)"
        ) from exc
    token = (proc.stdout or "").strip()
    if proc.returncode != 0 or not token:
        err = (proc.stderr or proc.stdout or "sin detalle").strip()
        raise GraphError(f"No se obtuvo token del store de Windows: {err}")
    return token


def acquire_token(cfg: GraphConfig) -> str:
    if not cfg.cert_path:
        return _token_store_windows(cfg)
    pem = Path(cfg.cert_path)
    if not pem.is_file():
        raise GraphError(f"No existe GRAPH_CERT_PATH: {pem}")
    private_key = pem.read_text(encoding="utf-8")
    if not cfg.thumbprint:
        raise GraphError("GRAPH_THUMBPRINT vacío")

    import msal

    app = msal.ConfidentialClientApplication(
        cfg.client_id,
        authority=f"https://login.microsoftonline.com/{cfg.tenant_id}",
        client_credential={"thumbprint": cfg.thumbprint, "private_key": private_key},
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    token = (result or {}).get("access_token")
    if not token:
        raise GraphError(result.get("error_description") or "No se obtuvo token Graph")
    return token
