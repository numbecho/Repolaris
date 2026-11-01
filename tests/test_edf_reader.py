import unittest
import tempfile
import os
import numpy as np
from repolaris.io.edf_reader import read_edf

class TestEDFReader(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.edf_path = os.path.join(self.temp_dir.name, "test_recording.edf")

        # 2 channels: 1 second records, 250 Hz = 250 samples per record. 2 records total (2 sec)
        num_signals = 2
        num_records = 2
        rec_duration = 1.0
        samples_per_rec = 250

        # Construct 256-byte main header
        main_hdr = (
            "0       ".encode("ascii") +                      # version (8)
            "PATIENT_ID_42".ljust(80).encode("ascii") +       # patient (80)
            "RECORDING_01".ljust(80).encode("ascii") +        # rec id (80)
            "27.10.26".encode("ascii") +                      # date (8)
            "14.30.00".encode("ascii") +                      # time (8)
            str(256 + 256 * num_signals).ljust(8).encode("ascii") + # header bytes (8)
            "".ljust(44).encode("ascii") +                    # reserved (44)
            str(num_records).ljust(8).encode("ascii") +       # num records (8)
            str(rec_duration).ljust(8).encode("ascii") +      # duration (8)
            str(num_signals).ljust(4).encode("ascii")         # num signals (4)
        )

        # Construct channel headers
        labels = "ECG I           ECG II          ".encode("ascii")
        transducers = ("".ljust(80) + "".ljust(80)).encode("ascii")
        phys_dims = "mV      mV      ".encode("ascii")
        phys_min = "-5.0    -5.0    ".encode("ascii")
        phys_max = "5.0     5.0     ".encode("ascii")
        dig_min = "-32768  -32768  ".encode("ascii")
        dig_max = "32767   32767   ".encode("ascii")
        prefilter = ("".ljust(80) + "".ljust(80)).encode("ascii")
        nr_samples = "250     250     ".encode("ascii")
        reserved = ("".ljust(32) + "".ljust(32)).encode("ascii")

        channel_hdrs = labels + transducers + phys_dims + phys_min + phys_max + dig_min + dig_max + prefilter + nr_samples + reserved

        # Data payload: 2 records. In each record: 250 samples of ch0, then 250 samples of ch1
        t = np.linspace(0, 1, samples_per_rec, endpoint=False)
        rec1_ch0 = (np.sin(2 * np.pi * 2.0 * t) * (32767 / 5.0)).astype("<i2")
        rec1_ch1 = (np.cos(2 * np.pi * 2.0 * t) * (32767 / 5.0)).astype("<i2")
        rec2_ch0 = (np.sin(2 * np.pi * 2.0 * (t + 1.0)) * (32767 / 5.0)).astype("<i2")
        rec2_ch1 = (np.cos(2 * np.pi * 2.0 * (t + 1.0)) * (32767 / 5.0)).astype("<i2")

        data_bytes = rec1_ch0.tobytes() + rec1_ch1.tobytes() + rec2_ch0.tobytes() + rec2_ch1.tobytes()

        with open(self.edf_path, "wb") as f:
            f.write(main_hdr)
            f.write(channel_hdrs)
            f.write(data_bytes)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_read_edf(self):
        rec = read_edf(self.edf_path)
        self.assertEqual(rec.patient_id, "PATIENT_ID_42")
        self.assertEqual(rec.num_signals, 2)
        self.assertEqual(rec.duration_sec, 2.0)
        self.assertIn("ECG I", rec.lead_names[0])
        self.assertEqual(rec.signals.shape, (2, 500))
        # Verify physical scale amplitude is roughly in [-1.0, 1.0] mV
        self.assertAlmostEqual(np.max(rec.signals[0]), 1.0, places=1)

if __name__ == "__main__":
    unittest.main()
