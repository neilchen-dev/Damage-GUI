"""发布元数据一致性测试。"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from damage_gui import __version__


class ProjectMetadataTests(unittest.TestCase):
    def test_versions_are_consistent(self) -> None:
        project_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        project_match = re.search(r'^version = "([^"\r\n]+)"', project_text, re.MULTILINE)
        self.assertIsNotNone(project_match)
        self.assertEqual(project_match.group(1), __version__)

    def test_desktop_entry_points_and_resources_use_qt(self) -> None:
        project_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        desktop_text = (ROOT / "src" / "damage_gui" / "desktop.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('damage-gui = "damage_gui.desktop:main"', project_text)
        self.assertIn('damage-gui-qt = "damage_gui.qt.app:main"', project_text)
        self.assertIn("from damage_gui.qt.app import main", desktop_text)
        self.assertIn('"qt/assets/*.png"', project_text)
        self.assertIn('"qt/assets/*.ico"', project_text)
        self.assertFalse((ROOT / "src" / "damage_gui" / "gui").exists())

    def test_declared_license_file_exists(self) -> None:
        self.assertTrue((ROOT / "LICENSE").is_file())


if __name__ == "__main__":
    unittest.main()
