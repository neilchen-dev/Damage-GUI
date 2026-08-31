"""Phase 7 deployment configuration and process-model contracts."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.runtime.paths import app_base_dir
from damage_gui.webapp.settings import (
    MAX_RETENTION_DAYS,
    WebRuntimeSettings,
    parse_port,
    parse_retention_days,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DeploymentConfigTests(unittest.TestCase):
    def test_environment_settings_resolve_container_paths(self) -> None:
        environment = {
            "DAMAGE_GUI_HOME": "G:/damagelab-runtime",
            "DAMAGE_GUI_DB": "G:/damagelab-runtime/db/trace.sqlite",
            "DAMAGE_GUI_MODEL_DIR": "G:/damagelab-runtime/models",
            "DAMAGE_GUI_RESULT_DIR": "G:/damagelab-runtime/results",
            "DAMAGE_GUI_DEFAULT_MODEL": "model-F",
            "DAMAGE_GUI_RESULT_RETENTION_DAYS": "30",
            "DAMAGE_GUI_HOST": "127.0.0.1",
            "DAMAGE_GUI_PORT": "8123",
        }
        with patch.dict(os.environ, environment, clear=False):
            settings = WebRuntimeSettings.from_env()
            self.assertEqual(settings.db_path, Path(environment["DAMAGE_GUI_DB"]).resolve())
            self.assertEqual(
                settings.model_dir, Path(environment["DAMAGE_GUI_MODEL_DIR"]).resolve()
            )
            self.assertEqual(
                settings.result_dir, Path(environment["DAMAGE_GUI_RESULT_DIR"]).resolve()
            )
            self.assertEqual(settings.default_model_id, "model-F")
            self.assertEqual(settings.retention_days, 30)
            self.assertEqual(settings.host, "127.0.0.1")
            self.assertEqual(settings.port, 8123)

    def test_legacy_web_environment_names_remain_supported(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DAMAGE_GUI_HOME": "G:/damagelab-runtime",
                "DAMAGE_GUI_RESULT_DIR": "",
                "DAMAGE_GUI_WEB_RESULT_DIR": "G:/legacy-results",
                "DAMAGE_GUI_PORT": "",
                "DAMAGE_GUI_WEB_PORT": "8124",
            },
            clear=False,
        ):
            settings = WebRuntimeSettings.from_env()
            self.assertEqual(settings.result_dir, Path("G:/legacy-results").resolve())
            self.assertEqual(settings.port, 8124)

    def test_runtime_path_and_value_validation(self) -> None:
        with patch.dict(os.environ, {"DAMAGE_GUI_HOME": "G:/damagelab-home"}, clear=False):
            self.assertEqual(app_base_dir(), Path("G:/damagelab-home").resolve())
        self.assertEqual(parse_port(None), 8000)
        self.assertEqual(parse_retention_days(None), 7)
        with self.assertRaises(ValueError):
            parse_port("70000")
        with self.assertRaises(ValueError):
            parse_retention_days(str(MAX_RETENTION_DAYS + 1))

    def test_container_and_proxy_contracts_are_explicit(self) -> None:
        dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
        compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        nginx = (
            PROJECT_ROOT / "deploy" / "nginx" / "default.conf.template"
        ).read_text(encoding="utf-8")
        entrypoint = (PROJECT_ROOT / "deploy" / "entrypoint.sh").read_text(encoding="utf-8")

        self.assertIn("MPLBACKEND=Agg", dockerfile)
        self.assertIn("groupadd --system --gid 10001 damagelab", dockerfile)
        self.assertIn("damagelab-drop-privileges", entrypoint)
        self.assertIn("--workers 1", dockerfile + entrypoint)
        self.assertIn('"80:80"', compose)
        self.assertIn('"443:443"', compose)
        self.assertNotIn('"8000:8000"', compose)
        self.assertIn("database:/var/lib/damagelab/db", compose)
        self.assertIn("models:/var/lib/damagelab/models:ro", compose)
        self.assertIn("results:/var/lib/damagelab/results", compose)
        self.assertIn("client_max_body_size 64k", nginx)
        self.assertIn("Strict-Transport-Security", nginx)
        self.assertIn("proxy_pass http://damagelab_app", nginx)
        self.assertIn("NGINX_ENVSUBST_FILTER", compose)


if __name__ == "__main__":
    unittest.main()
