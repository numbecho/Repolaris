import os
import io
import struct
import tempfile
import zipfile
import unittest
import numpy as np

from repolaris.io.mat_reader import load_mat_ecg, save_mat_ecg
from repolaris.io.e3c_reader import read_e3c
from repolaris.io.ecg_loader import load_ecg_file, load_ecg_dataset


class TestMatAndE3C(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_mat(self):
        mat_path = os.path.join(self.temp_dir.name, "test_record.mat")
        fs = 500.0
        n_samples = 1000
        sig_i = np.sin(np.linspace(0, 10, n_samples))
        sig_ii = np.cos(np.linspace(0, 10, n_samples))
        signals = {"Lead I": sig_i, "Lead II": sig_ii}

        save_mat_ecg(mat_path, signals, fs, metadata={"subject": "Patient_01"})
        loaded = load_mat_ecg(mat_path)

        self.assertIn("Lead I", loaded["signals"])
        self.assertIn("Lead II", loaded["signals"])
        self.assertEqual(loaded["fs"], 500.0)
        self.assertEqual(loaded["samples"], 1000)
        np.testing.assert_allclose(loaded["signals"]["Lead I"], sig_i, rtol=1e-5)

        # Test single lead load via universal router
        lead_i_loaded = load_ecg_file(mat_path, lead_name_or_index="Lead I")
        np.testing.assert_allclose(lead_i_loaded, sig_i, rtol=1e-5)

        # Test dataset load
        all_sig, loaded_fs, meta = load_ecg_dataset(mat_path)
        self.assertEqual(len(all_sig), 2)
        self.assertEqual(loaded_fs, 500.0)

    def test_e3c_reader(self):
        e3c_path = os.path.join(self.temp_dir.name, "record.e3c")
        channels = 2
        samples_per_ch = 500
        total_samples = channels * samples_per_ch

        # Synthesize raw int16 binary data
        raw_ints = (np.sin(np.linspace(0, 20, total_samples)) * 1000).astype(np.int16)
        ecg_bytes = raw_ints.tobytes()

        # Synthesize 2 QRS records: <6IB (25 bytes each)
        # qrson, qrsend, pattern, rpeak, rrprev, rrmean, bclass
        qrs_rec1 = struct.pack("<6IB", 50, 75, 1, 62, 500, 500, 0)
        qrs_rec2 = struct.pack("<6IB", 250, 275, 1, 262, 500, 500, 0)
        qrs_bytes = qrs_rec1 + qrs_rec2

        # Create zip archive
        with zipfile.ZipFile(e3c_path, "w") as zf:
            zf.writestr("current.ECG", ecg_bytes)
            zf.writestr("current.QRS", qrs_bytes)

        e3c_res = read_e3c(e3c_path)
        self.assertIn("Channel 1", e3c_res["signals"])
        self.assertIn("Channel 2", e3c_res["signals"])
        self.assertEqual(e3c_res["samples"], samples_per_ch)
        self.assertEqual(len(e3c_res["annotations"]["rpeak"]), 2)
        self.assertEqual(e3c_res["annotations"]["rpeak"][0], 62)

        # Test loading via universal loader
        ch1 = load_ecg_file(e3c_path, lead_name_or_index=0)
        self.assertEqual(len(ch1), samples_per_ch)


if __name__ == "__main__":
    unittest.main()
