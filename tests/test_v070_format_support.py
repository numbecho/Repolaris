"""Unit tests for Repolaris v0.7.0 Open International Format Ingestion.

Validates:
1. DICOM Waveform (SOP Class 1.2.840.10008.5.1.4.1.1.9.1.1) parsing and physical mV scaling.
2. HL7 Annotated ECG XML (ANSI/HL7 aECG) format decoding and lead metadata.
3. SCP-ECG (CEN EN 1064 / ISO 13713) Section 0, 3, and 6 rhythm decoding.
4. Format sniffing state machine (sniff_ecg_format).
5. Hamilton (2002) OSEA template matching classifier.
"""

import os
import struct
import tempfile
import unittest
import numpy as np

from repolaris.io import (
    load_ecg_dataset,
    load_ecg_file,
    sniff_ecg_format,
    read_dicom_waveform,
    is_dicom_file,
    read_hl7_aecg,
    is_hl7_xml,
    read_scp_ecg,
    is_scp_file,
)
from repolaris.detection.hamilton_classifier import HamiltonBeatClassifier
from repolaris.detection.classifier import BeatClass


class TestVersion070FormatSupport(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.fs = 500.0

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_dicom_waveform_roundtrip_and_sniffing(self):
        """Verifies synthetic DICOM Waveform file generation, sniffing, and calibrated mV reading."""
        dcm_path = os.path.join(self.tmp_dir.name, "test_ecg.dcm")

        # Create minimal synthetic DICOM file with preamble + DICM + WaveformData Tag (5400, 1010)
        n_channels = 12
        n_samples = 500
        # Generate 16-bit signed integers (e.g. 1 mV = 200 LSB)
        sine = (np.sin(np.linspace(0, 4 * np.pi, n_samples)) * 200).astype("<i2")
        multiplexed = np.repeat(sine[:, np.newaxis], n_channels, axis=1).reshape(-1)

        with open(dcm_path, "wb") as f:
            f.write(b"\x00" * 128)
            f.write(b"DICM")
            tag_bytes = b"\x00\x54\x10\x10"
            raw_data = multiplexed.tobytes()
            vr = b"OW\x00\x00"
            length = struct.pack("<I", len(raw_data))
            f.write(tag_bytes + vr + length + raw_data)

        self.assertTrue(is_dicom_file(dcm_path))
        self.assertEqual(sniff_ecg_format(dcm_path), "dicom")

        rec = read_dicom_waveform(dcm_path)
        self.assertEqual(rec.num_channels, n_channels)
        self.assertEqual(rec.num_samples, n_samples)
        self.assertAlmostEqual(float(np.max(rec.signals[0])), 1.0, places=1)

        # Test universal loader dispatch
        sigs, fs, meta = load_ecg_dataset(dcm_path)
        self.assertEqual(len(sigs), n_channels)
        self.assertEqual(fs, 500.0)
        self.assertIn("DICOM", meta["format"])

    def test_hl7_aecg_xml_parsing(self):
        """Verifies HL7 aECG XML parsing, increment frequency, and voltage scaling."""
        xml_path = os.path.join(self.tmp_dir.name, "test_study.aecg")

        raw_digits = "0 100 200 150 50 -50 -150 -100 0"
        hl7_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<AnnotatedECG xmlns="urn:hl7-org:v3">
  <clinicalDocument>
    <recordTarget>
      <patientPerson><name>DOE, JOHN</name></patientPerson>
    </recordTarget>
  </clinicalDocument>
  <component>
    <series>
      <sequence>
        <code code="MDC_ECG_LEAD_I"/>
        <scale value="0.005" unit="mV"/>
        <increment value="0.002" unit="s"/>
        <digits>{raw_digits}</digits>
      </sequence>
      <sequence>
        <code code="MDC_ECG_LEAD_II"/>
        <scale value="0.005" unit="mV"/>
        <increment value="0.002" unit="s"/>
        <digits>{raw_digits}</digits>
      </sequence>
    </series>
  </component>
</AnnotatedECG>
"""
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(hl7_content)

        self.assertTrue(is_hl7_xml(xml_path))
        self.assertEqual(sniff_ecg_format(xml_path), "hl7")

        rec = read_hl7_aecg(xml_path)
        self.assertEqual(rec.patient_name, "DOE, JOHN")
        self.assertEqual(rec.num_leads, 2)
        self.assertEqual(rec.sampling_rate, 500.0)
        self.assertEqual(rec.lead_names, ["Lead I", "Lead II"])
        self.assertAlmostEqual(float(np.max(rec.signals[0])), 1.0, places=2)

        # Test universal loader dispatch
        sigs, fs, meta = load_ecg_dataset(xml_path)
        self.assertIn("Lead I", sigs)
        self.assertEqual(fs, 500.0)
        self.assertIn("HL7", meta["format"])

    def test_scp_ecg_binary_parsing(self):
        """Verifies SCP-ECG (EN 1064) Section 0, 3, and 6 binary parsing."""
        scp_path = os.path.join(self.tmp_dir.name, "test_study.scp")

        n_leads = 2
        n_samples = 10
        samples_lead1 = (np.ones(n_samples, dtype="<i2") * 200).tobytes()
        samples_lead2 = (np.ones(n_samples, dtype="<i2") * 100).tobytes()

        s6_header = struct.pack("<HHBB", 5000, 2000, 0, 0)
        s6_lead_lens = struct.pack("<HH", len(samples_lead1), len(samples_lead2))
        s6_body = s6_header + s6_lead_lens + samples_lead1 + samples_lead2
        s6_sec = struct.pack("<HHIBB6s", 0, 6, 16 + len(s6_body), 10, 10, b"\x00" * 6) + s6_body

        s3_header = struct.pack("<BB2s", n_leads, 0, b"\x00\x00")
        s3_leads = struct.pack("<IIB", 1, n_samples, 1) + struct.pack("<IIB", 1, n_samples, 2)
        s3_body = s3_header + s3_leads
        s3_sec = struct.pack("<HHIBB6s", 0, 3, 16 + len(s3_body), 10, 10, b"\x00" * 6) + s3_body

        s0_len = 16 + 20
        s3_file_off = 6 + s0_len + 1
        s6_file_off = s3_file_off + len(s3_sec)
        s0_entry3 = struct.pack("<HII", 3, len(s3_sec), s3_file_off)
        s0_entry6 = struct.pack("<HII", 6, len(s6_sec), s6_file_off)
        s0_sec = struct.pack("<HHIBB6s", 0, 0, s0_len, 10, 10, b"\x00" * 6) + s0_entry3 + s0_entry6

        total_file_len = 6 + len(s0_sec) + len(s3_sec) + len(s6_sec)
        file_header = struct.pack("<HI", 0, total_file_len)

        with open(scp_path, "wb") as f:
            f.write(file_header + s0_sec + s3_sec + s6_sec)

        self.assertTrue(is_scp_file(scp_path))
        self.assertEqual(sniff_ecg_format(scp_path), "scp")

        rec = read_scp_ecg(scp_path)
        self.assertEqual(rec.num_leads, 2)
        self.assertEqual(rec.sampling_rate, 500.0)
        self.assertEqual(rec.lead_names, ["Lead I", "Lead II"])
        self.assertAlmostEqual(float(rec.signals[0][0]), 1.0, places=2)
        self.assertAlmostEqual(float(rec.signals[1][0]), 0.5, places=2)

        sigs, fs, meta = load_ecg_dataset(scp_path)
        self.assertIn("Lead I", sigs)
        self.assertEqual(fs, 500.0)
        self.assertIn("SCP", meta["format"])

    def test_hamilton_beat_classifier(self):
        """Verifies Patrick Hamilton (2002) OSEA template matching on normal and ectopic beats."""
        fs = 500.0
        n_beats = 15
        rr_samples = int(fs * 0.8)

        time_vec = np.arange(n_beats * rr_samples) / fs
        signal = np.zeros_like(time_vec)
        r_peaks = []

        for i in range(n_beats):
            r_idx = i * rr_samples + int(0.2 * fs)
            r_peaks.append(r_idx)
            signal[r_idx - 10 : r_idx + 10] += np.hanning(20) * 1.5

        pvc_idx = int(r_peaks[6] - 0.25 * fs)
        r_peaks[6] = pvc_idx
        signal[pvc_idx - 30 : pvc_idx + 30] += -np.hanning(60) * 2.2

        clf = HamiltonBeatClassifier(fs=fs)
        classified_beats, summary = clf.classify_recording(signal, np.array(r_peaks))

        self.assertEqual(len(classified_beats), n_beats)
        self.assertEqual(summary["total_beats"], n_beats)
        self.assertGreaterEqual(summary["template_cluster_count"], 1)

        self.assertEqual(classified_beats[6].beat_class, BeatClass.PVC)
        self.assertIn("Hamilton OSEA", classified_beats[6].diagnostic_rationale)
        self.assertEqual(classified_beats[0].beat_class, BeatClass.NORMAL)


if __name__ == "__main__":
    unittest.main()
