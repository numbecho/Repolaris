"""Unit tests for Repolaris v0.6.0 Advanced Autonomic & Spatial Repolarization Suite."""

from __future__ import annotations

import io
import os
import sys
import unittest
import numpy as np

from repolaris.api import AnalysisAPI
from repolaris.cli import main as cli_main
from repolaris.config import FilterConfig, DetectionConfig
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
from repolaris.detection.qtrr import (
    SUPPORTED_QTRR_MODELS,
    fit_all_qtrr_models,
    fit_qtrr_model,
)
from repolaris.detection.sqi import (
    compute_ksqi,
    compute_ssqi,
    evaluate_lead_quality,
    rank_leads_two_stage,
)
from repolaris.detection.t_end import detect_t_end
from repolaris.detection.twa import compute_mma_twa, compute_spectral_twa
from repolaris.utils.signal import generate_synthetic_ecg


class TestV060AutonomicAndRepolarization(unittest.TestCase):
    def setUp(self) -> None:
        self.fs = 500.0
        self.t, self.base_sig, self.r_peaks = generate_synthetic_ecg(
            duration_sec=16.0, fs=self.fs, heart_rate_bpm=75.0, noise_std=0.005
        )

    def test_hodges_qtc_and_hybrid_zhang_t_end(self) -> None:
        """Verify Hodges QTc formula and hybrid, tangent, Zhang (2006) SWA, and threshold T-end delineation."""
        f_cfg = FilterConfig()
        self.assertAlmostEqual(f_cfg.lowcut, 0.05, places=4)
        self.assertAlmostEqual(f_cfg.notch_quality, 30.0, places=2)

        qtc_60 = compute_qtc(0.400, 1.0)
        self.assertIn("hodges_ms", qtc_60)
        self.assertAlmostEqual(qtc_60["hodges_ms"], 400.0, places=2)

        qtc_80 = compute_qtc(0.400, 0.75)
        self.assertAlmostEqual(qtc_80["hodges_ms"], 435.0, places=2)

        r_idx = int(self.r_peaks[2])
        tp_h, te_h = detect_t_end(self.base_sig, r_idx, self.fs, method="hybrid")
        tp_t, te_t = detect_t_end(self.base_sig, r_idx, self.fs, method="tangent")
        tp_z, te_z = detect_t_end(self.base_sig, r_idx, self.fs, method="zhang_area")
        tp_th, te_th = detect_t_end(self.base_sig, r_idx, self.fs, method="threshold")
        self.assertEqual(tp_h, tp_t)
        self.assertEqual(tp_h, tp_z)
        self.assertEqual(tp_h, tp_th)
        self.assertGreater(te_h, tp_h)
        self.assertGreater(te_t, tp_t)
        self.assertGreater(te_z, tp_z)

    def test_two_stage_sqi_and_pairwise_lead_voting(self) -> None:
        """Verify Stage 1 absolute SQI rejection gate and Stage 2 six-index pairwise lead voting."""
        ksqi = compute_ksqi(self.base_sig)
        ssqi = compute_ssqi(self.base_sig)
        self.assertGreater(ksqi, 3.0)
        self.assertGreater(ssqi, 0.0)

        # 1. All dead leads must be rejected at Stage 1 (quorum_passed=False, no false winner)
        dead_leads = {
            "Lead I": np.zeros_like(self.base_sig),
            "Lead II": np.zeros_like(self.base_sig),
        }
        dead_rank = rank_leads_two_stage(dead_leads, fs=self.fs)
        self.assertFalse(dead_rank["quorum_passed"])
        self.assertIsNone(dead_rank["recommended_lead"])

        # 2. Mixed clean, moderately noisy, and detached leads
        rng = np.random.default_rng(42)
        noisy_lead = self.base_sig + rng.normal(0.0, 0.12, len(self.base_sig))
        multi_leads = {
            "Lead II (Clean)": self.base_sig,
            "Lead V5 (Noisy)": noisy_lead,
            "Lead V1 (Detached)": np.zeros_like(self.base_sig),
        }
        rank_res = rank_leads_two_stage(multi_leads, fs=self.fs)
        self.assertTrue(rank_res["quorum_passed"])
        self.assertEqual(rank_res["recommended_lead"], "Lead II (Clean)")
        self.assertIn("Lead V1 (Detached)", rank_res["rejected_leads"])
        vi_clean = rank_res["per_lead"]["Lead II (Clean)"]["voting_index"]
        self.assertGreaterEqual(vi_clean, -6.0)
        self.assertLessEqual(vi_clean, 6.0)

    def test_all_10_pueyo_qtrr_restitution_models(self) -> None:
        """Verify all 10 Pueyo et al. (2004) biparametric QT-RR restitution models and domain guards."""
        rr = np.linspace(0.60, 1.15, 25)
        qt = 0.23 + 0.16 * rr + 0.002 * np.sin(np.linspace(0, 3.14, 25))

        for model_name in SUPPORTED_QTRR_MODELS:
            fit = fit_qtrr_model(rr, qt, model=model_name)
            self.assertEqual(fit["model"], model_name)
            self.assertTrue(fit["well_conditioned"])
            self.assertGreater(fit["r_squared"], 0.85)
            self.assertGreater(fit["qtc_individual_ms"], 300.0)
            self.assertLess(fit["qtc_individual_ms"], 500.0)

        multi = fit_all_qtrr_models(rr, qt, preferred_model="auto_best")
        self.assertEqual(len(multi["models"]), len(SUPPORTED_QTRR_MODELS))
        self.assertGreaterEqual(len(multi["ranking"]), 10)
        self.assertIn(multi["best_model"], SUPPORTED_QTRR_MODELS)

    def test_qt_dispersion_and_quorum_gating(self) -> None:
        """Verify multi-lead QT dispersion, precordial Tpe,d, and lead quorum gating."""
        self.assertEqual(resolve_lead_quorum(3), 3)
        self.assertEqual(resolve_lead_quorum(12), 8)

        single_res = calculate_qt_dispersion(self.base_sig[None, :], fs=self.fs)
        self.assertIsNone(single_res)
        dual_res = calculate_qt_dispersion(np.vstack([self.base_sig, self.base_sig]), fs=self.fs)
        self.assertIsNone(dual_res)

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
        spec_clean = compute_spectral_twa(sig_clean, self.fs, r_peaks)
        self.assertFalse(spec_clean["is_positive"])

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
        nn_healthy_ms = [
            800.0, 800.0, 800.0,
            520.0,
            1080.0,
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
        rr_sec = np.concatenate([
            np.full(30, 1.0),
            np.linspace(1.0, 0.6, 30),
            np.full(30, 0.6),
            np.linspace(0.6, 1.0, 30),
        ])
        true_lambda = 0.08
        true_rr_eff = compute_effective_rr_exponential(rr_sec, lambda_param=true_lambda)
        qt_sec = 0.24 + 0.16 * true_rr_eff

        lw_rr = compute_effective_rr_linear(rr_sec, memory_beats=25)
        self.assertEqual(len(lw_rr), len(rr_sec))

        hyst_res = optimize_hysteresis_parameter(qt_sec, rr_sec, model_type="linear")
        self.assertAlmostEqual(hyst_res["optimal_lambda"], true_lambda, delta=0.04)
        self.assertLess(hyst_res["hysteresis_residual_rmse_ms"], hyst_res["raw_residual_rmse_ms"] * 0.25)
        self.assertGreater(hyst_res["loop_reduction_percent"], 75.0)
        self.assertGreater(hyst_res["t90_sec"], 0.0)

    def test_pipeline_and_cli_v060_integration(self) -> None:
        """Verify end-to-end pipeline, AnalysisAPI, CLI output, and GUI QT-RR settings/visualization."""
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
        self.assertIn("lead_voting", res)
        self.assertIsNotNone(res["dispersion"])
        self.assertIsNotNone(res["lead_voting"])

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

        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from repolaris.app import HAS_GUI, MainWindow, SettingsDialog
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

                # Verify interactive QT-RR model switching and SettingsDialog integration
                win.set_qtrr_model("hyperbolic")
                self.assertEqual(win.current_qtrr_model, "hyperbolic")
                win.set_hysteresis_mode("linear")
                self.assertEqual(win.current_hysteresis_mode, "linear")
                dlg = SettingsDialog(win)
                self.assertEqual(dlg.combo_qtrr_model.currentData(), "hyperbolic")
                self.assertEqual(dlg.combo_hysteresis.currentData(), "linear")
                dlg.close()
            finally:
                win.close()


if __name__ == "__main__":
    unittest.main()
