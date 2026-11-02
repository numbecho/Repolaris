"""Unit tests for Repolaris v0.6.0 Advanced Autonomic & Spatial Repolarization Suite."""

from __future__ import annotations

import io
import os
import sys
import unittest
import numpy as np

from repolaris.api import AnalysisAPI
from repolaris.cli import main as cli_main
from repolaris.detection.dispersion import calculate_qt_dispersion, resolve_lead_quorum
from repolaris.detection.hrt import compute_heart_rate_turbulence
from repolaris.detection.hrv import (
    compute_comprehensive_hrv,
    compute_frequency_domain_hrv,
    compute_nonlinear_hrv,
    compute_time_domain_hrv,
)
from repolaris.detection.hysteresis import (
    compute_effective_rr_exponential,
    compute_effective_rr_linear,
    optimize_hysteresis_parameter,
)
from repolaris.detection.pipeline import analyze_ecg
from repolaris.detection.pulse_metrics import compute_qtc
from repolaris.detection.t_end import detect_t_end
from repolaris.detection.twa import compute_mma_twa, compute_spectral_twa
from repolaris.utils.signal import generate_synthetic_ecg


class TestV060AutonomicAndRepolarization(unittest.TestCase):
    def setUp(self) -> None:
        self.fs = 500.0
        self.t, self.base_sig, self.r_peaks = generate_synthetic_ecg(
            duration_sec=16.0, fs=self.fs, heart_rate_bpm=75.0, noise_std=0.005
        )

    def test_hodges_qtc_and_hybrid_t_end(self) -> None:
        """Verify Hodges QTc formula and hybrid tangent T-end delineation."""
        # At 60 BPM (RR = 1.0 s), Hodges QTc = QT + 1.75*(60 - 60) = QT
        qtc_60 = compute_qtc(0.400, 1.0)
        self.assertIn("hodges_ms", qtc_60)
        self.assertAlmostEqual(qtc_60["hodges_ms"], 400.0, places=2)

        # At 80 BPM (RR = 0.75 s), Hodges QTc = 400 + 1.75*(80 - 60) = 435.0 ms
        qtc_80 = compute_qtc(0.400, 0.75)
        self.assertAlmostEqual(qtc_80["hodges_ms"], 435.0, places=2)

        r_idx = int(self.r_peaks[2])
        tp_h, te_h = detect_t_end(self.base_sig, r_idx, self.fs, method="hybrid")
        tp_t, te_t = detect_t_end(self.base_sig, r_idx, self.fs, method="tangent")
        tp_th, te_th = detect_t_end(self.base_sig, r_idx, self.fs, method="threshold")
        self.assertEqual(tp_h, tp_t)
        self.assertEqual(tp_h, tp_th)
        self.assertGreater(te_h, tp_h)
        self.assertGreater(te_t, tp_t)

    def test_qt_dispersion_and_quorum_gating(self) -> None:
        """Verify multi-lead QT dispersion, precordial Tpe,d, and lead quorum gating."""
        self.assertEqual(resolve_lead_quorum(3), 3)
        self.assertEqual(resolve_lead_quorum(12), 8)

        # Single/dual-lead must return None
        single_res = calculate_qt_dispersion(self.base_sig[None, :], fs=self.fs)
        self.assertIsNone(single_res)
        dual_res = calculate_qt_dispersion(np.vstack([self.base_sig, self.base_sig]), fs=self.fs)
        self.assertIsNone(dual_res)

        # Synthesize 4 Holter leads with controlled T-wave dispersion (+0 ms, +20 ms, +45 ms, flat dead lead)
        _, lead_a, _ = generate_synthetic_ecg(duration_sec=10.0, fs=self.fs, heart_rate_bpm=72.0, noise_std=0.002)
        lead_b = np.roll(lead_a, 8) * 0.9
        lead_c = np.roll(lead_a, 16) * 1.1
        lead_dead = np.zeros_like(lead_a)

        leads_dict = {
            "Lead II": lead_a,
            "V2": lead_b,
            "V5": lead_c,
            "V6_Flat": lead_dead,
        }
        disp = calculate_qt_dispersion(leads_dict, fs=self.fs)
        self.assertIsNotNone(disp)
        assert disp is not None
        self.assertTrue(disp["quorum_met"])
        self.assertIn("V6_Flat", disp["rejected_leads"])
        self.assertEqual(len(disp["valid_leads"]), 3)
        self.assertGreaterEqual(disp["summary"]["mean_qtd_ms"], 0.0)
        self.assertIn("precordial_tpe_dispersion_ms", disp)

    def test_spectral_and_mma_twa(self) -> None:
        """Verify Spectral FFT (0.5 cpb) and MMA T-Wave Alternans detection."""
        _, sig_clean, r_peaks = generate_synthetic_ecg(
            duration_sec=32.0, fs=self.fs, heart_rate_bpm=96.0, noise_std=0.002
        )
        # 1. Baseline rhythm without alternans -> negative TWA
        spec_clean = compute_spectral_twa(sig_clean, self.fs, r_peaks)
        self.assertFalse(spec_clean["is_positive"])

        # 2. Inject microvolt ABAB T-wave alternans (+0.08 mV = 80 uV on odd beats)
        sig_alt = sig_clean.copy()
        for idx, r_idx in enumerate(r_peaks):
            if idx % 2 == 1:
                t_center = int(r_idx + 0.22 * self.fs)
                win = np.arange(max(0, t_center - 40), min(len(sig_alt), t_center + 40))
                sig_alt[win] += 0.08 * np.exp(-0.5 * ((win - t_center) / 15.0) ** 2)

        spec_alt = compute_spectral_twa(sig_alt, self.fs, r_peaks)
        self.assertGreater(spec_alt["v_alt_uv"], 10.0)
        self.assertGreater(spec_alt["k_score"], 3.0)
        self.assertTrue(spec_alt["is_positive"])

        mma_alt = compute_mma_twa(sig_alt, self.fs, r_peaks)
        self.assertGreater(mma_alt["max_v_mma_uv"], 20.0)
        self.assertEqual(len(mma_alt["v_mma_series_uv"]), len(mma_alt["timestamps_sec"]))

    def test_heart_rate_turbulence_categories(self) -> None:
        """Verify Heart Rate Turbulence (TO, TS, and ISHNE risk categories 0, 1, 2)."""
        # Construct R-peaks with a solitary PVC at beat index 4:
        # Preceding sinus NN = 800 ms, coupling = 520 ms (< 0.85*800), pause = 1080 ms (> 1.15*800)
        # Healthy post-PVC response: early acceleration (750, 760 ms -> TO < 0%)
        # followed by gradual deceleration (+8 ms/beat -> TS > 2.5 ms/beat)
        nn_healthy_ms = [
            800.0, 800.0, 800.0,  # beats 0->1, 1->2, 2->3
            520.0,                # coupling interval 3->4 (PVC at index 4)
            1080.0,               # compensatory pause 4->5
            750.0, 760.0, 770.0, 780.0, 790.0, 800.0, 808.0, 815.0,
            812.0, 808.0, 804.0, 802.0, 800.0, 800.0, 800.0, 800.0,
        ]
        r_samples_healthy = np.cumsum([0.0] + [ms * self.fs / 1000.0 for ms in nn_healthy_ms]).astype(int)
        labels = ["N"] * len(r_samples_healthy)
        labels[4] = "V"

        hrt_normal = compute_heart_rate_turbulence(labels, r_samples_healthy, fs=self.fs)
        self.assertEqual(hrt_normal["valid_pvc_count"], 1)
        self.assertLess(hrt_normal["turbulence_onset"], 0.0)
        self.assertGreater(hrt_normal["turbulence_slope"], 2.5)
        self.assertEqual(hrt_normal["category"], 0)

        # Pathological blunted response: post-PVC intervals >= 810 ms (TO > 0%) and flat (TS <= 2.5) -> Category 2
        nn_blunted_ms = [
            800.0, 800.0, 800.0,
            520.0,
            1080.0,
            815.0, 815.0, 815.0, 815.0, 815.0, 815.0, 815.0, 815.0,
            815.0, 815.0, 815.0, 815.0, 815.0, 815.0, 815.0, 815.0,
        ]
        r_samples_blunted = np.cumsum([0.0] + [ms * self.fs / 1000.0 for ms in nn_blunted_ms]).astype(int)
        hrt_blunted = compute_heart_rate_turbulence(labels, r_samples_blunted, fs=self.fs)
        self.assertGreaterEqual(hrt_blunted["turbulence_onset"], 0.0)
        self.assertLessEqual(hrt_blunted["turbulence_slope"], 2.5)
        self.assertEqual(hrt_blunted["category"], 2)

    def test_comprehensive_hrv_suite(self) -> None:
        """Verify Time-Domain, Welch Frequency-Domain, and Poincaré/SampEn/DFA Non-Linear HRV."""
        rng = np.random.default_rng(123)
        t_beats = np.arange(120, dtype=np.float64)
        # Modulate NN intervals around 850 ms with 0.1 Hz LF and 0.25 Hz HF respiratory sinus arrhythmia
        nn_ms = (
            850.0
            + 35.0 * np.sin(2.0 * np.pi * 0.10 * t_beats * 0.85)
            + 25.0 * np.sin(2.0 * np.pi * 0.25 * t_beats * 0.85)
            + rng.normal(0.0, 5.0, len(t_beats))
        )

        td = compute_time_domain_hrv(nn_ms)
        self.assertGreater(td["sdnn"] or 0.0, 15.0)
        self.assertGreater(td["rmssd"] or 0.0, 10.0)
        self.assertGreaterEqual(td["pnn50"] or 0.0, 0.0)

        fd = compute_frequency_domain_hrv(nn_ms, fs_resample=4.0)
        self.assertGreater(fd["lf_power"], 0.0)
        self.assertGreater(fd["hf_power"], 0.0)
        self.assertGreater(fd["lf_hf_ratio"], 0.0)
        self.assertAlmostEqual(fd["lf_nu"] + fd["hf_nu"], 100.0, places=2)

        nl = compute_nonlinear_hrv(nn_ms)
        self.assertGreater(nl["sd1"], 0.0)
        self.assertGreater(nl["sd2"], 0.0)
        # Brennan (2001) mathematical identity: SD1^2 = 0.5 * Var(NN_{i+1} - NN_i)
        expected_sd1 = float(np.sqrt(0.5 * np.var(np.diff(nn_ms), ddof=1)))
        self.assertAlmostEqual(nl["sd1"], expected_sd1, places=4)
        self.assertGreaterEqual(nl["sampen"], 0.0)
        self.assertGreater(nl["alpha_1"], 0.0)

        comp = compute_comprehensive_hrv(nn_ms)
        self.assertIn("time_domain", comp)
        self.assertIn("frequency_domain", comp)
        self.assertIn("nonlinear", comp)

    def test_qtrr_hysteresis_loop_collapse(self) -> None:
        """Verify EW/LW effective RR kernels and hysteresis parameter optimization."""
        # Step transition in RR from 1.0s to 0.6s and back to 1.0s
        rr_sec = np.concatenate([
            np.full(30, 1.0),
            np.linspace(1.0, 0.6, 30),
            np.full(30, 0.6),
            np.linspace(0.6, 1.0, 30),
        ])
        true_lambda = 0.08
        true_rr_eff = compute_effective_rr_exponential(rr_sec, lambda_param=true_lambda)
        # True QT follows memory-lagged RR_eff linearly: QT = 0.24 + 0.16 * RR_eff
        qt_sec = 0.24 + 0.16 * true_rr_eff

        lw_rr = compute_effective_rr_linear(rr_sec, memory_beats=25)
        self.assertEqual(len(lw_rr), len(rr_sec))

        hyst_res = optimize_hysteresis_parameter(qt_sec, rr_sec, model_type="linear")
        self.assertAlmostEqual(hyst_res["optimal_lambda"], true_lambda, delta=0.04)
        # Memory compensation must dramatically collapse the hysteresis loop RMSE
        self.assertLess(hyst_res["hysteresis_residual_rmse_ms"], hyst_res["raw_residual_rmse_ms"] * 0.25)
        self.assertGreater(hyst_res["loop_reduction_percent"], 75.0)
        self.assertGreater(hyst_res["t90_sec"], 0.0)

    def test_pipeline_and_cli_v060_integration(self) -> None:
        """Verify end-to-end pipeline, AnalysisAPI, CLI output, and GUI channel gating."""
        multi_leads = {
            "Lead I": self.base_sig * 0.8,
            "Lead II": self.base_sig,
            "V5": np.roll(self.base_sig, 5) * 1.1,
        }
        res = AnalysisAPI.analyze_signal(self.base_sig, fs=self.fs, multi_lead_signals=multi_leads)
        self.assertIn("hrv", res)
        self.assertIn("hrt", res)
        self.assertIn("twa", res)
        self.assertIn("hysteresis", res)
        self.assertIn("dispersion", res)
        self.assertIsNotNone(res["dispersion"])

        # Verify CLI demo output prints proper Repolaris header and non-Unknown Quality Status
        buf = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = buf
            cli_main(["demo", "--duration", "8", "--fs", "500", "--hr", "72"])
        finally:
            sys.stdout = old_stdout
        cli_out = buf.getvalue()
        self.assertIn("Repolaris Repolarization Report", cli_out)
        self.assertNotIn("Quality Status:      Unknown", cli_out)

        # Verify MainWindow._evaluate_channel_capabilities() in offscreen mode
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from repolaris.app import HAS_GUI, MainWindow
        if HAS_GUI:
            from PyQt6.QtWidgets import QApplication
            _app = QApplication.instance() or QApplication(["pytest", "-platform", "offscreen"])
            win = MainWindow()
            try:
                win.multi_lead_signals = {"Lead II": self.base_sig}
                cap_single = win._evaluate_channel_capabilities()
                self.assertFalse(cap_single["is_multilead_quorum"])
                self.assertEqual(cap_single["mode"], "SINGLE_LEAD_PATCH")

                win.multi_lead_signals = multi_leads
                cap_multi = win._evaluate_channel_capabilities()
                self.assertTrue(cap_multi["is_multilead_quorum"])
                self.assertEqual(cap_multi["mode"], "MULTI_LEAD_HOLTER")
            finally:
                win.close()


if __name__ == "__main__":
    unittest.main()
