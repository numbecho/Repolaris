import unittest
import numpy as np
from repolaris.utils.signal import generate_synthetic_ecg
from repolaris.detection.qrs import detect_r_peaks
from repolaris.detection.q_onset import detect_q_onset
from repolaris.detection.t_end import detect_t_end
from repolaris.detection.pulse_metrics import compute_qtc

class TestDetection(unittest.TestCase):
    def setUp(self):
        self.fs = 500.0
        self.hr = 60.0  # 1 beat per second
        self.t, self.sig, self.true_r = generate_synthetic_ecg(
            duration_sec=6.0, fs=self.fs, heart_rate_bpm=self.hr, noise_std=0.0
        )
        
    def test_r_peak_detection_count(self):
        detected_r = detect_r_peaks(self.sig, self.fs)
        # Expect ~5-6 beats in 6 seconds at 60 BPM
        self.assertGreaterEqual(len(detected_r), 5)
        self.assertLessEqual(len(detected_r), 7)
        
    def test_q_onset_precedes_r_peak(self):
        r_peak = self.true_r[1]
        q_onset = detect_q_onset(self.sig, r_peak, self.fs)
        self.assertLess(q_onset, r_peak)
        self.assertGreater(q_onset, r_peak - int(0.12 * self.fs))
        
    def test_t_end_follows_r_peak(self):
        r_peak = self.true_r[1]
        t_peak, t_end = detect_t_end(self.sig, r_peak, self.fs)
        self.assertGreater(t_peak, r_peak)
        self.assertGreater(t_end, t_peak)
        
    def test_qtc_calculation(self):
        qt_sec = 0.400  # 400 ms
        rr_sec = 1.000  # 60 BPM -> 1 sec RR
        qtc = compute_qtc(qt_sec, rr_sec)
        
        # At RR = 1.0s, QTc Bazett and Fridericia must equal raw QT
        self.assertAlmostEqual(qtc["bazett_ms"], 400.0, places=1)
        self.assertAlmostEqual(qtc["fridericia_ms"], 400.0, places=1)

if __name__ == "__main__":
    unittest.main()
