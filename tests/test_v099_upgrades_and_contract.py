"""Stage 3 (v0.9.9) Upgrades, Schema Parity, 5-Language i18n & Public API Contract Audit."""

import contextlib
import io
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

import repolaris
from repolaris.api import AnalysisAPI, BatchAPI, ExportAPI, StudyAPI
from repolaris.cli import main as cli_main
from repolaris.detection.pipeline import analyze_ecg, analyze_ecg_stream
from repolaris.detection.t_end import detect_t_end
from repolaris.i18n import TRANSLATIONS
from repolaris.io.ecg_loader import reconstruct_derived_leads
from repolaris.io.scp_reader import _decode_cen_default_huffman, _reconstruct_differences
from repolaris.plugins import GLOBAL_PLUGIN_REGISTRY
from repolaris.utils.signal import generate_synthetic_ecg


class TestV099UpgradesAndContract(unittest.TestCase):
    """Verifies all v0.9.9 upgrades, streaming schema parity, 5-language i18n, and public API contract."""

    def test_version_and_public_api_exports(self) -> None:
        self.assertGreaterEqual(tuple(int(x) for x in repolaris.__version__.split(".")), (0, 9, 9))
        for obj in (StudyAPI, AnalysisAPI, ExportAPI, BatchAPI, GLOBAL_PLUGIN_REGISTRY):
            self.assertIsNotNone(obj)

    def test_cen_default_huffman_19999_and_second_difference_reconstruction(self) -> None:
        # Bitstream: "0" (0), "100" (+1), "101" (-1), "1100" (+2), "1101" (-2) -> 0 100 101 1100 1101 = 01001011 10011010
        payload = bytes([0b01001011, 0b10011010])
        decoded = _decode_cen_default_huffman(payload, expected_samples=5)
        self.assertEqual(decoded.tolist(), [0, 1, -1, 2, -2])

        # Second difference: s0=10, s1=12, d2=1 -> s2 = 1 + 2*12 - 10 = 15
        recon = _reconstruct_differences(np.array([10, 12, 1], dtype=np.int32), diff_mode=2)
        self.assertEqual(recon.tolist(), [10, 12, 15])

    def test_derived_12_lead_reconstruction_from_8_independent_leads(self) -> None:
        t = np.linspace(0, 1.0, 250, dtype=np.float32)
        lead_i = np.sin(2 * np.pi * 2.0 * t).astype(np.float32)
        lead_ii = np.cos(2 * np.pi * 2.0 * t).astype(np.float32)
        eight_leads = {
            "I": lead_i,
            "II": lead_ii,
            "V1": lead_i * 0.5,
            "V2": lead_i * 0.6,
            "V3": lead_i * 0.7,
            "V4": lead_i * 0.8,
            "V5": lead_i * 0.9,
            "V6": lead_i * 1.0,
        }
        twelve = reconstruct_derived_leads(eight_leads)
        self.assertEqual(len(twelve), 12)
        np.testing.assert_allclose(twelve["III"], lead_ii - lead_i, atol=1e-5)
        np.testing.assert_allclose(twelve["aVR"], -0.5 * (lead_i + lead_ii), atol=1e-5)
        np.testing.assert_allclose(twelve["aVL"], lead_i - 0.5 * lead_ii, atol=1e-5)
        np.testing.assert_allclose(twelve["aVF"], lead_ii - 0.5 * lead_i, atol=1e-5)

    def test_phasor_transform_delineator_and_builtin_plugin(self) -> None:
        _, sig, _ = generate_synthetic_ecg(10.0, fs=500.0, heart_rate_bpm=72.0)
        res = analyze_ecg(sig, fs=500.0)
        r0 = int(res["r_peaks"][1])
        t_pk, t_end = detect_t_end(sig, r0, fs=500.0, method="phasor")
        self.assertGreater(t_end, t_pk)

        plugin_fn = GLOBAL_PLUGIN_REGISTRY.get_t_end_delineator("phasor")
        self.assertIsNotNone(plugin_fn)
        assert plugin_fn is not None
        self.assertEqual(plugin_fn(sig, r0, 500.0), t_end)

    def test_strict_ectopic_summary_schema_parity_memory_vs_stream(self) -> None:
        _, sig, _ = generate_synthetic_ecg(300.0, fs=250.0, heart_rate_bpm=72.0)
        r_mem = analyze_ecg(sig, fs=250.0)
        r_str = analyze_ecg_stream(sig, fs=250.0, chunk_duration_sec=120.0, overlap_sec=5.0)
        self.assertEqual(set(r_mem["ectopic_summary"].keys()), set(r_str["ectopic_summary"].keys()))

    def test_cli_benchmark_native_atr_support(self) -> None:
        _, sig, _ = generate_synthetic_ecg(10.0, fs=250.0, heart_rate_bpm=72.0)
        res = analyze_ecg(sig, fs=250.0)
        r_peaks = [int(b["r_peak_sample"]) for b in res["beats"]]

        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            hea = tdir / "rec.hea"
            dat = tdir / "rec.dat"
            atr = tdir / "rec.atr"
            hea.write_text(f"rec 1 250 {len(sig)}\nrec.dat 16 200/mV 16 0 0 0 0 II\n")
            dat.write_bytes((sig * 200).astype("<i2").tobytes())

            # Encode MIT-BIH .atr with code 1 (N) at each r_peak
            buf = bytearray()
            prev = 0
            for rp in r_peaks:
                dt = rp - prev
                prev = rp
                if dt < 1024:
                    buf += struct.pack("<H", (1 << 10) | dt)
                else:
                    buf += struct.pack("<HH", (59 << 10) | 0, dt >> 16)
                    buf += struct.pack("<H", dt & 0xFFFF)
            buf += struct.pack("<H", 0)
            atr.write_bytes(bytes(buf))

            stdout_cap = io.StringIO()
            with contextlib.redirect_stdout(stdout_cap):
                cli_main(["benchmark", "--input", str(hea), "--reference", str(atr)])
            out = stdout_cap.getvalue()
            self.assertIn("ANSI/AAMI EC57 Real-Record Benchmark", out)
            self.assertIn("Se=100.00%", out)

    def test_five_language_i18n_complete_key_parity(self) -> None:
        expected_locales = {"en", "es", "fr", "de", "pt"}
        self.assertTrue(expected_locales.issubset(set(TRANSLATIONS.keys())))
        base_keys = set(TRANSLATIONS["en"].keys())
        for loc in expected_locales:
            self.assertEqual(
                set(TRANSLATIONS[loc].keys()),
                base_keys,
                f"Locale {loc!r} has key drift vs 'en'",
            )



    def test_pyside6_migration_and_distraction_free_gui(self) -> None:
        """Verifies zero PyQt6 imports remain, Demo button is removed, and UI tabs/buttons have no emoji clutter."""
        root = Path(__file__).resolve().parent.parent
        for py_file in (root / "src").rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            self.assertNotIn("from PyQt6", content, f"Legacy PyQt6 import found in {py_file}")
            self.assertNotIn("import PyQt6", content, f"Legacy PyQt6 import found in {py_file}")

        app_src = (root / "src" / "repolaris" / "app.py").read_text(encoding="utf-8")
        self.assertIn("from PySide6.QtCore import", app_src)
        self.assertNotIn("self.btn_demo", app_src)

        for key in ("btn_open", "btn_export", "btn_export_pdf", "btn_settings", "tab_overview", "tab_events", "tab_holter", "tab_beats", "tab_butterfly"):
            label = TRANSLATIONS["en"][key]
            self.assertTrue(all(ord(ch) < 0x1F000 for ch in label), f"Emoji found in {key}: {label!r}")


if __name__ == "__main__":
    unittest.main()
