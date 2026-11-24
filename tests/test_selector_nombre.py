"""Adjuntos por nombre: no se abren y van a ignorar."""

from __future__ import annotations

import unittest
from pathlib import Path

from src.selector import seleccionar_pdf

_IGNORAR = (
    "cbutomador-perezjuan.pdf",
    "cbu Gomez.pdf",
    "MEDIO DE PAGO LOPEZ.pdf",
    "medio_de_pago.pdf",
    "alias bancario.pdf",
    "constancia cbu.pdf",
    "CONFORMIDAD ANA PEREZ.pdf",
    "DNI PEREZ ANA.pdf",
)


class TestNombreAdjunto(unittest.TestCase):
    def test_datos_bancarios_y_conformidad_se_ignoran(self) -> None:
        for nombre in _IGNORAR:
            sel = seleccionar_pdf(Path(nombre))
            self.assertEqual(sel.decision, "ignorar", nombre)
            self.assertEqual(sel.categoria, "adjunto", nombre)

    def test_solicitud_no_se_excluye_por_nombre(self) -> None:
        from src.selector import _nombre_excluido

        self.assertFalse(_nombre_excluido("SOLICITUD PEREZ-GOMEZ.pdf"))
        self.assertFalse(_nombre_excluido("Propuesta Plan Familia LOPEZ.pdf"))


if __name__ == "__main__":
    unittest.main()
