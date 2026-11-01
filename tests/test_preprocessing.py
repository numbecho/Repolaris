import unittest
import numpy as np
from repolaris.preprocessing.filter import bandpass_filter, notch_filter
from repolaris.preprocessing.baseline import remove_baseline_wander

class TestPreprocessing(unittest.TestCase):
    def setUp(self):
        self.fs = 500.0
        self.t = np.linspace(0, 5, int(5 * self.fs), endpoint=False)
        
    def test_bandpass_attenuates_high_freq(self):
        # 10 Hz signal + 100 Hz high frequency noise
        sig = np.sin(2 * np.pi * 10 * self.t) + np.sin(2 * np.pi * 100 * self.t)
        filtered = bandpass_filter(sig, self.fs)
        
        orig_power = np.var(sig)
        filtered_power = np.var(filtered)
        self.assertLess(filtered_power, orig_power)
        
    def test_remove_baseline_wander(self):
        # 10 Hz signal + slow 0.1 Hz drift
        drift = 2.0 * np.sin(2 * np.pi * 0.1 * self.t)
        sig = np.sin(2 * np.pi * 10 * self.t) + drift
        cleaned = remove_baseline_wander(sig, self.fs)
        
        # Verify low frequency component is suppressed
        self.assertLess(np.max(np.abs(cleaned[-int(self.fs):])), 1.8)

if __name__ == "__main__":
    unittest.main()
