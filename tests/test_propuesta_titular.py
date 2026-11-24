"""Titular primero y número de propuesta (spec 2026-09-14)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

import openpyxl

from src.completitud import ResultadoCompletitud
from src.excel_builder import asignar_propuestas, generar_excel, numero_propuesta
from src.models import Asegurado, FormaPago, SolicitudSalud
from src.rules import solicitud_a_filas
from src.settings import cargar_parametria
from src.validation_builder import COLUMNAS_ANEXO_33, _chequear_columna, filas_checklist_emision


class TestNumeroPropuesta(unittest.TestCase):
    def test_fila_2_equivale_a_fila_a1_mas_24(self) -> None:
        self.assertEqual(numero_propuesta(date(2026, 9, 14), 2), "VAVI202609140025")

    def test_fila_5_usa_su_propia_fila(self) -> None:
        self.assertEqual(numero_propuesta(date(2026, 9, 14), 5), "VAVI202609140028")


class TestAsignarPropuestas(unittest.TestCase):
    def test_solo_fila_titular_recibe_numero(self) -> None:
        filas = [
            {"TIPO_RELACION": "Titular", "PROPUESTA": None},
            {"TIPO_RELACION": "Asegurado Titular", "PROPUESTA": None},
            {"TIPO_RELACION": "Asegurado Familiar", "PROPUESTA": None},
            {"TIPO_RELACION": "Titular", "PROPUESTA": None},
        ]
        out = asignar_propuestas(filas, fecha=date(2026, 9, 14), primera_fila_datos=2)
        self.assertEqual(out[0]["PROPUESTA"], "VAVI202609140025")
        self.assertIsNone(out[1]["PROPUESTA"])
        self.assertIsNone(out[2]["PROPUESTA"])
        self.assertEqual(out[3]["PROPUESTA"], "VAVI202609140028")

    def test_no_copia_formula(self) -> None:
        out = asignar_propuestas(
            [{"TIPO_RELACION": "Titular", "PROPUESTA": None}],
            fecha=date(2026, 9, 14),
        )
        self.assertIsInstance(out[0]["PROPUESTA"], str)
        self.assertFalse(str(out[0]["PROPUESTA"]).startswith("="))


def _solicitud_familiar_desordenada() -> SolicitudSalud:
    return SolicitudSalud(
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
        asegurados=[
            Asegurado(nombre="PEREZ LUCIA", nro_documento=30111111, relacion="Hijo"),
            Asegurado(nombre="PEREZ JUAN", nro_documento=20123456, relacion="Titular"),
            Asegurado(nombre="GOMEZ ANA", nro_documento=25999888, relacion="Conyuge"),
        ],
    )


class TestOrdenTitularPrimero(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parametria = cargar_parametria()

    def test_asegurables_desordenados_titular_queda_segundo(self) -> None:
        filas = solicitud_a_filas(_solicitud_familiar_desordenada(), self.parametria)
        relaciones = [f["TIPO_RELACION"] for f in filas]
        self.assertEqual(
            relaciones,
            ["Titular", "Asegurado Titular", "Asegurado Familiar", "Asegurado Familiar"],
        )
        self.assertEqual(filas[1]["APELLIDO_NOMBRE_TITULAR"], "PEREZ JUAN")
        self.assertEqual(filas[2]["APELLIDO_NOMBRE_TITULAR"], "PEREZ LUCIA")
        self.assertEqual(filas[3]["APELLIDO_NOMBRE_TITULAR"], "GOMEZ ANA")

    def test_propuesta_sigue_vacia_en_rules(self) -> None:
        filas = solicitud_a_filas(_solicitud_familiar_desordenada(), self.parametria)
        self.assertTrue(all(f.get("PROPUESTA") is None for f in filas))


def _solicitud_ok(*, dni: int, nombre: str, extra: list[Asegurado] | None = None) -> SolicitudSalud:
    asegurados = [Asegurado(nombre=nombre, nro_documento=dni, relacion="Titular")]
    if extra:
        asegurados.extend(extra)
    return SolicitudSalud(
        apellido_nombre_tomador=nombre,
        nro_documento_tomador=dni,
        calle="SAN MARTIN",
        nro="1",
        codigo_postal=5000,
        localidad="CORDOBA",
        email="a@b.com",
        plan="5",
        modulo=1,
        forma_pago=FormaPago.EFECTIVO,
        productor="1",
        organizador="2",
        inicio_vigencia=datetime(2026, 8, 1),
        fin_vigencia=datetime(2027, 8, 1),
        asegurados=asegurados,
    )


def _columna(ws, header: str):
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = headers.index(header)
    return idx, [row[idx] for row in ws.iter_rows(min_row=2) if any(c.value for c in row)]


def _titulares(ws) -> list:
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx_tipo = headers.index("TIPO_RELACION")
    idx_nom = headers.index("APELLIDO_NOMBRE_TITULAR")
    return [
        row[idx_nom].value
        for row in ws.iter_rows(min_row=2)
        if any(c.value for c in row) and row[idx_tipo].value == "Titular"
    ]


class TestExcelPropuesta(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parametria = cargar_parametria()

    def test_dos_familias_numero_solo_en_titular(self) -> None:
        s1 = _solicitud_ok(
            dni=20123456,
            nombre="PEREZ JUAN",
            extra=[Asegurado(nombre="PEREZ LUCIA", nro_documento=30111111, relacion="Hijo")],
        )
        s2 = _solicitud_ok(dni=30999888, nombre="GOMEZ ANA")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "emision.xlsx"
            generar_excel(
                [s1, s2],
                self.parametria,
                output_path=path,
                fecha_propuesta=date(2026, 9, 14),
            )
            wb = openpyxl.load_workbook(path)
            ws = wb["ExcelModelo"]
            _idx, celdas = _columna(ws, "PROPUESTA")
            rel_idx, _ = _columna(ws, "TIPO_RELACION")
            relaciones = [ws.cell(row=c.row, column=rel_idx + 1).value for c in celdas]
            valores = [c.value for c in celdas]
            self.assertEqual(relaciones[0], "Titular")
            self.assertEqual(valores[0], "VAVI202609140025")
            self.assertEqual(celdas[0].number_format, "@")
            self.assertNotEqual(celdas[0].data_type, "f")
            for rel, val in zip(relaciones, valores):
                if rel == "Titular":
                    self.assertTrue(str(val).startswith("VAVI20260914"))
                else:
                    self.assertIn(val, (None, ""))
            self.assertEqual(valores[relaciones.index("Titular", 1)], "VAVI202609140028")
            wb.close()

    def test_incompletos_tambien_numera_desde_fila_2(self) -> None:
        s = _solicitud_ok(dni=20123456, nombre="PEREZ JUAN")
        resultado = ResultadoCompletitud(faltantes=["email"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "emision.xlsx"
            generar_excel(
                [],
                self.parametria,
                incompletas=[(s, resultado)],
                output_path=path,
                fecha_propuesta=date(2026, 9, 14),
            )
            wb = openpyxl.load_workbook(path)
            _idx, celdas = _columna(wb["Incompletos"], "PROPUESTA")
            self.assertEqual(celdas[0].value, "VAVI202609140025")
            if len(celdas) > 1:
                self.assertIn(celdas[1].value, (None, ""))
            wb.close()

    def test_duplicados_van_a_su_hoja(self) -> None:
        a = _solicitud_ok(dni=20123456, nombre="PEREZ JUAN")
        a.archivo_origen = "version-a.pdf"
        b = _solicitud_ok(dni=20123456, nombre="PEREZ JUAN CARLOS")
        b.archivo_origen = "version-b.pdf"
        suelta = _solicitud_ok(dni=30999888, nombre="GOMEZ ANA")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "emision.xlsx"
            generar_excel(
                [suelta],
                self.parametria,
                duplicados=[a, b],
                output_path=path,
                fecha_propuesta=date(2026, 9, 14),
            )
            wb = openpyxl.load_workbook(path)
            self.assertIn("Duplicados", wb.sheetnames)
            self.assertEqual(
                _titulares(wb["Duplicados"]),
                ["PEREZ JUAN", "PEREZ JUAN CARLOS"],
            )
            self.assertEqual(_titulares(wb["ExcelModelo"]), ["GOMEZ ANA"])
            self.assertEqual(_titulares(wb["Incompletos"]), [])
            wb.close()

    def test_hoja_duplicados_existe_vacia(self) -> None:
        s = _solicitud_ok(dni=20123456, nombre="PEREZ JUAN")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "emision.xlsx"
            generar_excel([s], self.parametria, output_path=path, fecha_propuesta=date(2026, 9, 14))
            wb = openpyxl.load_workbook(path)
            self.assertIn("Duplicados", wb.sheetnames)
            self.assertEqual(_titulares(wb["Duplicados"]), [])
            wb.close()


class TestValidacionPropuesta(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parametria = cargar_parametria()
        cls.col = next(c for c in COLUMNAS_ANEXO_33 if c.columna == "PROPUESTA")

    def test_checklist_ok_en_excel_generado(self) -> None:
        s = _solicitud_ok(
            dni=20123456,
            nombre="PEREZ JUAN",
            extra=[Asegurado(nombre="PEREZ LUCIA", nro_documento=30111111, relacion="Hijo")],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "emision.xlsx"
            generar_excel([s], self.parametria, output_path=path, fecha_propuesta=date(2026, 9, 14))
            checks = filas_checklist_emision(path, self.parametria)
        prop = next(c for c in checks if c.campo == "PROPUESTA")
        self.assertEqual(prop.regla_codigo, "PROPUESTA_TIT")
        self.assertEqual(prop.estado, "OK")

    def test_familiar_con_propuesta_es_error(self) -> None:
        rows = [
            {"TIPO_RELACION": "Titular", "PROPUESTA": "VAVI202609140025", "_excel_row": 2},
            {"TIPO_RELACION": "Asegurado Familiar", "PROPUESTA": "VAVI202609140025", "_excel_row": 3},
        ]
        r = _chequear_columna(self.col, ["TIPO_RELACION", "PROPUESTA"], rows, self.parametria)
        self.assertEqual(r.estado, "ERROR")

    def test_sufijo_distinto_a_la_fila_es_error(self) -> None:
        rows = [
            {"TIPO_RELACION": "Titular", "PROPUESTA": "VAVI202609140099", "_excel_row": 2},
        ]
        r = _chequear_columna(self.col, ["TIPO_RELACION", "PROPUESTA"], rows, self.parametria)
        self.assertEqual(r.estado, "ERROR")


if __name__ == "__main__":
    unittest.main()
