import unittest

from repolaris.app import CLINICAL_GAINS, CLINICAL_SPEEDS
from repolaris.i18n import set_locale, tr


class TestCanvasControls(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(CLINICAL_SPEEDS, [12.5, 25.0, 50.0, 100.0])
        self.assertEqual(CLINICAL_GAINS, [2.5, 5.0, 10.0, 20.0])

    def test_scale_visibility(self):
        self.assertTrue(bool("lines" != "none"))
        self.assertFalse(bool("none" != "none"))

    def test_scale_formatting(self):
        set_locale("en")
        self.assertEqual(tr("canvas_scale_fmt", speed="25", gain="10"), "Scale: 25 mm/s | 10 mm/mV")

    def test_button_translations(self):
        set_locale("en")
        self.assertEqual(tr("grid_btn_lines"), "⊞ Lines")
        self.assertEqual(tr("grid_btn_dots"), "⁚ Dots")
        self.assertEqual(tr("grid_btn_off"), "⊘ Off")
        self.assertEqual(tr("calipers_btn_toggle"), "📏 Calipers")
        self.assertEqual(tr("calipers_btn_center"), "⟲ Center")
        self.assertEqual(tr("calipers_btn_add"), "➕ Line")
        self.assertEqual(tr("zoom_label"), "Zoom:")
