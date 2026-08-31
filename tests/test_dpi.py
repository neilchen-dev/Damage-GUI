"""Pure tests for the desktop DPI and font-selection helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.gui.dpi import dpi_to_tk_scaling
from damage_gui.gui.theme import Theme, resolve_font_families


class _FakeTk:
    def __init__(self) -> None:
        self.scaling = 1.0

    def call(self, *args: object) -> float:
        if args[:2] != ("tk", "scaling"):
            raise AssertionError(args)
        if len(args) == 3:
            self.scaling = float(args[2])
        return self.scaling


class _FakeRoot:
    def __init__(self) -> None:
        self.tk = _FakeTk()


class DpiAndFontTests(unittest.TestCase):
    def test_dpi_conversion_uses_tk_pixels_per_point(self) -> None:
        self.assertAlmostEqual(dpi_to_tk_scaling(96), 96 / 72)
        self.assertAlmostEqual(dpi_to_tk_scaling(120), 120 / 72)
        self.assertAlmostEqual(dpi_to_tk_scaling(144), 144 / 72)
        self.assertAlmostEqual(dpi_to_tk_scaling(168), 168 / 72)

    def test_tk_scaling_is_inspected_and_aligned(self) -> None:
        from damage_gui.gui.dpi import sync_tk_scaling

        info = sync_tk_scaling(_FakeRoot(), dpi=120)
        self.assertEqual(info.actual_dpi, 120)
        self.assertAlmostEqual(info.before, 1.0)
        self.assertAlmostEqual(info.after, 120 / 72)
        self.assertTrue(info.changed)

    def test_font_fallbacks_are_deterministic(self) -> None:
        theme = Theme()
        families = resolve_font_families(
            ("Segoe UI", "Microsoft YaHei UI", "Consolas"), theme
        )
        self.assertEqual(families.latin, "Segoe UI")
        self.assertEqual(families.chinese, "Microsoft YaHei UI")
        self.assertEqual(families.mono, "Consolas")


if __name__ == "__main__":
    unittest.main()
