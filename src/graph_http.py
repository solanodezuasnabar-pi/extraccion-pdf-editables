"""Cliente HTTP mínimo para Microsoft Graph (reintentos 423 / 429 / 5xx)."""

from __future__ import annotations

import time
from typing import Any, Callable

import requests

_RETRY = frozenset({423, 429, 500, 502, 503, 504})
_MAX_INTENTOS = 4
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


class GraphError(Exception):
    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class GraphHttp:
    def __init__(
        self,
        token: str,
        session: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.token = token
        self.session = session if session is not None else requests.Session()
        self.sleep = sleep

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if extra:
            headers.update(extra)
        return headers

    def _enviar(self, method: str, url: str, **kwargs) -> Any:
        headers = self._headers(kwargs.pop("headers", None))
        ultimo: GraphError | None = None
        for intento in range(1, _MAX_INTENTOS + 1):
            try:
                resp = self.session.request(method, url, headers=headers, timeout=60, **kwargs)
            except requests.RequestException as exc:
                ultimo = GraphError(str(exc))
                if intento == _MAX_INTENTOS:
                    raise ultimo from exc
                self.sleep(min(2 ** intento, 8))
                continue
            if resp.status_code in _RETRY and intento < _MAX_INTENTOS:
                espera = resp.headers.get("Retry-After")
                try:
                    delay = float(espera) if espera else min(2 ** intento, 8)
                except ValueError:
                    delay = min(2 ** intento, 8)
                self.sleep(delay)
                continue
            if resp.status_code >= 400:
                extra = ""
                if resp.status_code == 423:
                    extra = (
                        " (archivo bloqueado en SharePoint: cerralo en Excel/el navegador "
                        "y reintentá)"
                    )
                raise GraphError(
                    f"Graph {method} {url} → HTTP {resp.status_code}{extra}",
                    status_code=resp.status_code,
                )
            return resp
        raise ultimo or GraphError(f"Graph {method} {url} agotó reintentos")

    def request_json(self, method: str, url: str, **kwargs) -> dict:
        return self._enviar(method, url, **kwargs).json()

    def request_bytes(self, method: str, url: str, **kwargs) -> bytes:
        return self._enviar(method, url, **kwargs).content

    def put_bytes(self, url: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
        resp = self._enviar(
            "PUT",
            url,
            data=data,
            headers={"Content-Type": content_type},
        )
        try:
            return resp.json()
        except ValueError:
            return {}
