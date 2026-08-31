from __future__ import annotations

import unittest

from damage_gui.gui.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, Translator


class TranslatorTests(unittest.TestCase):
    def test_defaults_to_simplified_chinese(self) -> None:
        translator = Translator()

        self.assertEqual(translator.language, DEFAULT_LANGUAGE)
        self.assertEqual(translator.t("language.label"), "语言")
        self.assertEqual(translator.t("missing.key"), "missing.key")

    def test_switch_notifies_listeners_and_preserves_formatting(self) -> None:
        translator = Translator()
        changes: list[str] = []
        translator.subscribe(lambda: changes.append(translator.language))

        self.assertTrue(translator.set_language("en"))
        self.assertEqual(changes, ["en"])
        self.assertEqual(translator.t("panel.level_samples", level="F"), "Level F samples")
        self.assertFalse(translator.set_language("en"))
        self.assertFalse(translator.set_language("fr"))

    def test_language_choices_round_trip(self) -> None:
        translator = Translator()

        for language in SUPPORTED_LANGUAGES:
            label = translator.language_label(language)
            self.assertEqual(translator.language_from_label(label), language)

        self.assertEqual(translator.language_choices(), ("中文", "English"))


if __name__ == "__main__":
    unittest.main()
