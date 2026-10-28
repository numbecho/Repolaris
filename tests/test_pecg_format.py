import unittest
import tempfile
import os
import numpy as np
from repolaris.io.pecg_format import save_pecg, load_pecg

class TestPECGFormat(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fs = 500.0
        t = np.linspace(0, 10, 5000)
        lead_i = np.sin(2 * np.pi * 1.2 * t).astype(np.float32)
        lead_ii = (1.5 * np.sin(2 * np.pi * 1.2 * t)).astype(np.float32)
        lead_v5 = (0.8 * np.cos(2 * np.pi * 1.2 * t)).astype(np.float32)
        self.signals = np.stack([lead_i, lead_ii, lead_v5])
        self.lead_names = ["Lead I", "Lead II", "V5"]
        
        self.patient = {
            "age": 64,
            "race": "Hispanic / Latino",
            "sex": "M",
            "indication": "Syncope, evaluate for drug-induced QT prolongation"
        }
        
        self.annotations = {
            "physician_notes": [
                {"author": "Dr. Sergio Sanchez", "comment": "Review prolonged repolarization around beat 5"}
            ],
            "caliper_overrides": [
                {"beat_index": 5, "q_onset_sec": 4.120, "t_end_sec": 4.568}
            ]
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_uncompressed_roundtrip_and_mmap(self):
        filepath = os.path.join(self.temp_dir.name, "uncompressed.pecg")
        save_pecg(
            filepath=filepath,
            signals=self.signals,
            sampling_rate=self.fs,
            lead_names=self.lead_names,
            patient_info=self.patient,
            annotations=self.annotations,
            compression="none"
        )
        
        meta, sigs = load_pecg(filepath, mmap=False)
        self.assertEqual(meta["patient"]["age"], 64)
        self.assertEqual(meta["patient"]["race"], "Hispanic / Latino")
        np.testing.assert_allclose(sigs, self.signals, rtol=1e-5)
        
        meta, mmap_sigs = load_pecg(filepath, mmap=True)
        self.assertIsInstance(mmap_sigs, np.memmap)
        np.testing.assert_allclose(mmap_sigs[:, 500:1000], self.signals[:, 500:1000], rtol=1e-5)

    def test_deflate_compression_roundtrip(self):
        filepath = os.path.join(self.temp_dir.name, "deflate.pecg")
        save_pecg(
            filepath=filepath,
            signals=self.signals,
            sampling_rate=self.fs,
            lead_names=self.lead_names,
            patient_info=self.patient,
            annotations=self.annotations,
            compression="deflate"
        )
        
        meta, sigs = load_pecg(filepath)
        self.assertEqual(meta["patient"]["age"], 64)
        self.assertEqual(meta["patient"]["race"], "Hispanic / Latino")
        self.assertEqual(len(meta["annotations"]["physician_notes"]), 1)
        np.testing.assert_allclose(sigs, self.signals, rtol=1e-5)

if __name__ == "__main__":
    unittest.main()
