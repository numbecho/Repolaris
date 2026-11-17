"""Unit tests for Repolaris v0.8.0 Long-Term Holter Streaming, Clinical PDF Reports & Holter Triage Tab.

Validates:
1. Out-of-core SignalBuffer and np.memmap-backed chunk streaming (open_ecg_buffer, stream_ecg_chunks).
2. Chunked streaming diagnostic pipeline (analyze_ecg_stream) with boundary R-peak deduplication.
3. Multi-page printable clinical PDF report generation (generate_clinical_pdf_report & ExportAPI.export_clinical_pdf).
4. CLI --pdf and --stream flags.
5. Workstation GUI Holter Triage Tab (holter_trends_table, holter_af_table, action_export_pdf).
6. Streamed repolarization dynamics (QTVI, QT-RR 10-model restitution, hysteresis) & StudyAPI/AnalysisAPI parity.
"""

import os
import tempfile
import unittest

import numpy as np

from repolaris.api import AnalysisAPI, ExportAPI, StudyAPI
from repolaris.app import MainWindow, QApplication
from repolaris.cli import main as cli_main
from repolaris.detection.annotations import AnnotationManager
from repolaris.detection.pipeline import analyze_ecg, analyze_ecg_stream
from repolaris.detection.sqi import evaluate_lead_quality, rank_leads_two_stage
from repolaris.i18n import set_locale
from repolaris.io import (
    SignalBuffer,
    generate_clinical_pdf_report,
    open_ecg_buffer,
    save_pecg,
    stream_ecg_chunks,
)


class TestVersion080StreamingAndPDF(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.fs = 500.0
        set_locale("en")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_signal_buffer_and_memmap_streaming(self):
        """Verifies open_ecg_buffer backs large arrays with np.memmap and yields overlapping chunks."""
        npy_path = os.path.join(self.tmp_dir.name, "long_holter.npy")
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
        r_peaks = stream_res["r_peaks"]
        diffs = np.diff(r_peaks)
        self.assertTrue(np.all(diffs >= int(0.20 * self.fs)))

    def test_analyze_ecg_stream_repolarization_dynamics(self):
        """Verifies analyze_ecg_stream computes study-wide QTVI, QT-RR restitution, and hysteresis."""
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=20.0, fs=self.fs, heart_rate_bpm=75.0)
        stream_res = analyze_ecg_stream(sig, fs=self.fs, chunk_duration_sec=10.0, overlap_sec=2.0)
        self.assertIsNotNone(stream_res["qtvi"])
        self.assertIsNotNone(stream_res["qtrr"])
        self.assertIsNotNone(stream_res["hysteresis"])
        self.assertIn("qtc_individual_ms", stream_res["qtrr"])
        self.assertIn("optimal_lambda", stream_res["hysteresis"])

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

    def test_clinical_pdf_report_from_streamed_analysis(self):
        """Verifies PDF report generation works seamlessly on streamed analysis output."""
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=15.0, fs=self.fs, heart_rate_bpm=70.0)
        stream_res = analyze_ecg_stream(sig, fs=self.fs, chunk_duration_sec=10.0, overlap_sec=2.0)
        pdf_path = os.path.join(self.tmp_dir.name, "streamed_report.pdf")
        out = generate_clinical_pdf_report(
            filepath=pdf_path,
            analysis_results=stream_res,
            patient_metadata={"patient_id": "STREAM-01", "age": 55, "sex": "F"},
            fs=self.fs,
            lead_name="Lead I",
        )
        self.assertTrue(os.path.isfile(out))
        self.assertGreater(os.path.getsize(out), 5000)

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

    def test_study_api_open_study_buffer(self):
        """Verifies StudyAPI.open_study_buffer returns a valid SignalBuffer."""
        pecg_path = os.path.join(self.tmp_dir.name, "buf_case.pecg")
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=6.0, fs=250.0, heart_rate_bpm=72.0)
        save_pecg(pecg_path, sig[np.newaxis, :], 250.0, ["Lead II"])
        buf = StudyAPI.open_study_buffer(pecg_path, mmap_threshold_samples=500)
        self.assertEqual(buf.fs, 250.0)
        self.assertEqual(buf.lead_names, ["Lead II"])
        sl = buf.get_slice("Lead II", 0, 250)
        self.assertEqual(len(sl), 250)

    def test_study_api_stream_study_chunks(self):
        """Verifies StudyAPI.stream_study_chunks iterates over file windows."""
        pecg_path = os.path.join(self.tmp_dir.name, "chunks_case.pecg")
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=25.0, fs=250.0, heart_rate_bpm=72.0)
        save_pecg(pecg_path, sig[np.newaxis, :], 250.0, ["Lead II"])
        chunks = list(StudyAPI.stream_study_chunks(pecg_path, lead=0, chunk_duration_sec=10.0, overlap_sec=1.0))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0]["fs"], 250.0)

    def test_signal_buffer_index_and_name_lookup(self):
        """Verifies SignalBuffer lead lookup by both integer index and string name."""
        sigs = {
            "Lead I": np.ones(1000, dtype=np.float32),
            "Lead II": np.ones(1000, dtype=np.float32) * 2.0,
        }
        buf = SignalBuffer(signals=sigs, fs=500.0, metadata={})
        self.assertEqual(len(buf.lead_names), 2)
        self.assertEqual(buf.num_samples, 1000)
        self.assertAlmostEqual(buf.duration_sec, 2.0)
        s0 = buf.get_slice(0, 100, 200)
        s1 = buf.get_slice("Lead II", 100, 200)
        self.assertTrue(np.allclose(s0, 1.0))
        self.assertTrue(np.allclose(s1, 2.0))

    def test_signal_buffer_empty_and_single_lead_support(self):
        """Verifies SignalBuffer handles single-lead and empty dicts gracefully."""
        arr = np.linspace(0.0, 1.0, 500, dtype=np.float32)
        buf = SignalBuffer(signals={"Lead I": arr}, fs=250.0, metadata={})
        self.assertEqual(buf.lead_names, ["Lead I"])
        self.assertEqual(buf.num_samples, 500)
        s = buf.get_slice(0, 0, 100)
        self.assertEqual(len(s), 100)
        empty_buf = SignalBuffer(signals={}, fs=250.0, metadata={})
        self.assertEqual(empty_buf.num_samples, 0)

    def test_stream_ecg_from_pecg_file_path(self):
        """Verifies analyze_ecg_stream accepts a file path directly."""
        pecg_path = os.path.join(self.tmp_dir.name, "direct_stream.pecg")
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=12.0, fs=self.fs, heart_rate_bpm=72.0)
        save_pecg(pecg_path, sig[np.newaxis, :], self.fs, ["Lead II"])
        res = analyze_ecg_stream(pecg_path, fs=self.fs, lead="Lead II", chunk_duration_sec=6.0, overlap_sec=1.5)
        self.assertTrue(res["streamed"])
        self.assertGreaterEqual(res["summary"]["total_beats"], 10)

    def test_stream_progress_callback_monotonic(self):
        """Verifies analyze_ecg_stream emits monotonic progress callbacks ending at 1.0."""
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=15.0, fs=self.fs, heart_rate_bpm=72.0)
        progress_steps = []
        analyze_ecg_stream(
            sig,
            fs=self.fs,
            chunk_duration_sec=6.0,
            overlap_sec=1.0,
            progress_callback=lambda p, msg: progress_steps.append((p, msg)),
        )
        self.assertGreaterEqual(len(progress_steps), 2)
        self.assertAlmostEqual(progress_steps[-1][0], 1.0)

    def test_pdf_report_progress_callback(self):
        """Verifies generate_clinical_pdf_report invokes progress callbacks through 1.0."""
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=8.0, fs=self.fs, heart_rate_bpm=72.0)
        res = analyze_ecg(sig, fs=self.fs)
        steps = []
        pdf_path = os.path.join(self.tmp_dir.name, "cb_report.pdf")
        generate_clinical_pdf_report(
            filepath=pdf_path,
            analysis_results=res,
            fs=self.fs,
            progress_callback=lambda p, m: steps.append(p),
        )
        self.assertIn(1.0, steps)

    def test_pdf_report_empty_signal_graceful_fallback(self):
        """Verifies generate_clinical_pdf_report handles empty/minimal results without crashing."""
        pdf_path = os.path.join(self.tmp_dir.name, "empty_report.pdf")
        empty_res = {
            "clean_signal": np.zeros(0, dtype=np.float32),
            "beats": [],
            "events": [],
            "summary": {"total_beats": 0, "mean_hr_bpm": 0.0, "mean_qt_ms": 0.0},
            "af_report": {"af_burden_pct": 0.0, "num_episodes": 0, "longest_episode_sec": 0.0},
            "trends": {"hourly_bins": [], "total_pauses": 0, "max_pause_sec": 0.0},
        }
        out = generate_clinical_pdf_report(pdf_path, empty_res, fs=500.0)
        self.assertTrue(os.path.isfile(out))

    def test_evaluate_lead_quality_keys_consistency(self):
        """Verifies evaluate_lead_quality returns psqi, bassqi, ksqi, ssqi, snr_db, passed_absolute_gate, and verdict."""
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=6.0, fs=self.fs, heart_rate_bpm=72.0)
        sqi = evaluate_lead_quality(sig, fs=self.fs)
        for key in ("psqi", "bassqi", "ksqi", "ssqi", "snr_db", "passed_absolute_gate", "verdict"):
            self.assertIn(key, sqi)

    def test_rank_leads_two_stage_dict_input(self):
        """Verifies rank_leads_two_stage accepts a dictionary of named leads."""
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=6.0, fs=self.fs, heart_rate_bpm=72.0)
        leads = {
            "Lead I": sig,
            "Lead II": sig * 1.1,
            "Flatline": np.zeros_like(sig),
        }
        ranking = rank_leads_two_stage(leads, fs=self.fs)
        self.assertIn(ranking["recommended_lead"], ("Lead I", "Lead II"))
        self.assertIn("Lead I", ranking["passing_leads"])

    def test_annotation_manager_override_audit_trail(self):
        """Verifies AnnotationManager.override_beat_label updates beat label and author."""
        mgr = AnnotationManager()
        mgr.add_annotation(sample=250, timestamp_sec=0.5, label="N", author="AI_DETECTOR")
        updated = mgr.override_beat_label(sample=250, new_label="V", reviewer="Dr. Cardio", notes="Confirmed PVC")
        self.assertIsNotNone(updated)
        self.assertEqual(mgr.annotations[0].label, "V")
        self.assertTrue(mgr.annotations[0].is_manual_override)
        self.assertEqual(mgr.annotations[0].author, "Dr. Cardio")

    def test_af_detection_and_hourly_trends_direct(self):
        """Verifies AnalysisAPI.detect_af and AnalysisAPI.compute_hourly_trends on synthetic beats."""
        _, sig, r_peaks = StudyAPI.generate_demo_study(duration_sec=10.0, fs=self.fs, heart_rate_bpm=72.0)
        af = AnalysisAPI.detect_af(r_peaks, fs=self.fs)
        self.assertEqual(af["num_episodes"], 0)
        res = AnalysisAPI.analyze_signal(sig, fs=self.fs)
        trends = AnalysisAPI.compute_hourly_trends(
            res["classified_beats"],
            events=res["events"],
            total_duration_sec=10.0,
        )
        self.assertGreaterEqual(len(trends["hourly_bins"]), 1)

    def test_gui_seek_to_time_sec_and_populate_holter_tab(self):
        """Verifies MainWindow._update_cards_and_tables populates Holter, Overview (HRV/HRT/TWA), and Metadata tables."""
        set_locale("en")
        _app = QApplication.instance() or QApplication([])
        win = MainWindow()
        try:
            self.assertFalse(hasattr(win, "nonexistent_fake_widget_xyz"))
            _, sig, _ = StudyAPI.generate_demo_study(duration_sec=10.0, fs=self.fs, heart_rate_bpm=72.0)
            res = AnalysisAPI.analyze_signal(sig, fs=self.fs)
            win.signal_data = sig
            win.fs = self.fs
            win.current_metadata = {"patient_id": "PT-900", "age": 61, "gender": "Female", "format": "ISHNE 1.0"}
            win.analysis_results = res
            win._update_cards_and_tables()
            win._on_holter_hour_clicked(0, 0)
            self.assertIn("Holter Summary", win.lbl_holter_summary_banner.text())
            self.assertIn("HRV:", win.lbl_adv_hrv.text())
            self.assertIn("Microvolt TWA:", win.lbl_adv_twa.text())
            self.assertEqual(win.meta_table_a.rowCount(), 4)
            self.assertEqual(win.meta_table_b.rowCount(), 8)
        finally:
            win.close()

    def test_cli_export_subcommand(self):
        """Verifies CLI export subcommand creates a .pecg bundle."""
        npy_path = os.path.join(self.tmp_dir.name, "raw_input.npy")
        pecg_out = os.path.join(self.tmp_dir.name, "exported_bundle.pecg")
        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=6.0, fs=250.0, heart_rate_bpm=70.0)
        np.save(npy_path, sig)
        cli_main([
            "export",
            npy_path,
            pecg_out,
            "--compression",
            "deflate",
        ])
        self.assertTrue(os.path.isfile(pecg_out))



    def test_ui_ux_audit_all_7_fixes(self) -> None:
        """Verifies all 7 UI/UX vs. documentation fixes (caliper persistence, beat reclassification propagation, RR HUD, 8-column tables, and 5-language i18n)."""
        from repolaris.app import MainWindow
        from repolaris.i18n import SUPPORTED_LANGUAGES

        win = MainWindow()
        self.assertIsNotNone(win.analysis_results)

        # 1. RR HUD readout present and populated on beat selection
        self.assertTrue(hasattr(win, "lbl_tag_rr"))
        self.assertTrue(hasattr(win, "lbl_cal_rr"))
        win._select_beat(1)
        self.assertIn("ms", win.lbl_cal_rr.text())

        # 2. Manual caliper drag persists into analysis_results["beats"], summary, card_qtc, and beat_table (col 6 & 7)
        win._on_caliper_dragged(1.000, 1.440)  # 440 ms QT
        b1 = win.analysis_results["beats"][1]
        self.assertAlmostEqual(b1["qt_ms"], 440.0, places=1)
        self.assertEqual(win.beat_table.item(1, 6).text(), "440")
        self.assertIn("ms", win.card_qtc.val_lbl.text())

        # 3. Beat reclassification propagates to ectopic_summary, rhythm patterns, HRV/HRT, and beat_table
        win.reclassify_beat(2, "V")
        self.assertEqual(win.analysis_results["beats"][2]["beat_class"], "V")
        self.assertGreaterEqual(win.analysis_results["ectopic_summary"]["pvc_count"], 1)
        self.assertGreater(win.analysis_results["ectopic_summary"]["ectopic_burden_pct"], 0.0)
        self.assertEqual(win.beat_table.item(2, 2).text(), "V")

        # 4, 5, 6. Verify 8-column beat_table, 8-column qtrr_models_table, and 8-column holter_af_table
        self.assertIsNotNone(win.beat_table.item(0, 3))  # Pattern
        self.assertIsNotNone(win.beat_table.item(0, 4))  # RR (ms)
        self.assertIsNotNone(win.beat_table.item(0, 5))  # HR (BPM)
        self.assertIsNotNone(win.beat_table.item(0, 6))  # QT (ms)
        self.assertIsNotNone(win.beat_table.item(0, 7))  # QTc (ms)
        self.assertIsNotNone(win.qtrr_models_table.item(0, 2))  # Slope
        self.assertIsNotNone(win.qtrr_models_table.item(0, 3))  # Pearson r
        self.assertIsNotNone(win.qtrr_models_table.item(0, 6))  # AIC
        self.assertIsNotNone(win.qtrr_models_table.item(0, 7))  # QTc,ind

        # 7. Verify all 5 languages retranslate cleanly without hardcoded English fallbacks
        for lang_code in SUPPORTED_LANGUAGES:
            win.set_language(lang_code)
            self.assertTrue(len(win.card_qtd.title_lbl.text()) > 0)
            self.assertTrue(len(win.lbl_adv_hyst.text()) > 0)
        win.set_language("en")



    def test_keyboard_navigation_aami_hotkeys_and_ectopic_markers(self) -> None:
        """Verifies Left/Right beat navigation, N/V/S/F/Q single-key hotkeys, and color-coded ectopic R-peak markers."""
        from repolaris.app import MainWindow, Qt

        class _DummyKeyEvent:
            def __init__(self, key_code: int = 0, text_char: str = "") -> None:
                self._k = key_code
                self._t = text_char
            def key(self) -> int:
                return self._k
            def text(self) -> str:
                return self._t

        win = MainWindow()
        win._select_beat(0)
        self.assertEqual(win.current_beat_index, 0)

        # Step forward with Right arrow key and next_beat()
        win.keyPressEvent(_DummyKeyEvent(key_code=Qt.Key.Key_Right))
        self.assertEqual(win.current_beat_index, 1)
        win.next_beat()
        self.assertEqual(win.current_beat_index, 2)

        # Step backward with Left arrow key
        win.keyPressEvent(_DummyKeyEvent(key_code=Qt.Key.Key_Left))
        self.assertEqual(win.current_beat_index, 1)

        # Reclassify active beat (beat #1) to PVC ("V") via single-key hotkey
        win.keyPressEvent(_DummyKeyEvent(text_char="v"))
        self.assertEqual(win.analysis_results["beats"][1]["beat_class"], "V")
        self.assertEqual(win.ecg_plot.last_r_peak_classes[1], "V")
        self.assertEqual(win.ecg_plot.last_r_peak_colors[1], "#f87171")
        self.assertGreaterEqual(len(win.ecg_plot.ectopic_text_items), 1)

        # Reclassify active beat to PAC ("S") and back to Normal ("N")
        win.keyPressEvent(_DummyKeyEvent(text_char="S"))
        self.assertEqual(win.analysis_results["beats"][1]["beat_class"], "S")
        self.assertEqual(win.ecg_plot.last_r_peak_colors[1], "#fbbf24")
        win.keyPressEvent(_DummyKeyEvent(text_char="N"))
        self.assertEqual(win.analysis_results["beats"][1]["beat_class"], "N")


if __name__ == "__main__":
    unittest.main()
