"""Tests de guardado local de plantillas de correo."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.libs import config_manager, notification_manager

ROOT = Path(__file__).resolve().parents[1]


class TestNotificationSave(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / "output"
        self.config_patch = mock.patch.object(
            config_manager,
            "config",
            {
                "PROCESS_NAME": "Emision Plan Familia VAVI",
                "PROCESS_EMAIL": "robot@test.local",
                "PROCESS_SUCCESS_EMAILS": "dest@test.local",
                "PROCESS_ERROR_EMAILS": "err@test.local",
                "OUTPUTS": str(self.output),
                "MAIL_TEMPLATES": str(ROOT / "Plantillas"),
                "NOTIFY_ENABLED": False,
                "MAIL_SAVE_LOCAL": True,
                "SMTP_SERVER": "",
                "SMTP_PORT": 25,
            },
        )
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        notification_manager._run_dir = None
        self.addCleanup(setattr, notification_manager, "_run_dir", None)

    def _correos(self) -> list[Path]:
        return list((self.output / "correos").rglob("*.html"))

    def test_guarda_inicio_y_fin_sin_smtp(self) -> None:
        with mock.patch.object(
            notification_manager,
            "_send_smtp",
            side_effect=AssertionError("No debe intentar SMTP"),
        ):
            notification_manager.send_process_start()
            notification_manager.send_process_success()

        correos = self._correos()
        self.assertEqual(
            {p.name for p in correos},
            {"01_inicio.html", "02_fin_ok.html"},
        )
        asuntos = correos[0].parent / "asuntos.txt"
        self.assertTrue(asuntos.is_file())
        self.assertIn(
            "completado exitosamente",
            asuntos.read_text(encoding="utf-8"),
        )

    def test_guarda_inicio_y_error_sin_smtp(self) -> None:
        with mock.patch.object(
            notification_manager,
            "_send_smtp",
            side_effect=AssertionError("No debe intentar SMTP"),
        ):
            notification_manager.send_process_start()
            notification_manager.send_process_error(
                RuntimeError("prueba"),
                etapa="ejecución de prueba",
            )

        self.assertEqual(
            {p.name for p in self._correos()},
            {"01_inicio.html", "02_error.html"},
        )

    def test_error_de_archivo_no_se_reporta_como_falla_smtp(self) -> None:
        logger = mock.Mock()
        with (
            mock.patch.object(notification_manager, "_logger", return_value=logger),
            mock.patch.object(notification_manager.log_manager, "warning") as warning,
            mock.patch.object(notification_manager.log_manager, "warning_file") as warning_file,
        ):
            notification_manager._log_fallo_mail(
                "inicio",
                PermissionError("sin permiso de escritura"),
            )

        warning.assert_not_called()
        warning_file.assert_not_called()
        logger.exception.assert_called_once_with(
            "No se pudo enviar mail de %s",
            "inicio",
        )


if __name__ == "__main__":
    unittest.main()
