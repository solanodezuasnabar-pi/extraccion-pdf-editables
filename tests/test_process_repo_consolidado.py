"""Corrida multi-asesor: un Excel y un reporte en output/, nada en carpetas de mes."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import fitz
import openpyxl

from src.models import Asegurado, FormaPago, SolicitudSalud
from src.periodo import CARPETA_SOLICITUDES, Periodo
from src.process_manager import process_repo
from src.report_builder import generar_reporte


def _pdf_vacio(path: Path) -> None:
    doc = fitz.open()
    try:
        doc.new_page()
        doc.save(path)
    finally:
        doc.close()


def _pdf_solicitud(path: Path, *, nombre: str, dni: str) -> None:
    """PDF editable con huella Plan Familia suficiente para selector + extracción."""
    doc = fitz.open()
    try:
        page = doc.new_page()
        campos = [
            ("APELLIDO Y NOMBRES", nombre),
            ("APELLIDO Y NOMBRES DEL TITULARRow1", nombre),
            ("CALLE", "SAN MARTIN"),
            ("LOCALIDAD", "CORDOBA"),
            ("NRO DE DOCUMENTORow1", dni),
            ("FECHA DE NACIMIENTORow1", "01011990"),
            ("ORGANIZADOR NRORow1", "1"),
            ("PRODUCTOR NRORow1", "2"),
            ("TIPO PLAN", "On"),
            ("undefined", dni),
            ("NRO", "100"),
        ]
        y = 40
        for campo, valor in campos:
            widget = fitz.Widget()
            widget.field_name = campo
            widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            widget.field_value = valor
            widget.rect = fitz.Rect(50, y, 300, y + 18)
            page.add_widget(widget)
            y += 22
        doc.save(path)
    finally:
        doc.close()


def _mini_repo(root: Path, factory=_pdf_vacio) -> None:
    for nombre in ("ANA", "BOB"):
        mes = root / nombre / CARPETA_SOLICITUDES / "002 VTAS AGOSTO 26"
        mes.mkdir(parents=True)
        factory(mes / f"{nombre.lower()}.pdf")


def _xlsx_bajo(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*.xlsx")
        if p.name.startswith(("emision_", "reporte_"))
    ]


class TestProcessRepoConsolidado(unittest.TestCase):
    def test_no_escribe_excel_ni_reporte_en_carpetas_de_asesor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            out = Path(tmp) / "out"
            root.mkdir()
            out.mkdir()
            _mini_repo(root)
            process_repo(root, Periodo(anio=2026, mes=8), output_dir=out)
            self.assertEqual(_xlsx_bajo(root), [])

    def test_un_solo_reporte_en_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            out = Path(tmp) / "out"
            root.mkdir()
            out.mkdir()
            _mini_repo(root)
            process_repo(root, Periodo(anio=2026, mes=8), output_dir=out)
            reportes = list(out.glob("reporte_*.xlsx"))
            self.assertEqual(len(reportes), 1)
            self.assertEqual(reportes[0].name, "reporte_08_2026.xlsx")
            self.assertEqual(list(out.glob("emision_*.xlsx")), [])

    def test_un_excel_y_reporte_con_solicitudes_editables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            out = Path(tmp) / "out"
            root.mkdir()
            out.mkdir()
            _mini_repo(root, factory=lambda p: _pdf_solicitud(
                p, nombre="PEREZ JUAN", dni="20123456" if "ana" in p.name else "30999888"
            ))
            process_repo(root, Periodo(anio=2026, mes=8), output_dir=out)

            self.assertEqual(_xlsx_bajo(root), [])
            emisiones = list(out.glob("emision_*.xlsx"))
            reportes = list(out.glob("reporte_*.xlsx"))
            self.assertEqual([p.name for p in emisiones], ["emision_08_2026.xlsx"])
            self.assertEqual([p.name for p in reportes], ["reporte_08_2026.xlsx"])

            wb = openpyxl.load_workbook(emisiones[0], data_only=True)
            headers = [c.value for c in next(wb["ExcelModelo"].iter_rows(min_row=1, max_row=1))]
            self.assertNotIn("Asesor", headers)
            self.assertNotIn("Ruta", headers)
            self.assertGreaterEqual(wb["Incompletos"].max_row, 2)

            rep = openpyxl.load_workbook(reportes[0], data_only=True)
            por_pdf = [c.value for c in next(rep["Por PDF"].iter_rows(min_row=1, max_row=1))]
            self.assertEqual(por_pdf[-2:], ["Asesor", "Ruta"])
            asesores = {
                row[por_pdf.index("Asesor")].value
                for row in rep["Por PDF"].iter_rows(min_row=2)
                if row[0].value
            }
            self.assertTrue({"ANA", "BOB"} <= asesores)

    def test_duplicado_ambiguo_no_entra_a_excel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            out = Path(tmp) / "out"
            ana = root / "ANA" / CARPETA_SOLICITUDES / "002 VTAS AGOSTO 26"
            bob = root / "BOB" / CARPETA_SOLICITUDES / "002 VTAS AGOSTO 26"
            ana.mkdir(parents=True)
            bob.mkdir(parents=True)
            _pdf_solicitud(ana / "v1.pdf", nombre="PEREZ JUAN", dni="20123456")
            _pdf_solicitud(ana / "v2.pdf", nombre="PEREZ JUAN", dni="20123456")
            _pdf_solicitud(bob / "bob.pdf", nombre="GOMEZ ANA", dni="30999888")

            process_repo(root, Periodo(anio=2026, mes=8), output_dir=out)

            emision = out / "emision_08_2026.xlsx"
            self.assertTrue(emision.exists())
            wb = openpyxl.load_workbook(emision, data_only=True)
            self.assertEqual(wb["ExcelModelo"].max_row, 1)
            textos_inc = " ".join(
                str(c.value or "")
                for row in wb["Incompletos"].iter_rows(min_row=2)
                for c in row
            )
            self.assertIn("30999888", textos_inc)
            self.assertNotIn("20123456", textos_inc)
            textos_dup = " ".join(
                str(c.value or "")
                for row in wb["Duplicados"].iter_rows(min_row=2)
                for c in row
            )
            self.assertIn("20123456", textos_dup)
            self.assertNotIn("30999888", textos_dup)

            rep = openpyxl.load_workbook(out / "reporte_08_2026.xlsx", data_only=True)
            estados = [row[1].value for row in rep["Por PDF"].iter_rows(min_row=2)]
            self.assertGreaterEqual(estados.count("Duplicado ambiguo"), 2)
            resumen = {row[0].value: row[1].value for row in rep["Resumen"].iter_rows(min_row=2)}
            self.assertEqual(resumen.get("Veredicto"), "CON HALLAZGOS")
            self.assertEqual(resumen.get("PDFs duplicados ambiguos (hoja Duplicados)"), 2)


class TestReporteTrazabilidad(unittest.TestCase):
    def test_por_pdf_muestra_asesor_y_ruta(self) -> None:
        solicitud = SolicitudSalud(
            archivo_origen="ana.pdf",
            asesor_origen="ANA",
            ruta_origen=r"C:\repo\ANA\SOLICITUDES ESCANEADAS\002 VTAS AGOSTO 26",
            apellido_nombre_tomador="PEREZ JUAN",
            nro_documento_tomador=20123456,
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
            asegurados=[Asegurado(nombre="PEREZ JUAN", nro_documento=20123456, relacion="Titular")],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reporte.xlsx"
            generar_reporte([solicitud], [], output_path=path)
            wb = openpyxl.load_workbook(path, data_only=True)
            headers = [c.value for c in next(wb["Por PDF"].iter_rows(min_row=1, max_row=1))]
            self.assertIn("Asesor", headers)
            self.assertIn("Ruta", headers)
            fila = next(wb["Por PDF"].iter_rows(min_row=2, max_row=2))
            self.assertEqual(fila[headers.index("Asesor")].value, "ANA")
            self.assertIn("ANA", fila[headers.index("Ruta")].value or "")


if __name__ == "__main__":
    unittest.main()
