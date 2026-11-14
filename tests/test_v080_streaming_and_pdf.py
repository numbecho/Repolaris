"""Unit tests for Repolaris v0.8.0 Long-Term Holter Streaming, Clinical PDF Reports & Holter Triage Tab.

Validates:
1. Out-of-core SignalBuffer and np.memmap-backed chunk streaming (open_ecg_buffer, stream_ecg_chunks).
2. Chunked streaming diagnostic pipeline (analyze_ecg_stream) with boundary R-peak deduplication.
3. Multi-page printable clinical PDF report generation (generate_clinical_pdf_report & ExportAPI.export_clinical_pdf).
4. CLI --pdf and --stream flags.
5. Workstation GUI Holter Triage Tab (holter_trends_table, holter_af_table, action_export_pdf).
"""

import os
import tempfile
import unittest
import numpy as np

from repolaris.io import (
    SignalBuffer,
    open_ecg_buffer,
    stream_ecg_chunks,
    generate_clinical_pdf_report,
    save_pecg,
)
from repolaris.detection.pipeline import analyze_ecg, analyze_ecg_stream
from repolaris.api import StudyAPI, AnalysisAPI, ExportAPI
from repolaris.cli import main as cli_main
from repolaris.app import MainWindow, QApplication


class TestVersion080StreamingAndPDF(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.fs = 500.0

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_signal_buffer_and_memmap_streaming(self):
        """Verifies open_ecg_buffer backs large arrays with np.memmap and yields overlapping chunks."""
        npy_path = os.path.join(self.tmp_dir.name, "long_holter.npy")
        # Create 25-second signal (12,500 samples) and set mmap_threshold_samples=5,000
        t = np.linspace(0, 25.0, int(25.0 * 250.0))
        sig = (np.sin(2 * np.pi * 1.2 * t) * 1.0).astype(np.float32)
        np.save(npy_path, sig)

        buf = open_ecg_buffer(npy_path, mmap_threshold_samples=5000)
        self.assertIsInstance(buf, SignalBuffer)
        self.assertTrue(buf.metadata.get("mmap_backed", False))
        self.assertEqual(buf.num_samples, len(sig))

        chunks = list(stream_ecg_chunks(npy_path, chunk_duration_sec=10.0, overlap_sec=2.0))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0]["core_start_sample"], 0)
        self.assertEqual(chunks[0]["core_end_sample"], 2500)
        self.assertEqual(chunks[1]["core_start_sample"], 2500)

    def test_analyze_ecg_stream_boundary_deduplication(self):
        """Verifies analyze_ecg_stream processes overlapping windows and deduplicates boundary R-peaks."""
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=25.0, fs=self.fs, heart_rate_bpm=72.0)

        stream_res = AnalysisAPI.analyze_stream(
            sig,
            fs=self.fs,
            chunk_duration_sec=10.0,
            overlap_sec=2.0,
        )
        self.assertTrue(stream_res.get("streamed", False))
        self.assertGreater(stream_res["summary"]["total_beats"], 20)
        self.assertIn("af_report", stream_res)
        self.assertIn("trends", stream_res)
        # Ensure R-peaks are strictly monotonic with no duplicate peaks within 200ms
        r_peaks = stream_res["r_peaks"]
        diffs = np.diff(r_peaks)
        self.assertTrue(np.all(diffs >= int(0.20 * self.fs)))

    def test_clinical_pdf_report_generation(self):
        """Verifies generate_clinical_pdf_report produces a valid multi-page PDF document."""
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=12.0, fs=self.fs, heart_rate_bpm=75.0)
        res = AnalysisAPI.analyze_signal(sig, fs=self.fs)

        pdf_path = os.path.join(self.tmp_dir.name, "clinical_report.pdf")
        out = ExportAPI.export_clinical_pdf(
            filepath=pdf_path,
            analysis_results=res,
            patient_metadata={"patient_id": "PT-080", "age": 62, "gender": "Male", "indication": "Holter Syncope Evaluation"},
            fs=self.fs,
            lead_name="Lead II",
        )
        self.assertTrue(os.path.isfile(out))
        self.assertGreater(os.path.getsize(out), 5000)
        with open(out, "rb") as f:
            magic = f.read(5)
        self.assertEqual(magic, b"%PDF-")

    def test_cli_pdf_and_stream_options(self):
        """Verifies CLI --pdf and --stream flags execute cleanly."""
        pecg_path = os.path.join(self.tmp_dir.name, "cli_study.pecg")
        pdf_path = os.path.join(self.tmp_dir.name, "cli_report.pdf")

        cli_main(["demo", "--duration", "10", "--export", pecg_path, "--pdf", pdf_path])
        self.assertTrue(os.path.isfile(pecg_path))
        self.assertTrue(os.path.isfile(pdf_path))

        pdf_stream_path = os.path.join(self.tmp_dir.name, "cli_stream_report.pdf")
        cli_main(["analyze", pecg_path, "--stream", "--pdf", pdf_stream_path])
        self.assertTrue(os.path.isfile(pdf_stream_path))

    def test_gui_holter_triage_tab_and_pdf_action(self):
        """Verifies MainWindow initializes Holter Triage tab widgets and PDF export action."""
        _app = QApplication.instance() or QApplication([])
        win = MainWindow()
        try:
            self.assertTrue(hasattr(win, "holter_trends_table"))
            self.assertTrue(hasattr(win, "holter_af_table"))
            self.assertTrue(hasattr(win, "action_export_pdf"))
            self.assertTrue(hasattr(win, "btn_export_pdf"))
            self.assertGreaterEqual(win.tabs.count(), 6)
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
