import unittest
import tempfile
import os
from datetime import date, time
import numpy as np
from repolaris.io.ishne_reader import write_ishne, read_ishne

class TestISHNEReader(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.filepath = os.path.join(self.temp_dir.name, "test_holter.ecg")
        
        # 3 leads: Lead I (code 5), Lead II (code 6), V5 (code 15)
        # 1000 samples at 200 Hz = 5 seconds
        self.fs = 200
        self.lead_codes = [5, 6, 15]
        t = np.linspace(0, 5, 1000)
        ch0 = np.sin(2 * np.pi * 1.0 * t).astype(np.float32)
        ch1 = (1.5 * np.sin(2 * np.pi * 1.0 * t)).astype(np.float32)
        ch2 = (0.5 * np.cos(2 * np.pi * 1.0 * t)).astype(np.float32)
        self.signals = np.stack([ch0, ch1, ch2])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ishne_roundtrip(self):
        out = write_ishne(
            filepath=self.filepath,
            signals_mv=self.signals,
            sampling_rate=self.fs,
            lead_codes=self.lead_codes,
            patient_id="PATIENT-9982",
            first_name="John",
            last_name="Doe",
            sex_code=1,  # Male
            race_code=1, # Caucasian
            record_date=date(2026, 10, 27),
            start_time=time(14, 30, 0),
            clinical_notes="24-hour ambulatory Holter recording."
        )
        self.assertTrue(os.path.exists(out))

        record = read_ishne(out)
        self.assertEqual(record.patient_id, "PATIENT-9982")
        self.assertEqual(record.first_name, "John")
        self.assertEqual(record.sex, "Male")
        self.assertEqual(record.race, "Caucasian")
        self.assertEqual(record.sampling_rate, 200.0)
        self.assertEqual(record.num_leads, 3)
        self.assertEqual(record.lead_names, ["Lead_I", "Lead_II", "V5"])
        self.assertEqual(record.total_samples, 1000)
        self.assertIn("ambulatory Holter", record.clinical_notes)

        # Check signal values with quantization tolerance (5 uV = 0.005 mV resolution)
        np.testing.assert_allclose(record.signals, self.signals, atol=0.01)

if __name__ == "__main__":
    unittest.main()
