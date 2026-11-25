from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from repolaris.config import DetectionConfig, ECGConfig, FilterConfig
from repolaris.detection.dispersion import calculate_qt_dispersion
from repolaris.detection.pipeline import (
    BEAT_DTYPE,
    BeatArrayProxy,
    _condition_signal,
    analyze_ecg,
    analyze_ecg_stream,
)
from repolaris.detection.qrs import detect_r_peaks, detect_r_peaks_phasor_adaptive
from repolaris.detection.sqi import evaluate_lead_quality, rank_leads_two_stage
from repolaris.utils.signal import generate_synthetic_ecg


class TestSQIVotingAndQRSV1(unittest.TestCase):
    def test_2psd_welch_call_count_and_low_fs_bypass(self):
        fs = 500.0
        _, sig, _ = generate_synthetic_ecg(duration_sec=10.0, fs=fs, heart_rate_bpm=70.0)
        with mock.patch("repolaris.detection.sqi.welch", wraps=__import__("scipy.signal", fromlist=["welch"]).welch) as m_welch:
            q_same = evaluate_lead_quality(sig, fs)
            self.assertEqual(m_welch.call_count, 1)
            q_split = evaluate_lead_quality(sig, fs, conditioned_signal=sig * 0.99)
            self.assertEqual(m_welch.call_count, 3)

        self.assertIn("failed_criteria", q_split)
        self.assertIn("snr_clamped", q_same)

        # Low sampling rate <= 82 Hz bypasses empty 40-100 Hz noise band
        _, sig_low, _ = generate_synthetic_ecg(duration_sec=10.0, fs=80.0, heart_rate_bpm=65.0)
        q_low = evaluate_lead_quality(sig_low, 80.0)
        self.assertNotIn("snr_db", q_low["failed_criteria"])

    def test_rank_leads_selection_basis_and_fallback(self):
        fs = 250.0
        _, good, _ = generate_synthetic_ecg(duration_sec=8.0, fs=fs, heart_rate_bpm=72.0)
        flat = np.zeros_like(good)
        r_single = rank_leads_two_stage({"I": good, "II": flat}, fs=fs)
        self.assertTrue(r_single["quorum_passed"])
        self.assertEqual(r_single["recommended_lead"], "I")
        self.assertEqual(r_single["selection_basis"], "single_passing_lead")

        r_none = rank_leads_two_stage({"I": flat, "II": flat + 1e-9}, fs=fs)
        self.assertFalse(r_none["quorum_passed"])
        self.assertIsNone(r_none["recommended_lead"])
        self.assertIn(r_none["selection_basis"], ("fallback_snr", "none"))

    def test_qrs_inverted_bradycardia_ron_t_and_phasor(self):
        fs = 500.0
        # 1. Inverted S-dominant QRS complexes
        _, sig, true_r = generate_synthetic_ecg(duration_sec=10.0, fs=fs, heart_rate_bpm=70.0)
        inv_sig = -sig
        inv_clean = _condition_signal(inv_sig, fs, FilterConfig())
        det_inv = detect_r_peaks(inv_clean, fs)
        self.assertGreaterEqual(len(det_inv), len(true_r) - 1)
        for p in det_inv:
            self.assertLess(inv_clean[p], 0.0)

        # 2. Bradycardia 42 bpm with tall T-waves (~420 ms post-R)
        _, brady, true_brady = generate_synthetic_ecg(duration_sec=12.0, fs=fs, heart_rate_bpm=42.0)
        det_brady = detect_r_peaks(_condition_signal(brady, fs, FilterConfig()), fs)
        self.assertLessEqual(abs(len(det_brady) - len(true_brady)), 1)

        # 3. R-on-T PVC at 230 ms preserved under 200 ms refractory
        t = np.arange(0, int(6.0 * fs)) / fs
        ron_t = np.zeros_like(t)
        for r_sec in (1.0, 2.0, 2.23, 3.2, 4.2, 5.2):
            ron_t += 1.2 * np.exp(-0.5 * ((t - r_sec) / 0.010) ** 2)
        det_ront = detect_r_peaks(ron_t, fs, refractory_ms=200.0)
        self.assertGreaterEqual(len(det_ront), 5)

        # 4. Phasor backend + flatline guard
        det_phasor = detect_r_peaks_phasor_adaptive(sig, fs)
        self.assertGreaterEqual(len(det_phasor), len(true_r) - 1)
        self.assertEqual(len(detect_r_peaks_phasor_adaptive(np.zeros(1000), fs)), 0)

    def test_auto_select_lead_delineation_fallback_and_diagnostics(self):
        fs = 500.0
        _, clean_t, _ = generate_synthetic_ecg(duration_sec=8.0, fs=fs, heart_rate_bpm=70.0)
        # Lead I: sharp QRS but zeroed T-wave region; Lead II: full QRS + T-wave
        sharp_no_t = np.zeros_like(clean_t)
        t = np.arange(len(clean_t)) / fs
        for sec in np.arange(0.5, 7.5, 60.0 / 70.0):
            sharp_no_t += 1.4 * np.exp(-0.5 * ((t - sec) / 0.008) ** 2)

        cfg = ECGConfig(
            sampling_rate=fs,
            detection_cfg=DetectionConfig(collect_diagnostics=True),
        )
        res = analyze_ecg(
            sharp_no_t,
            fs=fs,
            config=cfg,
            multi_lead_signals={"I": sharp_no_t, "II": clean_t},
            auto_select_lead=True,
        )
        self.assertIn("diagnostics", res)
        self.assertIsNotNone(res["diagnostics"]["qrs_lead"])
        self.assertIsNotNone(res["diagnostics"]["delineation_lead"])

        # Backward-compatible None on < 3 leads
        self.assertIsNone(calculate_qt_dispersion({"I": sharp_no_t, "II": clean_t}, fs=fs))

    def test_streaming_auto_lead_and_beat_array_proxy_memory(self):
        # Verify 250,000 beats fit cleanly in 88-byte/beat structured array (~22 MB)
        n_beats = 250_000
        arr = np.zeros(n_beats, dtype=BEAT_DTYPE)
        arr["r_peak_sample"] = np.arange(n_beats, dtype=np.int64) * 400
        arr["rr_sec"] = 0.8
        arr["qt_sec"] = 0.40
        self.assertLess(arr.nbytes, 30 * 1024 * 1024)

        proxy = BeatArrayProxy(arr, fs=500.0, lead_names=["I", "II"], as_classified=False)
        self.assertEqual(len(proxy), n_beats)
        first = proxy[0]
        self.assertEqual(first["beat_index"], 0)
        self.assertAlmostEqual(first["qt_ms"], 400.0, places=3)
        with self.assertRaises(TypeError):
            proxy[0] = {}

        # Multi-lead array streaming with dead Lead 0 -> auto failover to Lead 1
        fs = 250.0
        _, good, _ = generate_synthetic_ecg(duration_sec=16.0, fs=fs, heart_rate_bpm=70.0)
        mat = np.vstack([np.zeros_like(good), good]).astype(np.float32)
        res_s = analyze_ecg_stream(mat, fs=fs, lead="auto", chunk_duration_sec=8.0, overlap_sec=1.0)
        self.assertIsInstance(res_s["beats"], BeatArrayProxy)
        self.assertGreater(len(res_s["beats"]), 10)
        self.assertEqual(res_s["beats"][0]["active_lead_id"], 1)


if __name__ == "__main__":
    unittest.main()
