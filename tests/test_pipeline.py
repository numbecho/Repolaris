import unittest
from repolaris.utils.signal import generate_synthetic_ecg
from repolaris.detection.pipeline import analyze_ecg

class TestPipeline(unittest.TestCase):
    def test_end_to_end_analysis(self):
        fs = 500.0
        _, sig, _ = generate_synthetic_ecg(duration_sec=8.0, fs=fs, heart_rate_bpm=75.0)
        results = analyze_ecg(sig, fs=fs)
        
        self.assertIn("summary", results)
        self.assertIn("beats", results)
        summary = results["summary"]
        
        self.assertGreater(summary["total_beats"], 6)
        self.assertAlmostEqual(summary["mean_hr_bpm"], 75.0, delta=5.0)
        self.assertGreater(summary["mean_qt_ms"], 300.0)
        self.assertLess(summary["mean_qt_ms"], 500.0)

if __name__ == "__main__":
    unittest.main()
