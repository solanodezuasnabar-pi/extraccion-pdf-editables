"""Snapshot del lote y duplicados ambiguos (spec consolidación mensual)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.lote import publicar_archivo, separar_duplicados_ambiguos, tomar_snapshot
from src.models import Asegurado, FormaPago, SolicitudSalud
from src.periodo import CARPETA_SOLICITUDES, Periodo


def _asesor_con_pdfs(root: Path, nombre: str, carpeta_mes: str, pdfs: list[str]) -> Path:
    mes = root / nombre / CARPETA_SOLICITUDES / carpeta_mes
    mes.mkdir(parents=True)
    for pdf in pdfs:
        (mes / pdf).write_bytes(b"%PDF-1.4\n")
    return mes


def _solicitud(
    *,
    archivo: str,
    asesor: str,
    dni: int | None,
    ruta: str = "",
) -> SolicitudSalud:
    return SolicitudSalud(
        archivo_origen=archivo,
        asesor_origen=asesor,
        ruta_origen=ruta,
        apellido_nombre_tomador="PEREZ JUAN",
        nro_documento_tomador=dni,
        calle="SAN MARTIN",
        nro="1",
        codigo_postal=5000,
        plan="5",
        modulo=1,
        forma_pago=FormaPago.EFECTIVO,
        productor="1",
        organizador="2",
        inicio_vigencia=datetime(2026, 8, 1),
        fin_vigencia=datetime(2027, 8, 1),
        asegurados=[Asegurado(nombre="PEREZ JUAN", nro_documento=dni, relacion="Titular")],
    )


class TestSnapshotLote(unittest.TestCase):
    def test_lista_asesores_y_pdfs_del_periodo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _asesor_con_pdfs(root, "ANA", "002 VTAS AGOSTO 26", ["a.pdf"])
            _asesor_con_pdfs(root, "BOB", "002 VTAS AGOSTO 26", ["b.pdf"])
            lote = tomar_snapshot(root, Periodo(anio=2026, mes=8))
            pares = {(item.asesor, item.pdf.name) for item in lote.items}
            self.assertEqual(pares, {("ANA", "a.pdf"), ("BOB", "b.pdf")})

    def test_pdf_agregado_despues_no_entra_al_lote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mes = _asesor_con_pdfs(root, "ANA", "002 VTAS AGOSTO 26", ["a.pdf"])
            lote = tomar_snapshot(root, Periodo(anio=2026, mes=8))
            (mes / "tarde.pdf").write_bytes(b"%PDF-1.4\n")
            nombres = [item.pdf.name for item in lote.items]
            self.assertEqual(nombres, ["a.pdf"])
            self.assertNotIn("tarde.pdf", nombres)


class TestDuplicadosAmbiguos(unittest.TestCase):
    def test_mismo_asesor_y_dni_ninguno_se_emite(self) -> None:
        emitibles, ambiguos = separar_duplicados_ambiguos(
            [
                _solicitud(archivo="v1.pdf", asesor="ANA", dni=20123456),
                _solicitud(archivo="v2.pdf", asesor="ANA", dni=20123456),
            ],
            periodo_slug="08_2026",
        )
        self.assertEqual(emitibles, [])
        self.assertEqual(len(ambiguos), 1)
        self.assertEqual({s.archivo_origen for s in ambiguos[0]}, {"v1.pdf", "v2.pdf"})

    def test_mismo_dni_distinto_asesor_no_es_ambiguo(self) -> None:
        emitibles, ambiguos = separar_duplicados_ambiguos(
            [
                _solicitud(archivo="ana.pdf", asesor="ANA", dni=20123456),
                _solicitud(archivo="bob.pdf", asesor="BOB", dni=20123456),
            ],
            periodo_slug="08_2026",
        )
        self.assertEqual({s.archivo_origen for s in emitibles}, {"ana.pdf", "bob.pdf"})
        self.assertEqual(ambiguos, [])


class TestPublicarArchivo(unittest.TestCase):
    def test_reemplaza_destino_y_no_deja_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            origen = Path(tmp) / "nuevo.txt"
            destino = Path(tmp) / "final.txt"
            origen.write_text("nuevo", encoding="utf-8")
            destino.write_text("viejo", encoding="utf-8")
            publicado = publicar_archivo(origen, destino)
            self.assertEqual(publicado, destino)
            self.assertEqual(destino.read_text(encoding="utf-8"), "nuevo")
            self.assertFalse((Path(tmp) / "final.tmp.txt").exists())


if __name__ == "__main__":
    unittest.main()
