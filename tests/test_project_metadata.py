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
        release_script = (ROOT / "scripts" / "build_release.bat").read_text(
            encoding="utf-8"
        )
        project_match = re.search(r'^version = "([^"\r\n]+)"', project_text, re.MULTILINE)
        release_match = re.search(r'set "VERSION=v([^"\r\n]+)"', release_script)
        self.assertIsNotNone(project_match)
        self.assertIsNotNone(release_match)
        self.assertEqual(project_match.group(1), __version__)
        self.assertEqual(release_match.group(1), __version__)

    def test_declared_license_file_exists(self) -> None:
        self.assertTrue((ROOT / "LICENSE").is_file())


if __name__ == "__main__":
    unittest.main()
