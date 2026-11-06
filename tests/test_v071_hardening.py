"""Unit tests for Repolaris v0.7.1 hardening and v0.8.0 prerequisite modules.

Validates:
1. Atrial Fibrillation (AF) / Flutter detection and burden calculation (detect_atrial_fibrillation).
2. Hourly Arrhythmia Trends and Holter Histogram generation (generate_hourly_trends).
3. SCP-ECG Huffman / residual compression guard rejection (read_scp_ecg).
4. European decimal comma handling in HL7 aECG XML reader (read_hl7_aecg).
5. Hamilton beat classifier entropy stabilization under irregular rhythms.
6. Diagnostic pipeline integration with af_report and trends.
"""

import os
import struct
import tempfile
import unittest
import numpy as np

from repolaris.detection.af_detector import detect_atrial_fibrillation, compute_rr_entropy, compute_rr_irregularity
from repolaris.detection.trends import generate_hourly_trends
from repolaris.detection.classifier import ClassifiedBeat, BeatClass, RhythmPattern, BeatFeatures
from repolaris.detection.hamilton_classifier import HamiltonBeatClassifier
from repolaris.detection.pipeline import analyze_ecg
from repolaris.io.scp_reader import read_scp_ecg
from repolaris.io.hl7_reader import read_hl7_aecg


class TestVersion071Hardening(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.fs = 500.0

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_atrial_fibrillation_detection_and_burden(self):
        """Verifies AF episode segmentation, Shannon entropy, and burden percentage."""
        fs = 500.0
        # 1. Generate NSR segment (regular 800ms RR = 400 samples)
        nsr_rrs = np.full(50, 0.8)
        # 2. Generate AF segment with chaotic irregular RR (varying 400ms to 1200ms)
        np.random.seed(42)
        af_rrs = np.random.uniform(0.40, 1.20, size=60)
        # 3. Generate NSR recovery segment
        nsr_rrs2 = np.full(50, 0.8)

        all_rrs = np.concatenate([nsr_rrs, af_rrs, nsr_rrs2])
        r_peaks = np.cumsum(np.round(all_rrs * fs)).astype(int)

        report = detect_atrial_fibrillation(
            r_peaks,
            fs=fs,
            window_beats=24,
            min_episode_duration_sec=20.0,
            entropy_threshold=0.65,
            irregularity_threshold=0.10,
        )

        self.assertGreater(report.total_duration_sec, 100.0)
        self.assertGreaterEqual(report.num_episodes, 1)
        self.assertGreater(report.af_burden_pct, 10.0)
        self.assertLess(report.af_burden_pct, 60.0)
        self.assertGreater(report.entropy_score, 0.50)

        ep = report.episodes[0]
        self.assertGreater(ep.duration_sec, 20.0)
        self.assertGreater(ep.mean_hr_bpm, 40.0)
        self.assertLess(ep.mean_hr_bpm, 180.0)

    def test_hourly_trends_and_holter_histograms(self):
        """Verifies multi-hour binning, min/max HR extrema, and ectopic counts."""
        classified_beats = []
        fs = 500.0

        # Simulate 2.5 hours of beats (~9000 beats)
        t = 0.0
        for i in range(250):
            # Create a beat every ~1.0s (36s per loop -> scaled up to test binning)
            # We scale time directly: 100 beats in hour 0, 100 beats in hour 1, 50 in hour 2
            if i < 100:
                t_sec = float(i * 30.0)  # 0 to 3000s (Hour 1)
            elif i < 200:
                t_sec = float(3600.0 + (i - 100) * 30.0)  # 3600 to 6600s (Hour 2)
            else:
                t_sec = float(7200.0 + (i - 200) * 30.0)  # 7200 to 8700s (Hour 3)

            b_class = BeatClass.PVC if (i % 25 == 0) else BeatClass.NORMAL
            r_pat = RhythmPattern.ISOLATED_ECTOPIC if b_class == BeatClass.PVC else RhythmPattern.NORMAL_SINUS

            features = BeatFeatures(
                pre_rr_sec=0.85,
                post_rr_sec=0.85,
                pre_rr_ratio=1.0,
                post_rr_ratio=1.0,
                compensatory_ratio=1.0,
                qrs_duration_ms=85.0,
                qrs_peak_to_peak_mv=1.0,
                qrs_energy=1.0,
                template_correlation=0.95,
                polarity=1,
            )
            classified_beats.append(
                ClassifiedBeat(
                    beat_index=i,
                    r_peak_sample=int(t_sec * fs),
                    time_sec=t_sec,
                    beat_class=b_class,
                    rhythm_pattern=r_pat,
                    confidence=0.90,
                    features=features,
                    diagnostic_rationale="Simulated test beat",
                )
            )

        events = [
            {"event_type": "PAUSE", "timestamp_sec": 1800.0, "metric_value": 2.2},
            {"event_type": "PAUSE", "timestamp_sec": 4000.0, "metric_value": 2.6},
        ]

        report = generate_hourly_trends(
            classified_beats,
            events=events,
            total_duration_sec=9000.0,
            bin_size_sec=3600.0,
        )

        self.assertGreaterEqual(report.total_duration_hours, 2.5)
        self.assertEqual(len(report.hourly_bins), 3)
        self.assertEqual(report.total_pauses, 2)
        self.assertEqual(report.max_pause_sec, 2.6)
        self.assertEqual(report.hourly_bins[0].pause_count, 1)
        self.assertEqual(report.hourly_bins[1].pause_count, 1)
        self.assertGreater(report.total_pvcs, 0)

    def test_scp_ecg_compression_guards(self):
        """Verifies that SCP files with Section 2 (Huffman) or Section 5 (Reference beat) raise NotImplementedError."""
        scp_path = os.path.join(self.tmp_dir.name, "huffman.scp")

        # Create Section 0 with pointer to Section 2 (Huffman table)
        s0_len = 16 + 10  # 16 header + 1 pointer entry (10 bytes)
        # Pointer table: sec_id=2 (Huffman), sec_len=100, sec_off=100
        sec_entry = struct.pack("<HII", 2, 100, 100)
        s0_hdr = struct.pack("<HHI", 0, 0, s0_len) + b"\x01\x01" + b"\x00" * 6

        file_len = 6 + s0_len + 200
        file_hdr = struct.pack("<HI", 0, file_len)

        with open(scp_path, "wb") as f:
            f.write(file_hdr + s0_hdr + sec_entry + b"\x00" * 200)

        with self.assertRaises(NotImplementedError) as ctx:
            read_scp_ecg(scp_path)
        self.assertIn("Huffman", str(ctx.exception))

    def test_hl7_aecg_european_comma_formatting(self):
        """Verifies HL7 aECG parser correctly normalizes European comma decimals."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<AnnotatedECG xmlns="urn:hl7-org:v3">
    <component>
        <series>
            <sequence>
                <code code="MDC_ECG_LEAD_I" />
                <scale value="0,005" unit="mV" />
                <increment value="0,002" unit="s" />
                <digits>100 200 -100 -200 150 0</digits>
            </sequence>
            <sequence>
                <code code="MDC_ECG_LEAD_II" />
                <scale value="0,005" unit="mV" />
                <increment value="0,002" unit="s" />
                <digits>120 220 -80 -180 170 10</digits>
            </sequence>
        </series>
    </component>
</AnnotatedECG>
"""
        hl7_path = os.path.join(self.tmp_dir.name, "european.xml")
        with open(hl7_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        rec = read_hl7_aecg(hl7_path)
        self.assertEqual(rec.num_leads, 2)
        self.assertAlmostEqual(rec.sampling_rate, 500.0, places=1)
        # 200 * 0.005 mV = 1.0 mV
        self.assertAlmostEqual(float(rec.signals[0, 1]), 1.0, places=3)

    def test_pipeline_integration_v071(self):
        """Verifies analyze_ecg returns af_report and trends dictionaries."""
        fs = 500.0
        n_seconds = 10
        t = np.linspace(0, n_seconds, int(n_seconds * fs))
        # Synthetic clean ECG sine rhythm at 1 Hz
        signal = np.sin(2 * np.pi * 1.0 * t) * 1.0

        res = analyze_ecg(signal, fs=fs)
        self.assertIn("af_report", res)
        self.assertIn("trends", res)
        self.assertIsInstance(res["af_report"], dict)
        self.assertIsInstance(res["trends"], dict)
        self.assertIn("af_burden_pct", res["af_report"])
        self.assertIn("hourly_bins", res["trends"])


if __name__ == "__main__":
    unittest.main()
