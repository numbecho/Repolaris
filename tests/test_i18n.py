"""Unit tests for Repolaris Internationalization (i18n) Engine."""

import unittest
from repolaris.i18n import (
    tr, set_locale, get_current_locale, get_supported_locales,
    SUPPORTED_LANGUAGES, TRANSLATIONS
)


class TestI18n(unittest.TestCase):
    def setUp(self):
        # Reset to default locale before each test
        set_locale("en")

    def test_supported_languages(self):
        locales = get_supported_locales()
        self.assertIn("en", locales)
        self.assertIn("es", locales)
        self.assertIn("fr", locales)
        self.assertIn("de", locales)
        self.assertEqual(locales["en"], "English")
        self.assertEqual(locales["es"], "Español")
        self.assertEqual(locales["fr"], "Français")
        self.assertEqual(locales["de"], "Deutsch")

    def test_default_english_translations(self):
        self.assertEqual(tr("app_title"), "Repolaris")
        self.assertIn("Mean Heart Rate", tr("kpi_hr_title"))
        self.assertIn("Repolarization", tr("kpi_qtc_title"))
        self.assertIn("Events Diary", tr("tab_events"))

    def test_spanish_translations(self):
        self.assertTrue(set_locale("es"))
        self.assertEqual(get_current_locale(), "es")
        self.assertIn("Frecuencia Cardíaca", tr("kpi_hr_title"))
        self.assertIn("Repolarización Ventricular", tr("kpi_qtc_title"))
        self.assertIn("Diario de Eventos", tr("tab_events"))
        self.assertIn("Abrir Registro", tr("btn_open"))

    def test_french_translations(self):
        self.assertTrue(set_locale("fr"))
        self.assertEqual(get_current_locale(), "fr")
        self.assertIn("Fréquence Cardiaque", tr("kpi_hr_title"))
        self.assertIn("Repolarisation Ventriculaire", tr("kpi_qtc_title"))
        self.assertIn("Journal des Événements", tr("tab_events"))
        self.assertIn("Ouvrir Enregistrement", tr("btn_open"))

    def test_german_translations(self):
        self.assertTrue(set_locale("de"))
        self.assertEqual(get_current_locale(), "de")
        self.assertIn("Herzfrequenz", tr("kpi_hr_title"))
        self.assertIn("Repolarisation", tr("kpi_qtc_title"))
        self.assertIn("Ereignistagebuch", tr("tab_events"))
        self.assertIn("EKG Öffnen", tr("btn_open"))

    def test_formatting_placeholders(self):
        set_locale("en")
        msg_en = tr("adv_total_cycles", count=142)
        self.assertEqual(msg_en, "Total Analyzed Cycles: 142")

        set_locale("es")
        msg_es = tr("adv_total_cycles", count=142)
        self.assertEqual(msg_es, "Total de Ciclos Analizados: 142")

    def test_dictionary_key_parity(self):
        """Ensure all supported languages have all the keys present in English."""
        en_keys = set(TRANSLATIONS["en"].keys())
        for lang in ("es", "fr", "de"):
            lang_keys = set(TRANSLATIONS[lang].keys())
            missing = en_keys - lang_keys
            self.assertEqual(
                len(missing), 0,
                f"Language '{lang}' is missing translation keys: {missing}"
            )


if __name__ == "__main__":
    unittest.main()
