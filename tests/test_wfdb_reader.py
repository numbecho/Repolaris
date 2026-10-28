import unittest
import tempfile
import os
from pathlib import Path
import numpy as np
from repolaris.io.wfdb_reader import read_wfdb

class TestWFDBReader(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.rec_name = "test_record"
        self.hea_path = os.path.join(self.temp_dir.name, f"{self.rec_name}.hea")
        self.dat_path = os.path.join(self.temp_dir.name, f"{self.rec_name}.dat")

        # 2 leads, 500 samples, 250 Hz
        self.fs = 250
        self.n_samples = 500
        t = np.linspace(0, 2, self.n_samples)
        ch0_mv = np.sin(2 * np.pi * 1.5 * t).astype(np.float32)
        ch1_mv = (1.2 * np.cos(2 * np.pi * 1.5 * t)).astype(np.float32)
        self.true_signals = np.stack([ch0_mv, ch1_mv])

        # Write Format 16 .dat file (int16 interleaved, gain=200 counts/mV)
        raw_ch0 = (ch0_mv * 200.0).astype("<i2")
        raw_ch1 = (ch1_mv * 200.0).astype("<i2")
        interleaved = np.empty((self.n_samples, 2), dtype="<i2")
        interleaved[:, 0] = raw_ch0
        interleaved[:, 1] = raw_ch1

        with open(self.dat_path, "wb") as f:
            f.write(interleaved.tobytes())

        # Write .hea file
        header_text = f"""{self.rec_name} 2 {self.fs} {self.n_samples}
{self.rec_name}.dat 16 200.0(0)/mV 16 0 0 0 0 Lead_I
{self.rec_name}.dat 16 200.0(0)/mV 16 0 0 0 0 Lead_II
"""
        with open(self.hea_path, "w", encoding="utf-8") as f:
            f.write(header_text.strip() + "\n")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_read_wfdb_format_16(self):
        rec = read_wfdb(self.hea_path)
        self.assertEqual(rec.record_name, self.rec_name)
        self.assertEqual(rec.sampling_rate, 250.0)
        self.assertEqual(rec.num_signals, 2)
        self.assertEqual(rec.num_samples, 500)
        self.assertEqual(rec.lead_names, ["Lead_I", "Lead_II"])
        np.testing.assert_allclose(rec.signals, self.true_signals, atol=0.01)

if __name__ == "__main__":
    unittest.main()
