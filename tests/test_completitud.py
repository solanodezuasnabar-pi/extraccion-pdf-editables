"""Lista de completitud 07/09 (spec 2026-09-10)."""

from __future__ import annotations

from datetime import datetime
import unittest

from src.completitud import aplicar_blancos_completitud, evaluar_completitud
from src.models import Asegurado, FormaPago, SolicitudSalud
from src.settings import cargar_parametria


def _solicitud_completa(**overrides) -> SolicitudSalud:
    s = SolicitudSalud(
        apellido_nombre_tomador="PEREZ JUAN",
        nro_documento_tomador=20123456,
        calle="SAN MARTIN",
        nro="100",
        codigo_postal=5000,
        plan="5",
        modulo=1,
        forma_pago=FormaPago.EFECTIVO,
        productor="123",
        organizador="456",
        inicio_vigencia=datetime(2026, 8, 1),
        fin_vigencia=datetime(2027, 8, 1),
        asegurados=[
            Asegurado(nombre="PEREZ JUAN", nro_documento=20123456, relacion="Titular"),
        ],
    )
    for key, value in overrides.items():
        setattr(s, key, value)
    return s


class TestCompletitud0709(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parametria = cargar_parametria()

    def _eval(self, solicitud: SolicitudSalud):
        return evaluar_completitud(solicitud, self.parametria)

    def test_factory_completa(self) -> None:
        r = self._eval(_solicitud_completa())
        self.assertTrue(r.completa)
        self.assertEqual(r.faltantes, [])

    def test_asesores_sin_plan_es_incompleta(self) -> None:
        r = self._eval(_solicitud_completa(plan=None, variante_formulario="asesores"))
        self.assertFalse(r.completa)
        self.assertIn("plan", r.faltantes)
        self.assertTrue(r.blank_plan)

    def test_plan_fuera_de_parametria_es_incompleto(self) -> None:
        r = self._eval(_solicitud_completa(plan="7"))
        self.assertFalse(r.completa)
        self.assertIn("plan", r.faltantes)

    def test_tarjeta_valida_visa_es_completa(self) -> None:
        r = self._eval(
            _solicitud_completa(
                forma_pago=FormaPago.TARJETA,
                tarjeta_nombre="Visa",
                tarjeta_numero="4111111111111111",
            )
        )
        self.assertTrue(r.completa)

    def test_tarjeta_corta_no_manda_a_incompletos(self) -> None:
        r = self._eval(
            _solicitud_completa(
                forma_pago=FormaPago.TARJETA,
                tarjeta_nombre="Visa",
                tarjeta_numero="4111",
            )
        )
        self.assertTrue(r.completa)
        self.assertNotIn("nro_tarjeta", r.faltantes)

    def test_tarjeta_sin_codigo_reconocido_no_manda_a_incompletos(self) -> None:
        r = self._eval(
            _solicitud_completa(
                forma_pago=FormaPago.TARJETA,
                tarjeta_nombre="Tarjeta Inventada XYZ",
                tarjeta_numero="4111111111111111",
            )
        )
        self.assertTrue(r.completa)
        self.assertNotIn("codigo_tarjeta", r.faltantes)

    def test_cbu_corto_no_manda_a_incompletos(self) -> None:
        r = self._eval(
            _solicitud_completa(
                forma_pago=FormaPago.CBU,
                cbu="123456789012345678901",
            )
        )
        self.assertTrue(r.completa)
        self.assertNotIn("cbu", r.faltantes)

    def test_cbu_22_digitos_es_completo(self) -> None:
        r = self._eval(
            _solicitud_completa(
                forma_pago=FormaPago.CBU,
                cbu="1234567890123456789012",
            )
        )
        self.assertTrue(r.completa)

    def test_productor_vacio_sigue_incompleto(self) -> None:
        r = self._eval(_solicitud_completa(productor=""))
        self.assertFalse(r.completa)
        self.assertIn("productor", r.faltantes)

    def test_email_vacio_no_integra_completitud(self) -> None:
        r = self._eval(_solicitud_completa(email=""))
        self.assertTrue(r.completa)

    def test_incompleto_por_plan_blanquea_opcion_cobertura(self) -> None:
        r = self._eval(_solicitud_completa(plan=None))
        filas = aplicar_blancos_completitud(
            [{"OPCION_COBERTURA": 28275, "TIPO_RELACION": "Titular"}],
            r,
        )
        self.assertIsNone(filas[0]["OPCION_COBERTURA"])
        self.assertIn("OPCION_COBERTURA", filas[0]["_celdas_faltantes"])


if __name__ == "__main__":
    unittest.main()
