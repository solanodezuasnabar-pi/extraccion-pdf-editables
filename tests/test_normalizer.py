"""Vigencia: fechas del PDF, o día 1 del mes siguiente a la carpeta de ventas."""

from __future__ import annotations

from datetime import datetime
import unittest

from src.models import FormaPago, SolicitudSalud
from src.normalizer import aplicar_pago_o_efectivo, normalizar
from src.rules import solicitud_a_filas
from src.settings import cargar_parametria


class TestNormalizerVigencia(unittest.TestCase):
    def test_noviembre_sin_fechas_arranca_el_primero_de_diciembre(self) -> None:
        s = SolicitudSalud(apellido_nombre_tomador="PEREZ JUAN")
        normalizar(s, periodo_ref=datetime(2026, 11, 1))
        self.assertEqual(s.inicio_vigencia, datetime(2026, 12, 1))
        self.assertEqual(s.fin_vigencia, datetime(2027, 12, 1))

    def test_diciembre_pasa_a_enero_del_anio_siguiente(self) -> None:
        s = SolicitudSalud(apellido_nombre_tomador="PEREZ JUAN")
        normalizar(s, periodo_ref=datetime(2026, 12, 15))
        self.assertEqual(s.inicio_vigencia, datetime(2027, 1, 1))
        self.assertEqual(s.fin_vigencia, datetime(2028, 1, 1))

    def test_firma_no_pisa_el_mes_de_la_carpeta(self) -> None:
        s = SolicitudSalud(
            apellido_nombre_tomador="PEREZ JUAN",
            fecha_firma=datetime(2026, 7, 15),
        )
        normalizar(s, periodo_ref=datetime(2026, 11, 1))
        self.assertEqual(s.inicio_vigencia, datetime(2026, 12, 1))
        self.assertEqual(s.fin_vigencia, datetime(2027, 12, 1))

    def test_sin_periodo_no_inventa_aunque_haya_firma(self) -> None:
        s = SolicitudSalud(
            apellido_nombre_tomador="PEREZ JUAN",
            fecha_firma=datetime(2026, 7, 15),
        )
        normalizar(s)
        self.assertIsNone(s.inicio_vigencia)
        self.assertIsNone(s.fin_vigencia)

    def test_fechas_del_pdf_se_conservan(self) -> None:
        s = SolicitudSalud(
            apellido_nombre_tomador="PEREZ JUAN",
            inicio_vigencia=datetime(2026, 3, 10),
            fin_vigencia=datetime(2027, 3, 10),
            fecha_firma=datetime(2026, 7, 15),
        )
        normalizar(s, periodo_ref=datetime(2026, 11, 1))
        self.assertEqual(s.inicio_vigencia, datetime(2026, 3, 10))
        self.assertEqual(s.fin_vigencia, datetime(2027, 3, 10))

    def test_inicio_sin_fin_completa_un_anio(self) -> None:
        s = SolicitudSalud(
            apellido_nombre_tomador="PEREZ JUAN",
            inicio_vigencia=datetime(2026, 9, 1),
        )
        normalizar(s)
        self.assertEqual(s.fin_vigencia, datetime(2027, 9, 1))


class TestNormalizerPago(unittest.TestCase):
    def test_infiere_cbu_por_longitud(self) -> None:
        s = SolicitudSalud(
            apellido_nombre_tomador="PEREZ JUAN",
            cbu="1234567890123456789012",
        )
        normalizar(s)
        self.assertEqual(s.forma_pago, FormaPago.CBU)

    def test_infiere_tarjeta_por_longitud(self) -> None:
        s = SolicitudSalud(
            apellido_nombre_tomador="PEREZ JUAN",
            tarjeta_nombre="Visa",
            tarjeta_numero="4111111111111111",
        )
        normalizar(s)
        self.assertEqual(s.forma_pago, FormaPago.TARJETA)

    def test_cbu_corto_pasa_a_efectivo(self) -> None:
        s = SolicitudSalud(
            apellido_nombre_tomador="PEREZ JUAN",
            forma_pago=FormaPago.CBU,
            cbu="123456789012345678901",
        )
        normalizar(s)
        self.assertEqual(s.forma_pago, FormaPago.EFECTIVO)
        self.assertEqual(s.cbu, "")

    def test_tarjeta_corta_pasa_a_efectivo(self) -> None:
        s = SolicitudSalud(
            apellido_nombre_tomador="PEREZ JUAN",
            forma_pago=FormaPago.TARJETA,
            tarjeta_nombre="Visa",
            tarjeta_numero="4111",
        )
        normalizar(s)
        self.assertEqual(s.forma_pago, FormaPago.EFECTIVO)
        self.assertEqual(s.tarjeta_numero, "")
        self.assertEqual(s.tarjeta_nombre, "")

    def test_tarjeta_marca_desconocida_pasa_a_efectivo(self) -> None:
        s = SolicitudSalud(
            apellido_nombre_tomador="PEREZ JUAN",
            forma_pago=FormaPago.TARJETA,
            tarjeta_nombre="Tarjeta Inventada XYZ",
            tarjeta_numero="4111111111111111",
        )
        normalizar(s)
        self.assertEqual(s.forma_pago, FormaPago.EFECTIVO)

    def test_desconocido_sin_numeros_pasa_a_efectivo(self) -> None:
        s = SolicitudSalud(apellido_nombre_tomador="PEREZ JUAN")
        normalizar(s)
        self.assertEqual(s.forma_pago, FormaPago.EFECTIVO)

    def test_excel_titular_efectivo_si_cbu_invalido(self) -> None:
        parametria = cargar_parametria()
        s = SolicitudSalud(
            apellido_nombre_tomador="PEREZ JUAN",
            nro_documento_tomador=20123456,
            forma_pago=FormaPago.CBU,
            cbu="123",
            plan="5",
            modulo=1,
        )
        aplicar_pago_o_efectivo(s, parametria)
        filas = solicitud_a_filas(s, parametria)
        titular = next(f for f in filas if f["TIPO_RELACION"] == "Titular")
        self.assertEqual(titular["EFECTIVO"], 1)
        self.assertIsNone(titular["CBU"])
        self.assertIsNone(titular["NRO_TARJETA"])


if __name__ == "__main__":
    unittest.main()
