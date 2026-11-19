"""Automated Verification Suite for Repolaris v0.9.0 Phase 2 Ambulatory Holter Features.

Validates:
1. Deceleration & Acceleration Capacity via Phase-Rectified Signal Averaging (`prsa.py`, `AnalysisAPI.analyze_prsa`):
   - Bauer et al. (The Lancet 2006) anchor selection, Haar wavelet scale s=2 evaluation, ectopic step filtering,
     and post-MI mortality risk stratification (<= 2.5 ms HIGH_RISK, 2.6-4.5 ms INTERMEDIATE_RISK, > 4.5 ms LOW_RISK).
2. Ambulatory ST-Segment Level, Slope & Transient Ischemia Engine (`st_segment.py`, `AnalysisAPI.analyze_st_segment`):
   - Local PQ isoelectric baseline reference, rate-adaptive J+80 ms (HR <= 120) vs. J+60 ms (HR > 120) measurement,
     horizontal/downsloping ST depression and ST elevation episode segmentation, and hourly ST trend histograms.
3. AF-Gated P-Wave Delineation & AV Block Screening (`p_wave.py`, `AnalysisAPI.analyze_p_waves_and_av_block`):
   - Pre-Q diastolic P-wave delineation (P_onset, P_peak, P_end, PR interval), AF gating when AF burden >= 80%,
     First-Degree AV Block (PR > 200 ms), Second-Degree Mobitz Type I (Wenckebach progressive PR before dropped beat),
     and Second-Degree Mobitz Type II (fixed PR before and after dropped beat).
4. ECG-Derived Respiration & Sleep-Disordered Breathing Screening (`edr.py`, `AnalysisAPI.analyze_edr`):
   - Moody & Mark (1985/1986) QRS area/envelope modulation resampling (4 Hz), respiratory passband (0.12-0.45 Hz)
     rate estimation (breaths/min), and Cyclic Variation of Heart Rate (CVHR) power ratio.
5. High-Rate Pacemaker Spike Guard (`detect_pacemaker_spikes`, `AnalysisAPI.detect_pacemaker_spikes`):
   - Strict Nyquist pulse-width gating (`fs >= 1000.0 Hz`) for raw waveform slew-rate (`dV/dt`) narrow spike detection,
     preventing false-positive EMG spike flags on 250-500 Hz Holters while honoring metadata pacing flags at all rates.
"""

from __future__ import annotations

import unittest

import numpy as np

from repolaris.api import AnalysisAPI, StudyAPI
from repolaris.app import MainWindow, QApplication
from repolaris.detection.edr import compute_ecg_derived_respiration
from repolaris.detection.p_wave import (
    analyze_p_waves_and_av_block,
    delineate_p_wave_single_beat,
    detect_pacemaker_spikes,
)
from repolaris.detection.pipeline import analyze_ecg, analyze_ecg_stream
from repolaris.detection.prsa import compute_prsa_capacity
from repolaris.detection.st_segment import analyze_st_segment, evaluate_beat_st_segment
from repolaris.i18n import set_locale, tr


class TestV090HolterSuite(unittest.TestCase):
    """Tests the 5 ambulatory Holter diagnostic modules introduced in v0.9.0 Phase 2."""

    def setUp(self) -> None:
        self.fs = 500.0
        set_locale("en")

    def test_prsa_deceleration_and_acceleration_capacity_risk_tiers(self) -> None:
        """Verifies Bauer (2006) PRSA DC/AC computation, ectopic step rejection, and post-MI risk tiers."""
        idx = np.arange(120, dtype=np.float64)

        # 1. Healthy vagal respiratory sinus arrhythmia (+/- 35 ms modulation around 850 ms)
        healthy_rr_ms = 850.0 + 35.0 * np.sin(2.0 * np.pi * idx / 6.0)
        res_healthy = AnalysisAPI.analyze_prsa(healthy_rr_ms)
        self.assertTrue(res_healthy["valid"])
        self.assertGreater(res_healthy["dc_ms"], 8.0)
        self.assertLess(res_healthy["ac_ms"], -8.0)
        self.assertEqual(res_healthy["risk_category"], "LOW_RISK")

        # 2. Severely blunted vagal capacity (+/- 1.5 ms modulation around 750 ms) -> DC <= 2.5 ms (HIGH_RISK)
        blunted_rr_ms = 750.0 + 1.5 * np.sin(2.0 * np.pi * idx / 6.0)
        res_blunted = compute_prsa_capacity(blunted_rr_ms)
        self.assertTrue(res_blunted["valid"])
        self.assertLessEqual(res_blunted["dc_ms"], 2.5)
        self.assertEqual(res_blunted["risk_category"], "HIGH_RISK")

        # 3. Intermediate vagal capacity (+/- 4.5 ms modulation) -> 2.5 < DC <= 4.5 ms (INTERMEDIATE_RISK)
        inter_rr_ms = 800.0 + 4.5 * np.sin(2.0 * np.pi * idx / 6.0)
        res_inter = compute_prsa_capacity(inter_rr_ms)
        self.assertGreater(res_inter["dc_ms"], 2.5)
        self.assertLessEqual(res_inter["dc_ms"], 4.5)
        self.assertEqual(res_inter["risk_category"], "INTERMEDIATE_RISK")

        # 4. Verify ectopic PVC spike rejection and seconds-to-ms auto-conversion
        rr_with_pvc_sec = blunted_rr_ms.copy() / 1000.0
        rr_with_pvc_sec[40] = 0.420  # Premature PVC
        rr_with_pvc_sec[41] = 1.180  # Compensatory pause
        classes = ["N"] * 120
        classes[40] = "V"
        res_gated = compute_prsa_capacity(rr_with_pvc_sec, beat_classes=classes)
        self.assertLessEqual(res_gated["dc_ms"], 2.5)
        self.assertEqual(res_gated["risk_category"], "HIGH_RISK")

    def test_st_segment_level_slope_and_ischemic_episode_detection(self) -> None:
        """Verifies J+60/80 ms ST deviation, rate-adaptive offset, and sustained ischemic episode segmentation."""
        _, base_sig, r_peaks = StudyAPI.generate_demo_study(duration_sec=20.0, fs=self.fs, heart_rate_bpm=75.0)

        # 1. Clean baseline rhythm -> normal ST segment, 0 ischemic episodes
        clean_st = analyze_st_segment(base_sig, fs=self.fs, r_peaks=r_peaks, min_episode_duration_sec=5.0)
        self.assertEqual(clean_st["num_episodes"], 0)
        self.assertEqual(clean_st["verdict"], "NORMAL")

        # 2. Inject a sustained -220 uV (-0.22 mV) horizontal ST depression after J-point on all beats
        dep_sig = base_sig.copy()
        for r_idx in r_peaks:
            j_start = min(len(dep_sig), int(r_idx) + int(0.035 * self.fs))
            j_end = min(len(dep_sig), int(r_idx) + int(0.165 * self.fs))
            dep_sig[j_start:j_end] -= 0.24

        isch_report = AnalysisAPI.analyze_st_segment(
            dep_sig,
            fs=self.fs,
            r_peaks=r_peaks,
            threshold_uv=100.0,
            min_episode_duration_sec=5.0,
        )
        self.assertGreaterEqual(isch_report["num_episodes"], 1)
        self.assertLessEqual(isch_report["mean_st_level_uv"], -100.0)
        self.assertGreater(isch_report["ischemic_burden_pct"], 40.0)
        self.assertEqual(isch_report["verdict"], "ISCHEMIC_EPISODES_DETECTED")
        self.assertEqual(isch_report["episodes"][0]["episode_type"], "ST_DEPRESSION")
        self.assertGreaterEqual(len(isch_report["hourly_st_trends"]), 1)

        # 3. Verify rate-adaptive J+60 ms selection when HR > 120 BPM vs. J+80 ms when HR <= 120 BPM
        r0 = int(r_peaks[2])
        b_rest = evaluate_beat_st_segment(dep_sig, r0 - 20, r0 + 20, self.fs, hr_bpm=75.0)
        b_tachy = evaluate_beat_st_segment(dep_sig, r0 - 20, r0 + 20, self.fs, hr_bpm=135.0)
        self.assertEqual(b_rest["measurement_offset_ms"], 80)
        self.assertEqual(b_tachy["measurement_offset_ms"], 60)

    def test_af_gated_p_wave_and_av_block_first_and_second_degree(self) -> None:
        """Verifies P-wave delineation, AF gating, 1st-degree AV block, and Mobitz Type I vs. Type II 2nd-degree AV block."""
        fs = 500.0

        def _synth_av_strip(pr_list_ms: list[float], drop_after_idx: int | None = None) -> tuple[np.ndarray, list[dict]]:
            sig = np.zeros(int(20.0 * fs), dtype=np.float64)
            t_axis = np.arange(len(sig), dtype=np.float64) / fs
            beats_out: list[dict] = []
            curr_t = 1.0
            for cycle_i, pr_ms in enumerate(pr_list_ms):
                r_samp = int(round(curr_t * fs))
                q_samp = r_samp - int(round(0.030 * fs))
                p_on_samp = q_samp - int(round((pr_ms / 1000.0) * fs))
                p_pk_samp = p_on_samp + int(round(0.045 * fs))
                p_t = p_pk_samp / fs

                # Add Gaussian P-wave, QRS spike, and T-wave
                sig += 0.16 * np.exp(-0.5 * ((t_axis - p_t) / 0.016) ** 2)
                sig += 1.20 * np.exp(-0.5 * ((t_axis - curr_t) / 0.010) ** 2)
                sig += 0.30 * np.exp(-0.5 * ((t_axis - (curr_t + 0.24)) / 0.035) ** 2)

                rr_s = (curr_t - beats_out[-1]["time_sec"]) if beats_out else 0.85
                beats_out.append({
                    "beat_index": cycle_i,
                    "r_peak_sample": r_samp,
                    "time_sec": curr_t,
                    "q_onset_sample": q_samp,
                    "rr_sec": rr_s,
                    "beat_class": "N",
                })

                if drop_after_idx is not None and cycle_i == drop_after_idx:
                    # Insert a non-conducted P-wave in the middle of a 1.70 s dropped-beat pause
                    blocked_p_t = curr_t + 0.85 - (pr_ms / 1000.0) + 0.045
                    sig += 0.16 * np.exp(-0.5 * ((t_axis - blocked_p_t) / 0.016) ** 2)
                    curr_t += 1.70
                else:
                    curr_t += 0.85
            return sig, beats_out

        # 1. Normal AV conduction (PR = 155 ms)
        sig_norm, beats_norm = _synth_av_strip([155.0] * 10)
        p_single = delineate_p_wave_single_beat(sig_norm, beats_norm[2]["q_onset_sample"], fs)
        self.assertTrue(p_single["p_detected"])
        res_norm = AnalysisAPI.analyze_p_waves_and_av_block(sig_norm, fs=fs, beats=beats_norm)
        self.assertFalse(res_norm["first_degree_av_block"])
        self.assertEqual(res_norm["second_degree_av_block"], "NONE")
        self.assertEqual(res_norm["av_conduction_verdict"], "NORMAL_AV_CONDUCTION")

        # 2. First-Degree AV Block (PR = 250 ms > 200 ms)
        sig_1st, beats_1st = _synth_av_strip([250.0] * 10)
        res_1st = analyze_p_waves_and_av_block(sig_1st, fs=fs, beats=beats_1st)
        self.assertTrue(res_1st["first_degree_av_block"])
        self.assertGreater(res_1st["mean_pr_ms"], 200.0)
        self.assertEqual(res_1st["av_conduction_verdict"], "FIRST_DEGREE_AV_BLOCK")

        # 3. Second-Degree AV Block Mobitz Type I (Wenckebach: progressive PR 150 -> 195 -> 245 ms -> dropped beat -> 150 ms)
        sig_m1, beats_m1 = _synth_av_strip([150.0, 155.0, 195.0, 245.0, 150.0, 160.0, 155.0], drop_after_idx=3)
        res_m1 = analyze_p_waves_and_av_block(sig_m1, fs=fs, beats=beats_m1)
        self.assertGreaterEqual(res_m1["dropped_p_wave_count"], 1)
        self.assertEqual(res_m1["second_degree_av_block"], "MOBITZ_TYPE_I_WENCKEBACH")
        self.assertEqual(res_m1["av_conduction_verdict"], "SECOND_DEGREE_AV_BLOCK_MOBITZ_I")

        # 4. Second-Degree AV Block Mobitz Type II (constant PR = 160 ms before and after dropped beat)
        sig_m2, beats_m2 = _synth_av_strip([160.0, 160.0, 160.0, 160.0, 160.0, 160.0, 160.0], drop_after_idx=3)
        res_m2 = analyze_p_waves_and_av_block(sig_m2, fs=fs, beats=beats_m2)
        self.assertGreaterEqual(res_m2["dropped_p_wave_count"], 1)
        self.assertEqual(res_m2["second_degree_av_block"], "MOBITZ_TYPE_II")
        self.assertEqual(res_m2["av_conduction_verdict"], "SECOND_DEGREE_AV_BLOCK_MOBITZ_II")

        # 5. AF Gating (AF burden = 95%) -> suppresses sinus P-wave search
        _, beats_af = _synth_av_strip([160.0] * 6)
        res_af = analyze_p_waves_and_av_block(sig_norm, fs=fs, beats=beats_af, af_report={"af_burden_pct": 95.0})
        self.assertTrue(res_af["af_gated"])
        self.assertEqual(res_af["av_conduction_verdict"], "AF_GATED_NO_SINUS_P")

    def test_ecg_derived_respiration_edr_frequency_recovery(self) -> None:
        """Verifies Moody & Mark (1985) EDR recovers a known 0.25 Hz (15 breaths/min) respiratory modulation."""
        _, base_sig, r_peaks = StudyAPI.generate_demo_study(duration_sec=24.0, fs=self.fs, heart_rate_bpm=75.0)
        t_vec = np.arange(len(base_sig), dtype=np.float64) / self.fs
        # Modulate QRS amplitude at 0.25 Hz (15.0 breaths/min)
        resp_envelope = 1.0 + 0.28 * np.sin(2.0 * np.pi * 0.25 * t_vec)
        mod_sig = base_sig * resp_envelope

        edr_res = AnalysisAPI.analyze_edr(mod_sig, fs=self.fs, r_peaks=r_peaks)
        direct_edr = compute_ecg_derived_respiration(mod_sig, fs=self.fs, r_peaks=r_peaks)
        self.assertTrue(edr_res["valid"])
        self.assertAlmostEqual(edr_res["respiratory_rate_brpm"], direct_edr["respiratory_rate_brpm"], places=2)
        self.assertAlmostEqual(edr_res["respiratory_rate_brpm"], 15.0, delta=3.0)
        self.assertGreater(len(edr_res["edr_waveform"]), 20)

    def test_high_rate_pacemaker_spike_guard_nyquist_gating(self) -> None:
        """Verifies pacemaker raw waveform spike detection is disabled at <1000 Hz and active at >=1000 Hz."""
        # 1. At 500 Hz (< 1000 Hz), raw spike detection is disabled even if narrow spikes exist
        _, sig_500, r_500 = StudyAPI.generate_demo_study(duration_sec=6.0, fs=500.0, heart_rate_bpm=72.0)
        sig_500_noisy = sig_500.copy()
        for r_idx in r_500:
            if r_idx > 20:
                sig_500_noisy[int(r_idx) - 15] += 1.5
        pm_500 = AnalysisAPI.detect_pacemaker_spikes(sig_500_noisy, fs=500.0, r_peaks=r_500, metadata={"pacemaker": "DDD"})
        self.assertFalse(pm_500["raw_spike_detection_enabled"])
        self.assertEqual(pm_500["spike_count"], 0)
        self.assertTrue(pm_500["metadata_pacemaker_flag"])
        self.assertTrue(pm_500["pacing_detected"])

        # 2. At 1000 Hz (>= 1000 Hz), 1 ms narrow pacing impulses 30 ms before R-peaks are detected
        _, sig_1000, r_1000 = StudyAPI.generate_demo_study(duration_sec=6.0, fs=1000.0, heart_rate_bpm=72.0)
        paced_sig = sig_1000.copy()
        for r_idx in r_1000:
            sp_idx = int(r_idx) - 30  # 30 ms before R-peak
            if sp_idx > 5:
                paced_sig[sp_idx] += 1.25  # 1 ms narrow 1.25 mV pacing impulse
        pm_1000 = detect_pacemaker_spikes(paced_sig, fs=1000.0, r_peaks=r_1000)
        self.assertTrue(pm_1000["raw_spike_detection_enabled"])
        self.assertGreaterEqual(pm_1000["spike_count"], len(r_1000) - 1)
        self.assertGreaterEqual(pm_1000["paced_beat_count"], len(r_1000) - 1)
        self.assertTrue(pm_1000["pacing_detected"])

    def test_pipeline_stream_and_gui_v090_phase2_integration(self) -> None:
        """Verifies end-to-end pipeline, streaming, and GUI Overview labels for all 5 Phase 2 Holter features."""
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=12.0, fs=self.fs, heart_rate_bpm=72.0)
        res = analyze_ecg(sig, fs=self.fs, metadata={"pacemaker": "NO"})
        for key in ("prsa", "st_segment", "p_wave", "edr", "pacemaker"):
            self.assertIn(key, res)

        stream_res = analyze_ecg_stream(sig, fs=self.fs, chunk_duration_sec=6.0, overlap_sec=1.5)
        for key in ("prsa", "st_segment", "p_wave", "edr", "pacemaker"):
            self.assertIn(key, stream_res)

        _app = QApplication.instance() or QApplication([])
        win = MainWindow()
        try:
            for attr in ("lbl_adv_prsa", "lbl_adv_st", "lbl_adv_pwave", "lbl_adv_edr"):
                self.assertTrue(hasattr(win, attr), f"MainWindow missing {attr}")

            win.signal_data = sig
            win.fs = self.fs
            win.analysis_results = res
            win._update_cards_and_tables()

            self.assertIn("ST", win.lbl_adv_st.text())
            self.assertIn("PR=", win.lbl_adv_pwave.text())
            self.assertIn("EDR", win.lbl_adv_edr.text())

            for lang in ("en", "es", "fr", "de", "pt"):
                win.set_language(lang)
                self.assertTrue(len(tr("adv_prsa_na", val="N/A")) > 0)
        finally:
            set_locale("en")
            win.close()


if __name__ == "__main__":
    unittest.main()
