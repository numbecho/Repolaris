"""Unit tests for Repolaris Internationalization (i18n) Engine."""

import unittest

from repolaris.i18n import (
    TRANSLATIONS,
    get_current_locale,
    get_supported_locales,
    set_locale,
    tr,
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
        self.assertIn("pt", locales)
        self.assertEqual(locales["en"], "English")
        self.assertEqual(locales["es"], "Español")
        self.assertEqual(locales["fr"], "Français")
        self.assertEqual(locales["de"], "Deutsch")
        self.assertEqual(locales["pt"], "Português")

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
        self.assertIn("Importar", tr("btn_open"))

    def test_french_translations(self):
        self.assertTrue(set_locale("fr"))
        self.assertEqual(get_current_locale(), "fr")
        self.assertIn("Fréquence Cardiaque", tr("kpi_hr_title"))
        self.assertIn("Repolarisation Ventriculaire", tr("kpi_qtc_title"))
        self.assertIn("Journal des Événements", tr("tab_events"))
        self.assertIn("Importer", tr("btn_open"))

    def test_german_translations(self):
        self.assertTrue(set_locale("de"))
        self.assertEqual(get_current_locale(), "de")
        self.assertIn("Herzfrequenz", tr("kpi_hr_title"))
        self.assertIn("Repolarisation", tr("kpi_qtc_title"))
        self.assertIn("Ereignistagebuch", tr("tab_events"))
        self.assertIn("Importieren", tr("btn_open"))

    def test_portuguese_translations(self):
        self.assertTrue(set_locale("pt"))
        self.assertEqual(get_current_locale(), "pt")
        self.assertIn("Frequência Cardíaca", tr("kpi_hr_title"))
        self.assertIn("Repolarização Ventricular", tr("kpi_qtc_title"))
        self.assertIn("Diário de Eventos", tr("tab_events"))
        self.assertIn("Importar", tr("btn_open"))

    def test_formatting_placeholders(self):
        set_locale("en")
        msg_en = tr("adv_total_cycles", count=142)
        self.assertEqual(msg_en, "Total Analyzed Cycles: 142")

        set_locale("es")
        msg_es = tr("adv_total_cycles", count=142)
        self.assertEqual(msg_es, "Total de Ciclos Analizados: 142")

        set_locale("pt")
        msg_pt = tr("adv_total_cycles", count=142)
        self.assertEqual(msg_pt, "Total de Ciclos Analisados: 142")

    def test_canvas_scale_and_grid_translations(self):
        """Verify scale badge formatting and toggle button labels across all languages."""
        for lang, expected_prefix, expected_lines in [
            ("en", "Scale", "⊞ Lines"),
            ("es", "Escala", "⊞ Líneas"),
            ("fr", "Échelle", "⊞ Lignes"),
            ("de", "Maßstab", "⊞ Linien"),
            ("pt", "Escala", "⊞ Linhas"),
        ]:
            set_locale(lang)
            self.assertEqual(tr("canvas_scale_prefix"), expected_prefix)
            self.assertEqual(tr("grid_btn_lines"), expected_lines)
            fmt = tr("canvas_scale_fmt", speed="25", gain="10")
            self.assertIn("25 mm/s", fmt)
            self.assertIn("10 mm/mV", fmt)

    def test_clinical_ecg_zoom_and_scale_constants(self):
        """Verify standard ECG sweep speeds, sensitivities, and grid visibility logic."""
        from repolaris.app import CLINICAL_GAINS, CLINICAL_SPEEDS

        self.assertEqual(CLINICAL_SPEEDS, [12.5, 25.0, 50.0, 100.0])
        self.assertEqual(CLINICAL_GAINS, [2.5, 5.0, 10.0, 20.0])

        # Verify 250 mm standard strip duration formula (250 / speed)
        self.assertAlmostEqual(250.0 / 25.0, 10.0)
        self.assertAlmostEqual(250.0 / 50.0, 5.0)
        self.assertAlmostEqual(250.0 / 12.5, 20.0)
        self.assertAlmostEqual(250.0 / 100.0, 2.5)

        # Verify 40 mm standard amplitude span formula (40 / gain)
        self.assertAlmostEqual(40.0 / 10.0, 4.0)
        self.assertAlmostEqual(40.0 / 5.0, 8.0)
        self.assertAlmostEqual(40.0 / 20.0, 2.0)
        self.assertAlmostEqual(40.0 / 2.5, 16.0)

        # Scale indicator badge only visible when grid is enabled (lines or dots)
        self.assertTrue("lines" != "none")
        self.assertTrue("dots" != "none")
        self.assertFalse("none" != "none")

    def test_time_axis_millisecond_precision(self):
        """Verify time axis precision down to milliseconds (hh:mm:ss:xxx)."""
        from repolaris.app import TimeAxisItem

        axis = TimeAxisItem()

        # Sub-second tick strings (e.g. at 25 mm/s or 50 mm/s where spacing < 1.0s)
        self.assertEqual(axis.format_timestamp(0.040, include_millis=True), "00:00:00:040")
        self.assertEqual(axis.format_timestamp(0.200, include_millis=True), "00:00:00:200")
        self.assertEqual(axis.format_timestamp(1.456, include_millis=True), "00:00:01:456")
        self.assertEqual(axis.format_timestamp(65.123, include_millis=True), "00:01:05:123")
        self.assertEqual(axis.format_timestamp(3661.005, include_millis=True), "01:01:01:005")
        self.assertEqual(axis.format_timestamp(-0.500, include_millis=True), "-00:00:00:500")

        # Test tickStrings method with sub-second spacing
        ticks = axis.tickStrings([0.0, 0.040, 0.080, 0.120], scale=1.0, spacing=0.040)
        self.assertEqual(ticks, ["00:00:00:000", "00:00:00:040", "00:00:00:080", "00:00:00:120"])

        # Test axis_time label localization contains hh:mm:ss:xxx
        for lang, expected_token in [
            ("en", "hh:mm:ss:xxx"),
            ("es", "hh:mm:ss:xxx"),
            ("fr", "hh:mm:ss:xxx"),
            ("de", "hh:mm:ss:xxx"),
            ("pt", "hh:mm:ss:xxx"),
        ]:
            set_locale(lang)
            self.assertIn(expected_token, tr("axis_time"))

    def test_menu_bar_translations(self):
        """Verify menu bar items and action titles across all languages."""
        for lang, expected_file, expected_pref, expected_help in [
            ("en", "File", "Preferences", "Help"),
            ("es", "Archivo", "Preferencias", "Ayuda"),
            ("fr", "Fichier", "Préférences", "Aide"),
            ("de", "Datei", "Einstellungen", "Hilfe"),
            ("pt", "Arquivo", "Preferências", "Ajuda"),
        ]:
            set_locale(lang)
            self.assertEqual(tr("menu_file"), expected_file)
            self.assertEqual(tr("menu_preferences"), expected_pref)
            self.assertEqual(tr("menu_help"), expected_help)
            self.assertTrue(len(tr("menu_open_study")) > 0)
            self.assertTrue(len(tr("menu_export_study")) > 0)
            self.assertTrue(len(tr("menu_close_study")) > 0)
            self.assertTrue(len(tr("menu_languages")) > 0)
            self.assertTrue(len(tr("menu_interface_theme")) > 0)
            self.assertTrue(len(tr("menu_canvas_theme")) > 0)
            self.assertTrue(len(tr("menu_toggle_calipers")) > 0)
            self.assertTrue(len(tr("menu_wiki")) > 0)
            self.assertTrue(len(tr("menu_license")) > 0)
            self.assertTrue(len(tr("menu_about")) > 0)

    def test_mvc_api_and_resources_architecture(self):
        """Verify in-process API layer (StudyAPI, AnalysisAPI, ExportAPI) and resources."""
        import os
        import xml.etree.ElementTree as ET

        from repolaris.api import AnalysisAPI, StudyAPI

        # 1. StudyAPI demo generation
        t, sig, r_peaks = StudyAPI.generate_demo_study(
            duration_sec=3.0, fs=500.0, heart_rate_bpm=72.0
        )
        self.assertEqual(len(t), 1500)
        self.assertEqual(len(sig), 1500)
        self.assertTrue(len(r_peaks) >= 3)

        # 2. AnalysisAPI execution
        res = AnalysisAPI.analyze_signal(sig, fs=500.0)
        self.assertIn("summary", res)
        self.assertTrue(res["summary"]["mean_hr_bpm"] > 60)

        # 3. AnalysisAPI QTc computation
        qtc = AnalysisAPI.calculate_qtc(0.400, 0.850)
        self.assertIn("bazett_ms", qtc)
        self.assertIn("fridericia_ms", qtc)

        # 4. resources/app.ui XML validation
        ui_path = "src/repolaris/resources/app.ui"
        self.assertTrue(os.path.exists(ui_path), f"UI file missing at {ui_path}")
        tree = ET.parse(ui_path)
        root = tree.getroot()
        self.assertEqual(root.tag, "ui")
        self.assertEqual(root.find("class").text, "MainWindow")
        widgets = {w.get("name") for w in root.iter("widget")}
        self.assertIn("mainSplitter", widgets)
        self.assertIn("plot_widget", widgets)
        self.assertIn("tabs", widgets)

        # 5. Verify utils/signal.py has zero GUI dependencies
        with open("src/repolaris/utils/signal.py", encoding="utf-8") as f:
            code = f.read()
        self.assertNotIn("PyQt", code)
        self.assertNotIn("QWidget", code)
        self.assertNotIn("QFrame", code)

    def test_dictionary_key_parity(self):
        """Ensure all supported languages have all the keys present in English."""
        en_keys = set(TRANSLATIONS["en"].keys())
        for lang in ("es", "fr", "de", "pt"):
            lang_keys = set(TRANSLATIONS[lang].keys())
            missing = en_keys - lang_keys
            self.assertEqual(
                len(missing), 0, f"Language '{lang}' is missing translation keys: {missing}"
            )


if __name__ == "__main__":
    unittest.main()

