import json
import os
import tempfile
import unittest

import numpy as np

from repolaris.io.pecg_format import load_pecg, save_pecg


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
            "indication": "Syncope, evaluate for drug-induced QT prolongation",
            "pacemaker": "VVI",
        }

        self.annotations = {
            "physician_notes": [
                {
                    "author": "Dr. Sergio Sanchez",
                    "comment": "Review prolonged repolarization around beat 5",
                }
            ],
            "caliper_overrides": [{"beat_index": 5, "q_onset_sec": 4.120, "t_end_sec": 4.568}],
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
            compression="none",
        )

        meta, sigs = load_pecg(filepath, mmap=False)
        self.assertEqual(meta["patient"]["age"], 64)
        self.assertEqual(meta["patient"]["race"], "Hispanic / Latino")
        self.assertEqual(meta["patient"]["pacemaker"], "VVI")
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
            compression="deflate",
        )

        meta, sigs = load_pecg(filepath)
        self.assertEqual(meta["patient"]["age"], 64)
        self.assertEqual(meta["patient"]["race"], "Hispanic / Latino")
        self.assertEqual(meta["patient"]["pacemaker"], "VVI")
        self.assertEqual(len(meta["annotations"]["physician_notes"]), 1)
        np.testing.assert_allclose(sigs, self.signals, rtol=1e-5)

    def test_security_sanitization_rejections(self):
        import struct

        # 1. Rejects file smaller than 12 bytes
        p_short = os.path.join(self.temp_dir.name, "too_short.pecg")
        with open(p_short, "wb") as f:
            f.write(b"PECG1234")
        with self.assertRaises(ValueError) as cm:
            load_pecg(p_short)
        self.assertIn("smaller than the 12-byte header", str(cm.exception))

        # 2. Rejects corrupt magic bytes
        p_bad_magic = os.path.join(self.temp_dir.name, "bad_magic.pecg")
        with open(p_bad_magic, "wb") as f:
            f.write(b"XXXX" + struct.pack("<HBB I", 1, 0, 0, 0))
        with self.assertRaises(ValueError) as cm:
            load_pecg(p_bad_magic)
        self.assertIn("Expected magic b'PECG'", str(cm.exception))

        # 3. Rejects metadata block exceeding 10 MB ceiling
        p_huge_meta = os.path.join(self.temp_dir.name, "huge_meta.pecg")
        with open(p_huge_meta, "wb") as f:
            f.write(b"PECG" + struct.pack("<HBB I", 1, 0, 0, 20 * 1024 * 1024))
        with self.assertRaises(ValueError) as cm:
            load_pecg(p_huge_meta)
        self.assertIn("exceeds the 10 MB safety ceiling", str(cm.exception))

        # 4. Rejects metadata block extending beyond EOF
        p_eof_meta = os.path.join(self.temp_dir.name, "eof_meta.pecg")
        with open(p_eof_meta, "wb") as f:
            f.write(b"PECG" + struct.pack("<HBB I", 1, 0, 0, 5000))
            f.write(b"truncated")
        with self.assertRaises(ValueError) as cm:
            load_pecg(p_eof_meta)
        self.assertIn("extends beyond end-of-file", str(cm.exception))

        # 5. Rejects invalid channel count (> 64)
        p_bad_ch = os.path.join(self.temp_dir.name, "bad_ch.pecg")
        bad_meta = json.dumps(
            {"recording": {"num_channels": 256, "num_samples": 100, "sampling_rate": 250.0}}
        ).encode("utf-8")
        with open(p_bad_ch, "wb") as f:
            f.write(b"PECG" + struct.pack("<HBB I", 1, 0, 0, len(bad_meta)))
            f.write(bad_meta)
        with self.assertRaises(ValueError) as cm:
            load_pecg(p_bad_ch)
        self.assertIn("Invalid channel count", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
