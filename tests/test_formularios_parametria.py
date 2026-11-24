"""Parametría de módulos / variantes PDF (diseño 2026-07-29)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.extractors.n1_formfields import WidgetInfo, _detectar_modulo, _detectar_plan
from src.settings import FormulariosConfig, cargar_parametria, default_formularios


class TestFormulariosParametria(unittest.TestCase):
    def test_parametria_repo_incluye_formularios(self) -> None:
        p = cargar_parametria()
        self.assertIn("A", p.formularios.modulo_excel)
        self.assertEqual(p.formularios.modulo_excel["A"], 1)
        self.assertEqual(p.formularios.modulo_excel["B"], 2)
        self.assertIn("plan4", p.formularios.variantes)
        self.assertIn("asesores", p.formularios.variantes)

    def test_default_formularios_sin_seccion_yaml(self) -> None:
        yaml_min = """
pais_origen: 1
grupo_estadistico: 2301
opcion_cobertura_por_plan:
  "4": 18484
  "5": 28275
  "6": 33403
  "100": 56128
tarjetas: {}
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "parametria.yaml"
            path.write_text(yaml_min, encoding="utf-8")
            p = cargar_parametria(path)
            self.assertEqual(p.formularios.modulo_excel, default_formularios().modulo_excel)

    def test_modulo_plan4_sin_seleccion_asume_a(self) -> None:
        """Plantilla Operatoria especial: A/PLAN 4 van impresos, no hay widget B."""
        cfg = default_formularios()
        widgets = [
            WidgetInfo(nombre="APORTE", valor="Off", x0=10, y0=10, on_state="On"),
            WidgetInfo(nombre="DOCM", valor="Off", x0=20, y0=10, on_state="On"),
            WidgetInfo(nombre="APORTE1", valor="Off", x0=10, y0=20, on_state="On"),
            WidgetInfo(nombre="DOCM1", valor="Off", x0=20, y0=20, on_state="On"),
        ]
        self.assertEqual(_detectar_modulo(widgets, "plan4", formularios=cfg), 1)

    def test_modulo_plan4_widgets_vacios_asume_a(self) -> None:
        cfg = default_formularios()
        widgets = [
            WidgetInfo(nombre="APORTE", valor="", x0=10, y0=10),
            WidgetInfo(nombre="DOCM", valor="", x0=20, y0=10),
        ]
        self.assertEqual(_detectar_modulo(widgets, "plan4", formularios=cfg), 1)

    def test_modulo_asesores_sin_seleccion_es_none(self) -> None:
        cfg = default_formularios()
        widgets = [
            WidgetInfo(nombre="COBERTURA", valor="Off", x0=10, y0=10, on_state="On"),
            WidgetInfo(nombre="COBERTURA", valor="Off", x0=10, y0=20, on_state="On1"),
        ]
        self.assertIsNone(_detectar_modulo(widgets, "asesores", formularios=cfg))

    def test_modulo_plan4_b_marcado(self) -> None:
        cfg = default_formularios()
        widgets = [
            WidgetInfo(nombre="APORTE", valor="Off", x0=10, y0=10, on_state="On"),
            WidgetInfo(nombre="APORTE1", valor="On", x0=10, y0=20, on_state="On"),
        ]
        self.assertEqual(_detectar_modulo(widgets, "plan4", formularios=cfg), 2)

    def test_modulo_asesores_usa_export_configurado(self) -> None:
        cfg = default_formularios()
        widgets = [
            WidgetInfo(nombre="COBERTURA", valor="On1", x0=10, y0=10, on_state="On1"),
        ]
        self.assertEqual(_detectar_modulo(widgets, "asesores", formularios=cfg), 2)

    def test_modulo_excel_configurable(self) -> None:
        cfg = FormulariosConfig(
            modulo_excel={"A": 1, "B": 9},
            variantes=default_formularios().variantes,
        )
        widgets = [
            WidgetInfo(nombre="COBERTURA", valor="On1", x0=10, y0=10, on_state="On1"),
        ]
        self.assertEqual(_detectar_modulo(widgets, "asesores", formularios=cfg), 9)

    def test_plan_asesores_usa_export_configurado(self) -> None:
        cfg = default_formularios()
        widgets = [
            WidgetInfo(nombre="TIPO PLAN", valor="On2", x0=10, y0=30, on_state="On2"),
        ]
        self.assertEqual(_detectar_plan(widgets, "asesores", formularios=cfg), "100")

    def test_yaml_on_no_se_come_como_bool(self) -> None:
        """Claves On/On1 deben quedar como strings de export PDF."""
        p = cargar_parametria()
        plan_ex = p.formularios.variantes["asesores"].plan.por_export
        mod_ex = p.formularios.variantes["asesores"].modulo.por_export
        self.assertEqual(plan_ex.get("On"), "5")
        self.assertEqual(plan_ex.get("On1"), "6")
        self.assertEqual(mod_ex.get("On"), "A")
        self.assertNotIn("True", plan_ex)
        widgets = [WidgetInfo(nombre="TIPO PLAN", valor="On", x0=10, y0=10, on_state="On")]
        self.assertEqual(_detectar_plan(widgets, "asesores", formularios=p.formularios), "5")
        widgets_m = [WidgetInfo(nombre="COBERTURA", valor="On", x0=10, y0=10, on_state="On")]
        self.assertEqual(_detectar_modulo(widgets_m, "asesores", formularios=p.formularios), 1)


_EDITABLES_FEB = (
    Path(__file__).resolve().parents[1] / "output" / "editables_02_2026"
)


def _pdf_editable(nombre: str) -> Path | None:
    if not _EDITABLES_FEB.is_dir():
        return None
    hits = list(_EDITABLES_FEB.rglob(nombre))
    return hits[0] if hits else None


class TestModuloPdfsFebrero(unittest.TestCase):
    """Regresión sobre el set descargado; se salta si no está en disco."""

    def test_titular_a_plan4_modulo_a(self) -> None:
        from src.normalizer import extraer_pdf

        pdf = _pdf_editable("TITULAR A SALUD PLAN4.pdf")
        if pdf is None:
            self.skipTest("no está output/editables_02_2026")
        solicitud = extraer_pdf(pdf)
        self.assertIsNotNone(solicitud)
        self.assertEqual(solicitud.modulo, 1)

    def test_titular_b_plan100_modulo_b(self) -> None:
        from src.normalizer import extraer_pdf

        pdf = _pdf_editable("TITULAR B Plan100 CON RENTA diaria.pdf")
        if pdf is None:
            self.skipTest("no está output/editables_02_2026")
        solicitud = extraer_pdf(pdf)
        self.assertIsNotNone(solicitud)
        self.assertEqual(solicitud.modulo, 2)


if __name__ == "__main__":
    unittest.main()
