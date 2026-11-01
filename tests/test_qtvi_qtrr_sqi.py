import unittest
import numpy as np

from repolaris.detection.qtvi import resample_berger, compute_qtvi, optimize_alpha
from repolaris.detection.qtrr import fit_qtrr_model
from repolaris.detection.sqi import compute_psqi, compute_bassqi, evaluate_lead_quality
from repolaris.detection.pipeline import analyze_ecg
from repolaris.utils.signal import generate_synthetic_ecg


class TestQTVIQTRRSQI(unittest.TestCase):
    def test_berger_resample(self):
        # 5 beats at ~1 Hz (0, 1.0, 2.05, 3.0, 4.1)
        r_times = np.array([0.0, 1.0, 2.05, 3.0, 4.1])
        t_grid, rrv = resample_berger(r_times, fs_resample=4.0)
        self.assertGreater(len(t_grid), 0)
        self.assertEqual(len(t_grid), len(rrv))
        self.assertTrue(np.all(rrv > 0))

    def test_compute_qtvi(self):
        rr = np.array([0.85, 0.88, 0.82, 0.86, 0.84, 0.87])
        qt = np.array([0.38, 0.39, 0.37, 0.385, 0.38, 0.39])
        qtvi = compute_qtvi(rr, qt)
        self.assertIsInstance(qtvi, float)
        # Should be a negative number typically around -1.0 to -1.5
        self.assertLess(qtvi, 1.0)
        self.assertGreater(qtvi, -5.0)

    def test_qtrr_fit(self):
        rr = np.array([0.7, 0.8, 0.9, 1.0, 1.1])
        # Linear relationship qt = 0.2 * rr + 0.25
        qt = 0.2 * rr + 0.25
        res = fit_qtrr_model(rr, qt, model="linear")
        self.assertAlmostEqual(res["slope"], 0.2, places=4)
        self.assertAlmostEqual(res["intercept"], 0.25, places=4)
        self.assertAlmostEqual(res["pearson_r"], 1.0, places=4)

        # Test predict_fn
        pred = res["predict_fn"]([0.85])
        self.assertAlmostEqual(pred[0], 0.2 * 0.85 + 0.25, places=4)

    def test_sqi_metrics(self):
        fs = 500.0
        t, sig, _ = generate_synthetic_ecg(duration_sec=6.0, fs=fs, heart_rate_bpm=72.0)
        psqi = compute_psqi(sig, fs)
        bassqi = compute_bassqi(sig, fs)
        quality = evaluate_lead_quality(sig, fs)

        self.assertGreaterEqual(psqi, 0.0)
        self.assertLessEqual(psqi, 1.0)
        self.assertGreaterEqual(bassqi, 0.0)
        self.assertLessEqual(bassqi, 1.0)
        self.assertIn(quality["verdict"], ["EXCELLENT", "ACCEPTABLE", "POOR"])

    def test_pipeline_with_qtvi_and_sqi(self):
        fs = 500.0
        t, sig, _ = generate_synthetic_ecg(duration_sec=10.0, fs=fs, heart_rate_bpm=75.0)
        results = analyze_ecg(sig, fs=fs)

        self.assertIn("qtvi", results)
        self.assertIn("qtrr", results)
        self.assertIn("sqi", results)
        self.assertIsNotNone(results["sqi"])
        if results["qtvi"] is not None:
            self.assertIsInstance(results["qtvi"], float)


if __name__ == "__main__":
    unittest.main()
