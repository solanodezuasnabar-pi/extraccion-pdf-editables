"""Token Graph: store Windows con timeout (subprocess mockeado)."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from src.graph_auth import _PS_TIMEOUT_S, acquire_token
from src.graph_config import GraphConfig
from src.graph_http import GraphError

_CFG = GraphConfig(
    tenant_id="t",
    client_id="c",
    thumbprint="AB12",
    cert_path="",
)


class TestTokenStoreWindows(unittest.TestCase):
    @patch("src.graph_auth._PS_TOKEN")
    @patch("src.graph_auth.subprocess.run")
    def test_timeout_lanza_graph_error(self, run, ps_token) -> None:
        ps_token.is_file.return_value = True
        run.side_effect = subprocess.TimeoutExpired(cmd="powershell", timeout=_PS_TIMEOUT_S)
        with self.assertRaises(GraphError) as ctx:
            acquire_token(_CFG)
        self.assertIn("timeout 60s", str(ctx.exception))
        self.assertEqual(run.call_args.kwargs["timeout"], 60)

    @patch("src.graph_auth._PS_TOKEN")
    @patch("src.graph_auth.subprocess.run")
    def test_ok_devuelve_token(self, run, ps_token) -> None:
        ps_token.is_file.return_value = True
        run.return_value = subprocess.CompletedProcess(
            args=["powershell"], returncode=0, stdout="  tok123  \n", stderr=""
        )
        self.assertEqual(acquire_token(_CFG), "tok123")

    @patch("src.graph_auth._PS_TOKEN")
    @patch("src.graph_auth.subprocess.run")
    def test_rc_1_lanza_graph_error(self, run, ps_token) -> None:
        ps_token.is_file.return_value = True
        run.return_value = subprocess.CompletedProcess(
            args=["powershell"], returncode=1, stdout="", stderr="cert not found"
        )
        with self.assertRaises(GraphError) as ctx:
            acquire_token(_CFG)
        self.assertIn("cert not found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
