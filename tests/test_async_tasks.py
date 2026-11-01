"""Unit tests for asynchronous background tasks, progress callbacks, and UI/CLI progress reporting."""

import io
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import numpy as np

from repolaris.api import StudyAPI, AnalysisAPI, ExportAPI
from repolaris.cli import print_cli_progress
from repolaris.app import MainWindow, BackgroundTaskWorker


class TestAsyncTasksAndProgress(unittest.TestCase):
    def test_study_api_generate_demo_progress(self):
        """Verify StudyAPI.generate_demo_study emits progress callbacks."""
        progress_events = []

        def _cb(fraction: float, message: str) -> None:
            progress_events.append((fraction, message))

        time_vec, lead2, true_r = StudyAPI.generate_demo_study(
            duration_sec=2.0, fs=500.0, heart_rate_bpm=72.0, progress_callback=_cb
        )
        self.assertGreater(len(progress_events), 0)
        self.assertEqual(progress_events[-1][0], 1.0)
        self.assertIn("Benchmark", progress_events[-1][1])
        self.assertEqual(len(time_vec), len(lead2))

    def test_analysis_api_progress(self):
        """Verify AnalysisAPI.analyze_signal reports progress through diagnostic stages."""
        time_vec, lead2, _ = StudyAPI.generate_demo_study(duration_sec=2.0, fs=500.0)
        stages = []

        def _cb(fraction: float, message: str) -> None:
            stages.append((fraction, message))

        res = AnalysisAPI.analyze_signal(lead2, fs=500.0, progress_callback=_cb)
        self.assertIn("summary", res)
        self.assertGreaterEqual(len(stages), 5)
        # Verify monotonically increasing progress
        fractions = [s[0] for s in stages]
        self.assertEqual(fractions, sorted(fractions))
        self.assertEqual(fractions[-1], 1.0)
        self.assertIn("complete", stages[-1][1].lower())

    def test_export_api_and_loader_progress(self):
        """Verify ExportAPI and ecg_loader report progress and decode correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_pecg = os.path.join(tmpdir, "test_study.pecg")
            t, sig, r_peaks = StudyAPI.generate_demo_study(duration_sec=2.0, fs=500.0)

            export_progress = []
            def _exp_cb(fraction: float, message: str) -> None:
                export_progress.append((fraction, message))

            out_path = ExportAPI.export_study_pecg(
                filepath=target_pecg,
                signals=sig,
                sampling_rate=500.0,
                lead_names=["Lead II"],
                compression="deflate",
                progress_callback=_exp_cb,
            )
            self.assertTrue(os.path.exists(out_path))
            self.assertGreater(len(export_progress), 0)
            self.assertEqual(export_progress[-1][0], 1.0)

            # Test load_study_dataset progress
            load_progress = []
            def _load_cb(fraction: float, message: str) -> None:
                load_progress.append((fraction, message))

            signals, fs, meta = StudyAPI.load_study_dataset(out_path, progress_callback=_load_cb)
            self.assertIn("Lead II", signals)
            self.assertEqual(fs, 500.0)
            self.assertGreater(len(load_progress), 0)
            self.assertEqual(load_progress[-1][0], 1.0)

            # Test load_study_file progress
            single_sig, single_fs = StudyAPI.load_study_file(out_path, lead="Lead II", progress_callback=_load_cb)
            self.assertEqual(len(single_sig), len(sig))
            self.assertEqual(single_fs, 500.0)

    def test_cli_progress_bar_output(self):
        """Verify terminal progress bar formatting and completion."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = captured
            print_cli_progress(0.45, "Testing analysis progress...")
            print_cli_progress(1.00, "Task complete.")
        finally:
            sys.stdout = old_stdout

        out = captured.getvalue()
        self.assertIn("45%", out)
        self.assertIn("100%", out)
        self.assertIn("Testing analysis progress...", out)
        self.assertIn("Task complete.", out)

    def test_gui_statusbar_elements_in_xml(self):
        """Verify gui.ui defines QStatusBar named statusbar."""
        ui_path = "src/repolaris/resources/app.ui"
        self.assertTrue(os.path.exists(ui_path))
        tree = ET.parse(ui_path)
        root = tree.getroot()
        statusbars = [w for w in root.iter("widget") if w.get("class") == "QStatusBar"]
        self.assertEqual(len(statusbars), 1)
        self.assertEqual(statusbars[0].get("name"), "statusbar")


    def test_precompile_ui(self):
        """Verify app.ui can be precompiled into ui_app.py."""
        from repolaris.resources import compile_ui, Ui_MainWindow, get_ui_path
        ui_path = get_ui_path("app.ui")
        self.assertTrue(ui_path.exists())

        out_py = compile_ui(ui_path)
        self.assertTrue(out_py.exists())
        self.assertTrue(hasattr(Ui_MainWindow, "setupUi"))
        self.assertTrue(hasattr(Ui_MainWindow, "retranslateUi"))

    def test_mainwindow_status_bar_and_background_worker(self):
        """Verify MainWindow status bar helper methods and background execution."""
        from repolaris.app import HAS_GUI
        if HAS_GUI:
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
            try:
                from PyQt6.QtWidgets import QApplication
                _app = QApplication.instance()
                if _app is None:
                    _app = QApplication(["pytest", "-platform", "offscreen"])
            except Exception as exc:
                self.skipTest(f"Headless display unavailable: {exc}")
                return

        try:
            win = MainWindow()
        except Exception as exc:
            self.skipTest(f"MainWindow initialization skipped in headless container: {exc}")
            return
        self.assertTrue(hasattr(win, "status_bar"))
        self.assertTrue(hasattr(win, "lbl_status_msg"))
        self.assertTrue(hasattr(win, "status_progress"))

        # Test setting progress
        win.set_task_progress(0.65, "Calculating QTc...")
        self.assertEqual(win.status_progress.value(), 65)
        self.assertFalse(win.status_progress.isHidden())
        self.assertEqual(win.lbl_status_msg.text(), "Calculating QTc...")

        # Test finishing task
        win.set_task_finished("Ready")
        self.assertTrue(win.status_progress.isHidden())
        self.assertEqual(win.lbl_status_msg.text(), "Ready")

        # Test _run_background_task
        task_executed = False
        def _dummy_task(progress_callback=None):
            nonlocal task_executed
            task_executed = True
            if progress_callback:
                progress_callback(0.5, "In-flight task...")
            return 42

        result_received = None
        def _on_success(val):
            nonlocal result_received
            result_received = val

        win._run_background_task(_dummy_task, _on_success, initial_msg="Starting dummy task...")
        self.assertTrue(task_executed)
        self.assertEqual(result_received, 42)


if __name__ == "__main__":
    unittest.main()
