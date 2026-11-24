"""Reglas Fase 1: período por calendario, formato canónico de carpetas."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.periodo import (
    CARPETA_SOLICITUDES,
    Periodo,
    carpetas_canonicas_para_periodo,
    detectar_carpetas_mal_nombradas,
    parse_periodo_carpeta,
    parse_periodo_carpeta_laxo,
    periodo_calendario_actual,
    resolver_periodo,
    validar_repo_periodo,
)


class TestParsePeriodoCarpeta(unittest.TestCase):
    def test_acepta_formato_canonico(self) -> None:
        p = parse_periodo_carpeta("002 VTAS FEBRERO 26")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.mes, 2)
        self.assertEqual(p.anio, 2026)

    def test_acepta_prefijo_tres_digitos(self) -> None:
        p = parse_periodo_carpeta("001 VTAS ENERO 26")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.slug, "01_2026")

    def test_rechaza_variantes_no_canonicas(self) -> None:
        self.assertIsNone(parse_periodo_carpeta("VTAS FEBRERO 2026"))
        self.assertIsNone(parse_periodo_carpeta("07 julio 25"))
        self.assertIsNone(parse_periodo_carpeta("BERMULLER"))
        self.assertIsNone(parse_periodo_carpeta("2024"))

    def test_laxo_detecta_variantes_viejas(self) -> None:
        self.assertIsNotNone(parse_periodo_carpeta_laxo("VTAS FEBRERO 2026"))
        self.assertIsNotNone(parse_periodo_carpeta_laxo("07 julio 25"))


class TestPeriodoCalendario(unittest.TestCase):
    def test_periodo_calendario_actual(self) -> None:
        p = periodo_calendario_actual(date(2026, 8, 19))
        self.assertEqual(p.mes, 8)
        self.assertEqual(p.anio, 2026)

    def test_resolver_periodo_sin_flags_usa_calendario(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _crear_asesor_con_carpeta(root, "ASESOR_A", "002 VTAS AGOSTO 26")
            periodo = resolver_periodo(root, fecha_ref=date(2026, 8, 19))
            self.assertEqual(periodo.slug, "08_2026")


class TestValidacionRepo(unittest.TestCase):
    def test_error_si_ningun_asesor_tiene_carpeta_del_mes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _crear_asesor_con_carpeta(root, "ASESOR_A", "002 VTAS JULIO 26")
            with self.assertRaises(ValueError) as ctx:
                resolver_periodo(root, fecha_ref=date(2026, 8, 19))
            self.assertIn("Ningún asesor", str(ctx.exception))

    def test_asesor_sin_carpeta_no_bloquea_si_otro_tiene(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _crear_asesor_con_carpeta(root, "CON_MES", "002 VTAS AGOSTO 26")
            _crear_asesor_vacio(root, "SIN_VENTAS")
            periodo = resolver_periodo(root, fecha_ref=date(2026, 8, 19))
            self.assertEqual(periodo.slug, "08_2026")

    def test_duplicados_mismo_mes_levantan_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asesor = root / "DUP"
            escaneadas = asesor / CARPETA_SOLICITUDES
            escaneadas.mkdir(parents=True)
            for nombre in ("002 VTAS FEBRERO 26", "003 VTAS FEBRERO 26"):
                d = escaneadas / nombre
                d.mkdir()
                (d / "a.pdf").write_bytes(b"%PDF-1.4")
            periodo = Periodo(anio=2026, mes=2)
            with self.assertRaises(ValueError) as ctx:
                validar_repo_periodo(root, periodo)
            self.assertIn("duplicadas", str(ctx.exception))

    def test_carpetas_canonicas_para_periodo_devuelve_todas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asesor = _crear_asesor_con_carpeta(root, "DUP", "002 VTAS FEBRERO 26")
            extra = asesor / CARPETA_SOLICITUDES / "003 VTAS FEBRERO 26"
            extra.mkdir()
            periodo = Periodo(anio=2026, mes=2)
            matches = carpetas_canonicas_para_periodo(asesor, periodo)
            self.assertEqual(len(matches), 2)


class TestCarpetasMalNombradas(unittest.TestCase):
    def test_detecta_carpeta_laxa_como_mal_nombrada(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asesor = Path(tmp) / "ASESOR"
            escaneadas = asesor / CARPETA_SOLICITUDES
            escaneadas.mkdir(parents=True)
            (escaneadas / "VTAS MARZO 2026").mkdir()
            (escaneadas / "002 VTAS MARZO 26").mkdir()
            avisos = detectar_carpetas_mal_nombradas(asesor)
            nombres = [a.nombre_carpeta for a in avisos]
            self.assertIn("VTAS MARZO 2026", nombres)
            self.assertNotIn("002 VTAS MARZO 26", nombres)


def _crear_asesor_con_carpeta(root: Path, nombre: str, carpeta_mes: str) -> Path:
    asesor = root / nombre
    mes_dir = asesor / CARPETA_SOLICITUDES / carpeta_mes
    mes_dir.mkdir(parents=True)
    (mes_dir / "dummy.pdf").write_bytes(b"%PDF-1.4")
    return asesor


def _crear_asesor_vacio(root: Path, nombre: str) -> Path:
    asesor = root / nombre
    (asesor / CARPETA_SOLICITUDES).mkdir(parents=True)
    return asesor


if __name__ == "__main__":
    unittest.main()
