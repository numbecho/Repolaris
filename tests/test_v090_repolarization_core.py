"""Automated Verification Suite for Repolaris v0.9.0 Phase 1 Core Repolarization Features.

Validates:
1. FDA CiPA Sub-Interval Decomposition (`detect_j_point`, `compute_cipa_metrics`, `AnalysisAPI.calculate_cipa_subintervals`):
   - J-Tpeak, rate-corrected J-Tpeakc (Johannesen et al., 2014/2016 exponent 0.58), Tpe (Tpeak-Tend), and Tpe/QT ratio (Gupta et al., 2008).
   - Differentiation of pure hERG block (prolonged J-Tpeakc & Tpe) vs. balanced multichannel late Na+ block (normal/shortened J-Tpeakc).
2. Short-Term & Long-Term Variability of QT (`compute_stv_qt`, `compute_qt_variability_poincare`, `AnalysisAPI.analyze_stv_qt`):
   - Exact Poincaré analytical equivalence (`STV_QT = sum(|QT_{n+1} - QT_n|) / (N * sqrt(2))`), sinus ('N') beat filtering, unit auto-detection, and TdP risk stratification.
3. T-Wave Morphology & 3D SVD/PCA Loop Descriptors (`t_morphology.py`, `AnalysisAPI.analyze_t_morphology`):
   - Single-lead limb area asymmetry/symmetry, flatness, notched double-peak detection, and biphasic detection.
   - Multi-lead 3D SVD dipolarity ratio (`T2/T1`), `T3/T1`, non-dipolar residue (`T_NDR %`), and Total Cosine R-to-T (`TCRT`).
4. Superimposed Multi-Lead "Butterfly" Median Beat View (`compute_superimposed_median_beat`, `MainWindow.tab_butterfly`):
   - Ensemble R-peak alignment, spatial RMS magnitude curve, global earliest Q-onset & global latest T-end caliper adjudication, interactive caliper dragging, and 5-language i18n parity.
"""

from __future__ import annotations

import math
import unittest

import numpy as np

from repolaris.api import AnalysisAPI, StudyAPI
from repolaris.app import MainWindow, QApplication
from repolaris.detection.pipeline import analyze_ecg, analyze_ecg_stream
from repolaris.detection.pulse_metrics import (
    compute_cipa_metrics,
    compute_stv_qt,
    summarize_beats,
)
from repolaris.detection.q_onset import detect_j_point, detect_q_onset
from repolaris.detection.qtvi import compute_qt_variability_poincare
from repolaris.detection.t_morphology import (
    compute_superimposed_median_beat,
    compute_t_wave_morphology,
    evaluate_beat_t_morphology,
)
from repolaris.i18n import set_locale, tr


class TestV090RepolarizationCore(unittest.TestCase):
    """Tests the 4 core repolarization features introduced in v0.9.0 Phase 1."""

    def setUp(self) -> None:
        self.fs = 500.0
        set_locale("en")

    def test_j_point_delineation_and_fda_cipa_subintervals(self) -> None:
        """Verifies J-point localization and FDA CiPA J-Tpeakc, Tpe, and Tpe/QT calculations."""
        _, sig, r_peaks = StudyAPI.generate_demo_study(duration_sec=8.0, fs=self.fs, heart_rate_bpm=72.0)
        r0 = int(r_peaks[1])
        q_idx = detect_q_onset(sig, r0, self.fs)
        j_idx = detect_j_point(sig, r0, self.fs)

        self.assertLess(q_idx, r0)
        self.assertGreater(j_idx, r0)
        # J-point should lie within physiological post-R window (16 ms to 85 ms)
        self.assertGreaterEqual(j_idx - r0, int(0.016 * self.fs))
        self.assertLessEqual(j_idx - r0, int(0.085 * self.fs))

        # Test exact Johannesen (2014) J-Tpeakc = J-Tpeak / (RR ** 0.58) and Gupta (2008) Tpe/QT
        rr_sec = 0.800
        cipa = AnalysisAPI.calculate_cipa_subintervals(
            q_onset_sample=100,
            j_point_sample=145,
            t_peak_sample=255,
            t_end_sample=305,
            fs=500.0,
            rr_sec=rr_sec,
        )
        expected_jtp = 220.0
        expected_jtpc = expected_jtp / (rr_sec**0.58)
        expected_tpe = 100.0
        expected_ratio = 100.0 / 410.0

        self.assertAlmostEqual(cipa["jt_peak_ms"], expected_jtp, places=2)
        self.assertAlmostEqual(cipa["jt_peak_c_ms"], round(expected_jtpc, 2), places=2)
        self.assertAlmostEqual(cipa["tpe_ms"], expected_tpe, places=2)
        self.assertAlmostEqual(cipa["tpe_qt_ratio"], round(expected_ratio, 4), places=4)

        # Simulate pure hERG block (prolongs both J-Tpeak and Tpe) vs. late Na+ block (shortens J-Tpeak)
        herg_cipa = compute_cipa_metrics(100, 145, 270, 330, 500.0, rr_sec=0.800)
        late_na_cipa = compute_cipa_metrics(100, 145, 245, 315, 500.0, rr_sec=0.800)
        self.assertGreater(herg_cipa["jt_peak_c_ms"], late_na_cipa["jt_peak_c_ms"] + 40.0)
        self.assertGreater(herg_cipa["tpe_ms"], 110.0)

    def test_poincare_stv_qt_and_ltv_qt_analytical_and_ectopic_gating(self) -> None:
        """Verifies Thomsen (2004) Poincaré STV_QT, LTV_QT, ectopic PVC exclusion, and risk tiers."""
        # 1. Constant QT intervals -> 0.0 ms variability
        const_res = compute_stv_qt([400.0, 400.0, 400.0, 400.0, 400.0])
        self.assertAlmostEqual(const_res["stv_qt_ms"], 0.0, places=4)
        self.assertAlmostEqual(const_res["ltv_qt_ms"], 0.0, places=4)
        self.assertEqual(const_res["risk_category"], "NORMAL")

        # 2. Alternating beat-to-beat QT series: 400, 412, 400, 412, 400, 412 ms
        alt_qt = [400.0, 412.0, 400.0, 412.0, 400.0, 412.0]
        alt_res = AnalysisAPI.analyze_stv_qt(alt_qt)
        self.assertAlmostEqual(alt_res["stv_qt_ms"], 12.0 / math.sqrt(2.0), places=2)
        self.assertAlmostEqual(alt_res["ltv_qt_ms"], 0.0, places=3)
        self.assertEqual(alt_res["risk_category"], "HIGH_TDP_RISK")

        # 3. Verify seconds-to-milliseconds auto-scaling and qtvi.py alias parity
        alt_sec = [q / 1000.0 for q in alt_qt]
        poinc_res = compute_qt_variability_poincare(alt_sec)
        self.assertAlmostEqual(poinc_res["stv_qt_ms"], alt_res["stv_qt_ms"], places=2)

        # 4. Verify ectopic PVC ('V') filtering preserves clean sinus STV_QT
        qt_with_pvc = [400.0, 401.0, 400.0, 520.0, 401.0, 400.0]
        classes = ["N", "N", "N", "V", "N", "N"]
        gated_res = compute_stv_qt(qt_with_pvc, beat_classes=classes)
        self.assertLess(gated_res["stv_qt_ms"], 1.5)
        self.assertEqual(gated_res["beats_used"], 5)
        self.assertEqual(gated_res["risk_category"], "NORMAL")

    def test_t_wave_morphology_notching_biphasic_and_3d_svd_pca(self) -> None:
        """Verifies single-lead T-wave asymmetry/flatness/notching/biphasic detection and 3D SVD T2/T1 & TCRT."""
        fs = 500.0
        n_samp = 250
        t = np.arange(n_samp, dtype=np.float64) / fs

        # 1. Clean monophasic asymmetric T-wave (slow ascent, fast descent)
        mono_sig = np.zeros(n_samp, dtype=np.float64)
        for i in range(40, 140):
            tau = (i - 40) / 100.0
            mono_sig[i] = 0.35 * (tau**2) * ((1.0 - tau) ** 0.8) * 6.5
        tp_mono = int(np.argmax(mono_sig))
        m_mono = evaluate_beat_t_morphology(mono_sig, 40, tp_mono, 140, fs)
        self.assertFalse(m_mono["is_notched"])
        self.assertFalse(m_mono["is_biphasic"])
        self.assertGreater(m_mono["asymmetry_ratio"], 1.05)
        self.assertLess(m_mono["flatness_score"], 0.45)

        # 2. Notched (double-humped LQT2/hERG) T-wave
        notched_sig = (
            0.25 * np.exp(-0.5 * ((t - 0.16) / 0.018) ** 2)
            + 0.24 * np.exp(-0.5 * ((t - 0.23) / 0.018) ** 2)
        )
        m_notched = evaluate_beat_t_morphology(notched_sig, 40, 80, 160, fs)
        self.assertTrue(m_notched["is_notched"])
        self.assertGreater(m_notched["notch_score"], 0.10)

        # 3. Biphasic (+ / -) T-wave
        biph_sig = (
            0.25 * np.exp(-0.5 * ((t - 0.15) / 0.020) ** 2)
            - 0.18 * np.exp(-0.5 * ((t - 0.22) / 0.020) ** 2)
        )
        m_biph = evaluate_beat_t_morphology(biph_sig, 40, 75, 155, fs)
        self.assertTrue(m_biph["is_biphasic"])

        # 4. Multi-lead 3D SVD/PCA descriptors (T2/T1, T3/T1, T_NDR, TCRT)
        _, base_sig, r_peaks = StudyAPI.generate_demo_study(duration_sec=10.0, fs=fs, heart_rate_bpm=72.0)
        t_vec = np.arange(len(base_sig), dtype=np.float64) / fs
        ortho_t = 0.08 * np.sin(2.0 * np.pi * 1.2 * t_vec)
        multi_leads = {
            "Lead I": base_sig * 0.75 + ortho_t * 0.4,
            "Lead II": base_sig * 1.00,
            "Lead V2": base_sig * 0.60 - ortho_t * 0.8,
            "Lead V5": base_sig * 0.90 + ortho_t * 0.2,
        }
        direct_morph = compute_t_wave_morphology(
            base_sig,
            fs=fs,
            r_peaks=r_peaks,
            multi_lead_signals=multi_leads,
        )
        morph_report = AnalysisAPI.analyze_t_morphology(
            base_sig,
            fs=fs,
            r_peaks=r_peaks,
            multi_lead_signals=multi_leads,
        )
        self.assertEqual(direct_morph["verdict"], morph_report["verdict"])
        self.assertIn("svd_3d", morph_report)
        svd = morph_report["svd_3d"]
        self.assertTrue(svd["available"])
        self.assertEqual(svd["lead_count"], 4)
        self.assertIsNotNone(svd["t2_t1_ratio"])
        self.assertGreaterEqual(svd["t2_t1_ratio"], 0.0)
        self.assertIsNotNone(svd["tcrt"])
        self.assertGreaterEqual(svd["tcrt"], -1.0)
        self.assertLessEqual(svd["tcrt"], 1.0)

    def test_superimposed_butterfly_median_beat_global_calipers(self) -> None:
        """Verifies Butterfly median beat synthesis and global earliest-Q / latest-T caliper resolution."""
        _, lead2, r_peaks = StudyAPI.generate_demo_study(duration_sec=10.0, fs=self.fs, heart_rate_bpm=72.0)
        leads = {
            "Lead I": np.roll(lead2, -3) * 0.70,
            "Lead II": lead2,
            "Lead V5": np.roll(lead2, 4) * 0.90,
        }
        bf = compute_superimposed_median_beat(leads, fs=self.fs, r_peaks=r_peaks, preprocess=False)
        self.assertEqual(len(bf["lead_names"]), 3)
        self.assertGreaterEqual(bf["beats_averaged"], 8)
        self.assertEqual(len(bf["rms_signal"]), len(bf["time_rel_ms"]))
        self.assertLess(bf["global_q_onset_ms"], 0.0)
        self.assertGreater(bf["global_j_point_ms"], 0.0)
        self.assertGreater(bf["global_t_peak_ms"], bf["global_j_point_ms"])
        self.assertGreater(bf["global_t_end_ms"], bf["global_t_peak_ms"])
        self.assertAlmostEqual(
            bf["global_qt_ms"],
            bf["global_t_end_ms"] - bf["global_q_onset_ms"],
            places=1,
        )

    def test_pipeline_stream_and_gui_butterfly_tab_integration(self) -> None:
        """Verifies end-to-end pipeline, streaming, summarize_beats, and GUI Butterfly & T-PCA tab."""
        _, lead2, _ = StudyAPI.generate_demo_study(duration_sec=12.0, fs=self.fs, heart_rate_bpm=72.0)
        multi = {
            "Lead I": lead2 * 0.65,
            "Lead II": lead2,
            "Lead V5": lead2 * 0.85,
        }
        res = analyze_ecg(lead2, fs=self.fs, multi_lead_signals=multi)
        self.assertIn("stv_qt", res)
        self.assertIn("t_morphology", res)
        self.assertIn("butterfly", res)
        self.assertGreater(res["summary"]["mean_jt_peak_c_ms"], 50.0)
        self.assertGreater(res["summary"]["mean_tpe_ms"], 10.0)
        self.assertGreater(res["summary"]["mean_tpe_qt_ratio"], 0.05)

        # Verify streamed pipeline also populates CiPA, STV_QT, t_morphology, and butterfly
        stream_res = analyze_ecg_stream(lead2, fs=self.fs, chunk_duration_sec=6.0, overlap_sec=1.5)
        self.assertIn("stv_qt", stream_res)
        self.assertIsNotNone(stream_res["stv_qt"])
        self.assertGreater(stream_res["summary"]["mean_jt_peak_c_ms"], 50.0)
        self.assertIsNotNone(stream_res["butterfly"])

        # Verify summarize_beats backwards compatibility on minimal legacy beat dictionaries
        legacy_sum = summarize_beats([{"hr_bpm": 70.0, "qt_ms": 400.0, "qtc": {"bazett_ms": 430.0}}])
        self.assertEqual(legacy_sum["mean_jt_peak_c_ms"], 0.0)
        self.assertEqual(legacy_sum["stv_qt_ms"], 0.0)

        # Verify MainWindow Butterfly & T-PCA tab, interactive calipers, and 5-language retranslation
        _app = QApplication.instance() or QApplication([])
        win = MainWindow()
        try:
            self.assertTrue(hasattr(win, "tab_butterfly"))
            self.assertTrue(hasattr(win, "butterfly_plot_widget"))
            self.assertTrue(hasattr(win, "butterfly_table"))
            self.assertTrue(hasattr(win, "lbl_adv_cipa"))
            self.assertTrue(hasattr(win, "lbl_adv_stv"))
            self.assertTrue(hasattr(win, "lbl_adv_tmorph"))
            self.assertGreaterEqual(win.tabs.count(), 7)

            win.multi_lead_signals = multi
            win.signal_data = lead2
            win.fs = self.fs
            win.analysis_results = res
            win._update_cards_and_tables()

            self.assertGreaterEqual(win.butterfly_table.rowCount(), 4)
            self.assertIn("J-Tpeakc=", win.lbl_adv_cipa.text())
            self.assertIn("STV_QT=", win.lbl_adv_stv.text())
            self.assertIn("T2/T1=", win.lbl_adv_tmorph.text())

            # Drag Butterfly global calipers and verify live recalculation
            win.bf_q_line.setValue(-45.0)
            win.bf_te_line.setValue(375.0)
            win._on_butterfly_caliper_moved()
            self.assertAlmostEqual(win.analysis_results["butterfly"]["global_qt_ms"], 420.0, places=1)
            self.assertIn("420.0 ms", win.lbl_butterfly_banner.text())

            # Verify 5-language switching
            for lang in ("en", "es", "fr", "de", "pt"):
                win.set_language(lang)
                self.assertTrue(len(tr("tab_butterfly")) > 0)
        finally:
            set_locale("en")
            win.close()


if __name__ == "__main__":
    unittest.main()
