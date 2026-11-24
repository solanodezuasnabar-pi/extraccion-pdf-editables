"""Conector Graph: listar mes, materializar, publicar y limpiar (HTTP falso)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

from src.graph_config import GraphConfig
from src.graph_conector import (
    ItemRemoto,
    listar_pdfs_periodo,
    materializar_lote,
    preparar_repo_desde_graph,
    publicar_salida,
)
from src.graph_http import GraphError, GraphHttp
from src.periodo import CARPETA_SOLICITUDES, Periodo

DRIVE = "drive-1"
SITE = "site-1"
LIST_ID = "list-1"
CFG = GraphConfig(
    tenant_id="t",
    client_id="c",
    thumbprint="th",
    cert_path="C:/certs/vavi.pem",
    site_id=SITE,
    list_id=LIST_ID,
    vavi_root="SOLICITUDES SALUD VAVI-RETIRO",
    salida="_salida",
)


def _children(items: list[dict], next_link: str | None = None) -> dict:
    body: dict = {"value": items}
    if next_link:
        body["@odata.nextLink"] = next_link
    return body


class FakeHttp:
    def __init__(self, routes: dict[tuple[str, str], object]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str]] = []
        self.puts: list[tuple[str, bytes]] = []

    def _key(self, method: str, url: str) -> tuple[str, str]:
        return method.upper(), unquote(url)

    def request_json(self, method: str, url: str, **kwargs) -> dict:
        self.calls.append((method.upper(), url))
        key = self._key(method, url)
        if key not in self.routes:
            raise GraphError(f"sin ruta {key}")
        payload = self.routes[key]
        if callable(payload):
            payload = payload()
        if isinstance(payload, GraphError):
            raise payload
        return payload

    def request_bytes(self, method: str, url: str, **kwargs) -> bytes:
        self.calls.append((method.upper(), url))
        key = self._key(method, url)
        payload = self.routes[key]
        if callable(payload):
            payload = payload()
        if isinstance(payload, GraphError):
            raise payload
        if isinstance(payload, bytes):
            return payload
        return json.dumps(payload).encode()

    def put_bytes(self, url: str, data: bytes, content_type: str = "") -> dict:
        self.calls.append(("PUT", url))
        self.puts.append((unquote(url), data))
        return {"name": Path(unquote(url)).name}


def _drive_routes() -> dict[tuple[str, str], object]:
    vavi = "SOLICITUDES SALUD VAVI-RETIRO"
    base = f"https://graph.microsoft.com/v1.0/drives/{DRIVE}"
    return {
        (
            "GET",
            f"https://graph.microsoft.com/v1.0/sites/{SITE}/lists/{LIST_ID}/drive",
        ): {"id": DRIVE},
        (
            "GET",
            f"{base}/root:/{vavi}:/children",
        ): _children(
            [
                {"name": "ANA", "id": "ana", "folder": {}},
                {"name": "BOB", "id": "bob", "folder": {}},
                {"name": "_salida", "id": "out", "folder": {}},
            ]
        ),
        (
            "GET",
            f"{base}/root:/{vavi}/ANA/{CARPETA_SOLICITUDES}:/children",
        ): _children(
            [
                {"name": "002 VTAS FEBRERO 26", "id": "ana-feb", "folder": {}},
                {"name": "003 VTAS MARZO 26", "id": "ana-mar", "folder": {}},
            ]
        ),
        (
            "GET",
            f"{base}/root:/{vavi}/BOB/{CARPETA_SOLICITUDES}:/children",
        ): _children(
            [
                {"name": "002 VTAS FEBRERO 26", "id": "bob-feb", "folder": {}},
            ]
        ),
        (
            "GET",
            f"{base}/root:/{vavi}/ANA/{CARPETA_SOLICITUDES}/002 VTAS FEBRERO 26:/children",
        ): _children(
            [
                {"name": "a.pdf", "id": "pdf-a", "file": {}},
                {"name": "viejo.xlsx", "id": "xlsx-a", "file": {}},
            ]
        ),
        (
            "GET",
            f"{base}/root:/{vavi}/ANA/{CARPETA_SOLICITUDES}/003 VTAS MARZO 26:/children",
        ): _children([{"name": "marzo.pdf", "id": "pdf-mar", "file": {}}]),
        (
            "GET",
            f"{base}/root:/{vavi}/BOB/{CARPETA_SOLICITUDES}/002 VTAS FEBRERO 26:/children",
        ): _children([{"name": "b.pdf", "id": "pdf-b", "file": {}}]),
        ("GET", f"{base}/items/pdf-a/content"): b"%PDF-ANA",
        ("GET", f"{base}/items/pdf-b/content"): b"%PDF-BOB",
        ("GET", f"{base}/items/pdf-mar/content"): b"%PDF-MAR",
    }


def _drive_routes_persona() -> dict[tuple[str, str], object]:
    """ANA febrero: PDF suelto + carpetas de persona (un nivel) + nieto que no entra."""
    routes = dict(_drive_routes())
    vavi = "SOLICITUDES SALUD VAVI-RETIRO"
    base = f"https://graph.microsoft.com/v1.0/drives/{DRIVE}"
    mes = f"{base}/root:/{vavi}/ANA/{CARPETA_SOLICITUDES}/002 VTAS FEBRERO 26"
    routes[("GET", f"{mes}:/children")] = _children(
        [
            {"name": "a.pdf", "id": "pdf-a", "file": {}},
            {"name": "viejo.xlsx", "id": "xlsx-a", "file": {}},
            {"name": "Persona Ejemplo", "id": "fold-persona", "folder": {}},
            {"name": "Vacia", "id": "fold-vacia", "folder": {}},
            {"name": "PersonaA", "id": "fold-pa", "folder": {}},
            {"name": "PersonaB", "id": "fold-pb", "folder": {}},
        ]
    )
    routes[("GET", f"{mes}/Persona Ejemplo:/children")] = _children(
        [
            {"name": "bar.pdf", "id": "pdf-bar", "file": {}},
            {"name": "otra", "id": "fold-otra", "folder": {}},
        ]
    )
    routes[("GET", f"{mes}/Persona Ejemplo/otra:/children")] = _children(
        [{"name": "x.pdf", "id": "pdf-nieto", "file": {}}]
    )
    routes[("GET", f"{mes}/Vacia:/children")] = _children([])
    routes[("GET", f"{mes}/PersonaA:/children")] = _children(
        [{"name": "solicitud.pdf", "id": "pdf-pa", "file": {}}]
    )
    routes[("GET", f"{mes}/PersonaB:/children")] = _children(
        [{"name": "solicitud.pdf", "id": "pdf-pb", "file": {}}]
    )
    routes[("GET", f"{base}/items/pdf-bar/content")] = b"%PDF-BAR"
    routes[("GET", f"{base}/items/pdf-pa/content")] = b"%PDF-PA"
    routes[("GET", f"{base}/items/pdf-pb/content")] = b"%PDF-PB"
    routes[("GET", f"{base}/items/pdf-nieto/content")] = b"%PDF-NIETO"
    return routes


class TestListarPeriodo(unittest.TestCase):
    def test_solo_pdf_del_mes_y_ignora_salida(self) -> None:
        http = FakeHttp(_drive_routes())
        items = listar_pdfs_periodo(http, CFG, Periodo(anio=2026, mes=2))
        pares = {(i.asesor, i.nombre) for i in items}
        self.assertEqual(pares, {("ANA", "a.pdf"), ("BOB", "b.pdf")})
        self.assertFalse(any(i.asesor == "_salida" for i in items))
        self.assertFalse(any(i.nombre == "marzo.pdf" for i in items))
        self.assertFalse(any(i.nombre.endswith(".xlsx") for i in items))


class TestListarSubcarpetaPersona(unittest.TestCase):
    def test_suelto_y_un_nivel_de_persona(self) -> None:
        http = FakeHttp(_drive_routes_persona())
        items = listar_pdfs_periodo(http, CFG, Periodo(anio=2026, mes=2))
        ana = {(i.nombre, i.subcarpeta) for i in items if i.asesor == "ANA"}
        self.assertIn(("a.pdf", ""), ana)
        self.assertIn(("bar.pdf", "Persona Ejemplo"), ana)
        self.assertIn(("solicitud.pdf", "PersonaA"), ana)
        self.assertIn(("solicitud.pdf", "PersonaB"), ana)
        self.assertFalse(any(i.nombre == "x.pdf" for i in items))
        self.assertFalse(any(i.nombre == "viejo.xlsx" for i in items))

    def test_carpeta_persona_vacia_no_falla(self) -> None:
        http = FakeHttp(_drive_routes_persona())
        items = listar_pdfs_periodo(http, CFG, Periodo(anio=2026, mes=2))
        self.assertFalse(any(i.subcarpeta == "Vacia" for i in items))

    def test_nieto_no_entra(self) -> None:
        http = FakeHttp(_drive_routes_persona())
        listar_pdfs_periodo(http, CFG, Periodo(anio=2026, mes=2))
        urls = [u for _, u in http.calls]
        self.assertFalse(any("Persona Ejemplo/otra" in unquote(u) for u in urls))

    def test_mismo_nombre_no_se_pisa_en_staging(self) -> None:
        http = FakeHttp(_drive_routes_persona())
        items = [
            i
            for i in listar_pdfs_periodo(http, CFG, Periodo(anio=2026, mes=2))
            if i.nombre == "solicitud.pdf"
        ]
        self.assertEqual(len(items), 2)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "repo"
            materializar_lote(http, CFG, items, dest)
            mes = dest / "ANA" / CARPETA_SOLICITUDES / "002 VTAS FEBRERO 26"
            pa = mes / "PersonaA" / "solicitud.pdf"
            pb = mes / "PersonaB" / "solicitud.pdf"
            self.assertEqual(pa.read_bytes(), b"%PDF-PA")
            self.assertEqual(pb.read_bytes(), b"%PDF-PB")


class TestMaterializar(unittest.TestCase):
    def test_pdf_listado_despues_no_se_baja(self) -> None:
        items = [
            ItemRemoto(
                asesor="ANA",
                carpeta_mes="002 VTAS FEBRERO 26",
                nombre="a.pdf",
                item_id="pdf-a",
            )
        ]
        routes = _drive_routes()
        http = FakeHttp(routes)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "repo"
            materializar_lote(http, CFG, items, dest)
            self.assertTrue((dest / "ANA" / CARPETA_SOLICITUDES / "002 VTAS FEBRERO 26" / "a.pdf").exists())
            self.assertEqual(
                (dest / "ANA" / CARPETA_SOLICITUDES / "002 VTAS FEBRERO 26" / "a.pdf").read_bytes(),
                b"%PDF-ANA",
            )
            routes[("GET", f"https://graph.microsoft.com/v1.0/drives/{DRIVE}/items/pdf-tarde/content")] = (
                b"%PDF-TARDE"
            )
            self.assertFalse(
                (dest / "ANA" / CARPETA_SOLICITUDES / "002 VTAS FEBRERO 26" / "tarde.pdf").exists()
            )


class TestPublicar(unittest.TestCase):
    def test_sube_a_salida_unica(self) -> None:
        http = FakeHttp({
            (
                "GET",
                f"https://graph.microsoft.com/v1.0/sites/{SITE}/lists/{LIST_ID}/drive",
            ): {"id": DRIVE},
        })
        with tempfile.TemporaryDirectory() as tmp:
            emision = Path(tmp) / "emision_02_2026.xlsx"
            reporte = Path(tmp) / "reporte_02_2026.xlsx"
            emision.write_bytes(b"EXCEL")
            reporte.write_bytes(b"REP")
            publicar_salida(http, CFG, [emision, reporte])
        destinos = [url for url, _ in http.puts]
        self.assertTrue(any("/_salida/emision_02_2026.xlsx:" in u for u in destinos))
        self.assertTrue(any("/_salida/reporte_02_2026.xlsx:" in u for u in destinos))
        self.assertFalse(
            any(
                "SOLICITUDES SALUD VAVI-RETIRO/emision_02_2026.xlsx:" in u and "/_salida/" not in u
                for u in destinos
            )
        )
        self.assertFalse(any("SOLICITUDES ESCANEADAS" in u for u in destinos))

    def test_emision_en_raiz_si_flag_false(self) -> None:
        cfg = GraphConfig(
            tenant_id="t",
            client_id="c",
            thumbprint="th",
            cert_path="C:/certs/vavi.pem",
            site_id=SITE,
            list_id=LIST_ID,
            vavi_root="SOLICITUDES SALUD VAVI-RETIRO",
            salida="_salida",
            publicar_todo_en_salida=False,
        )
        http = FakeHttp({
            (
                "GET",
                f"https://graph.microsoft.com/v1.0/sites/{SITE}/lists/{LIST_ID}/drive",
            ): {"id": DRIVE},
        })
        with tempfile.TemporaryDirectory() as tmp:
            emision = Path(tmp) / "emision_02_2026.xlsx"
            reporte = Path(tmp) / "reporte_02_2026.xlsx"
            emision.write_bytes(b"EXCEL")
            reporte.write_bytes(b"REP")
            publicar_salida(http, cfg, [emision, reporte])
        destinos = [url for url, _ in http.puts]
        self.assertTrue(
            any("SOLICITUDES SALUD VAVI-RETIRO/emision_02_2026.xlsx:" in u for u in destinos)
        )
        self.assertFalse(any("/_salida/emision_" in u for u in destinos))
        self.assertTrue(any("/_salida/reporte_02_2026.xlsx:" in u for u in destinos))

    def test_publicar_todo_en_salida(self) -> None:
        cfg = GraphConfig(
            tenant_id="t",
            client_id="c",
            thumbprint="th",
            cert_path="C:/certs/vavi.pem",
            site_id=SITE,
            list_id=LIST_ID,
            vavi_root="SOLICITUDES SALUD VAVI-RETIRO",
            salida="_listar",
            publicar_todo_en_salida=True,
        )
        http = FakeHttp({
            (
                "GET",
                f"https://graph.microsoft.com/v1.0/sites/{SITE}/lists/{LIST_ID}/drive",
            ): {"id": DRIVE},
        })
        with tempfile.TemporaryDirectory() as tmp:
            emision = Path(tmp) / "emision_01_2000.xlsx"
            reporte = Path(tmp) / "reporte_01_2000.xlsx"
            emision.write_bytes(b"EXCEL")
            reporte.write_bytes(b"REP")
            publicar_salida(http, cfg, [emision, reporte])
        destinos = [url for url, _ in http.puts]
        self.assertTrue(any("/_listar/emision_01_2000.xlsx:" in u for u in destinos))
        self.assertTrue(any("/_listar/reporte_01_2000.xlsx:" in u for u in destinos))
        self.assertFalse(any("SOLICITUDES SALUD VAVI-RETIRO/emision_01_2000.xlsx:" in u and "/_listar/" not in u for u in destinos))

    def test_423_no_aborta_el_otro_archivo(self) -> None:
        class LockedHttp(FakeHttp):
            def put_bytes(self, url: str, data: bytes, content_type: str = "") -> dict:
                if "reporte_" in url:
                    raise GraphError("locked", status_code=423)
                return super().put_bytes(url, data, content_type)

        http = LockedHttp({
            (
                "GET",
                f"https://graph.microsoft.com/v1.0/sites/{SITE}/lists/{LIST_ID}/drive",
            ): {"id": DRIVE},
        })
        with tempfile.TemporaryDirectory() as tmp:
            emision = Path(tmp) / "emision_01_2000.xlsx"
            reporte = Path(tmp) / "reporte_01_2000.xlsx"
            emision.write_bytes(b"EXCEL")
            reporte.write_bytes(b"REP")
            publicados = publicar_salida(http, CFG, [emision, reporte])
        self.assertEqual(len(publicados), 1)
        self.assertTrue(publicados[0].endswith("emision_01_2000.xlsx"))


class _FakeResp:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = {}

    def json(self):
        return self._payload

    @property
    def content(self):
        return b""


class _SeqSession:
    def __init__(self, codes: list[int]) -> None:
        self.codes = codes
        self.n = 0

    def request(self, method, url, **kwargs):
        code = self.codes[min(self.n, len(self.codes) - 1)]
        self.n += 1
        if code == 200:
            return _FakeResp(200, {"id": DRIVE})
        return _FakeResp(code, {})


class TestReintentos(unittest.TestCase):
    def test_423_luego_ok(self) -> None:
        session = _SeqSession([423, 200])
        http = GraphHttp(token="t", session=session, sleep=lambda _s: None)
        data = http.request_json(
            "GET",
            f"https://graph.microsoft.com/v1.0/sites/{SITE}/lists/{LIST_ID}/drive",
        )
        self.assertEqual(data["id"], DRIVE)
        self.assertEqual(session.n, 2)

    def test_429_luego_ok(self) -> None:
        session = _SeqSession([429, 200])
        http = GraphHttp(token="t", session=session, sleep=lambda _s: None)
        data = http.request_json(
            "GET",
            f"https://graph.microsoft.com/v1.0/sites/{SITE}/lists/{LIST_ID}/drive",
        )
        self.assertEqual(data["id"], DRIVE)
        self.assertEqual(session.n, 2)


class TestLimpieza(unittest.TestCase):
    def test_falla_a_mitad_no_deja_staging(self) -> None:
        routes = _drive_routes()

        class BoomHttp(FakeHttp):
            def request_bytes(self, method: str, url: str, **kwargs) -> bytes:
                if "pdf-b" in url:
                    raise GraphError("boom")
                return super().request_bytes(method, url, **kwargs)

        http = BoomHttp(routes)
        with tempfile.TemporaryDirectory() as parent:
            parent_path = Path(parent)
            with self.assertRaises(GraphError):
                preparar_repo_desde_graph(
                    http,
                    CFG,
                    Periodo(anio=2026, mes=2),
                    staging_parent=parent_path,
                )
            leftovers = [p for p in parent_path.iterdir() if p.name.startswith("vavi_graph_")]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
