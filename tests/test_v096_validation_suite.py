"""Comprehensive verification suite for Repolaris v0.9.6 Pre-1.0 Validation & Cohort Pillars.

Tests:
1. ANSI/AAMI EC57 (`bxb`) 1-to-1 monotonic beat matching, 150 ms tolerance window, learning period,
   and 5x5 AAMI classification confusion matrix (N, S, V, F, Q).
2. Common Standards for Quantitative Electrocardiography (CSE) / PhysioNet QTDB fiducial boundary
   delineation verification and episode (`epi`) overlap evaluation + synthetic self-certification.
3. Circadian Day/Night (Diurnal vs. Nocturnal) Holter repolarization stratification, nocturnal HR
   dipping categories, nocturnal QTcF lengthening (LQT2/LQT3 pattern), and diurnal QT-RR slope.
4. Headless Multi-File Cohort Batch Runner (`BatchAPI.analyze_directory`) with CSV/JSON export and
   per-file fault isolation on corrupted inputs.
5. Extensible Research Algorithm & Biomarker Plugin Registry (`PluginRegistry`, `@register_biomarker`,
   and fault-isolated execution inside `analyze_ecg` and `analyze_ecg_stream`).
6. End-to-end CLI (`benchmark`, `batch`) and Workstation GUI (`lbl_adv_circadian`) integration.
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import repolaris
from repolaris.api import AnalysisAPI, BatchAPI, ExportAPI, StudyAPI
from repolaris.app import MainWindow, QApplication
from repolaris.benchmarks.ec57 import (
    evaluate_episode_overlap_ec57,
    evaluate_fiducial_delineation_cse,
    evaluate_qrs_and_classification_ec57,
    run_synthetic_self_certification,
)
from repolaris.cli import main as cli_main
from repolaris.detection.circadian import analyze_circadian_repolarization
from repolaris.plugins import (
    clear_registered_plugins,
    get_registered_plugins,
    register_biomarker,
    register_qrs_detector,
    register_t_end_delineator,
)


class TestV096ValidationSuite(unittest.TestCase):
    """Verifies all 4 v0.9.6 pre-1.0 validation, circadian, batch, and plugin pillars."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self) -> None:
        clear_registered_plugins()

    def test_aami_ec57_bxb_matching_one_to_one_and_confusion_matrix(self) -> None:
        """Verifies 1-to-1 monotonic AAMI EC57 bxb beat matching, doublet FP rejection, and 5x5 confusion matrix."""
        fs = 500.0
        # 5 reference beats at 1.0s, 2.0s, 3.0s, 4.0s, 5.0s
        ref_samples = [500, 1000, 1500, 2000, 2500]
        ref_classes = ["N", "N", "V", "S", "N"]

        # Test detections:
        # - 510 (+20 ms from beat 0 -> TP)
        # - 535 (+70 ms doublet near beat 0 -> must NOT double-match beat 0; counted as 1 FP!)
        # - 995 (-10 ms from beat 1 -> TP)
        # - 1515 (+30 ms from beat 2 -> TP, classified as V)
        # - beat 3 (2000) missed -> 1 FN
        # - 2505 (+10 ms from beat 4 -> TP, misclassified as S instead of N)
        test_samples = [510, 535, 995, 1515, 2505]
        test_classes = ["N", "N", "N", "V", "S"]

        res = evaluate_qrs_and_classification_ec57(
            ref_samples=ref_samples,
            test_samples=test_samples,
            fs=fs,
            ref_classes=ref_classes,
            test_classes=test_classes,
            match_window_ms=150.0,
        )
        self.assertEqual(res["tp"], 4)
        self.assertEqual(res["fp"], 1)
        self.assertEqual(res["fn"], 1)
        self.assertAlmostEqual(res["sensitivity_pct"], 80.0, places=2)
        self.assertAlmostEqual(res["positive_predictivity_pct"], 80.0, places=2)
        self.assertEqual(res["confusion_matrix"]["N"]["N"], 2)
        self.assertEqual(res["confusion_matrix"]["N"]["S"], 1)
        self.assertEqual(res["confusion_matrix"]["V"]["V"], 1)
        self.assertEqual(res["per_class_metrics"]["V"]["sensitivity_pct"], 100.0)

    def test_cse_fiducial_delineation_and_ec57_episode_overlap(self) -> None:
        """Verifies CSE referee tolerance checking, EC57 episode overlap, and synthetic self-certification."""
        fs = 500.0
        ref_fids = {
            "q_onset": [480, 980, 1480, 1980, 2480],
            "j_point": [520, 1020, 1520, 2020, 2520],
            "t_end": [650, 1150, 1650, 2150, 2650],
        }
        # Tight delineation errors (+2 ms, -2 ms, 0 ms -> SD well below CSE limits)
        test_fids_good = {
            "q_onset": [481, 979, 1480, 1981, 2479],
            "j_point": [521, 1019, 1520, 2022, 2519],
            "t_end": [652, 1148, 1651, 2149, 2650],
        }
        cse_ok = evaluate_fiducial_delineation_cse(ref_fids, test_fids_good, fs=fs)
        self.assertTrue(cse_ok["all_within_cse_limits"])
        self.assertTrue(cse_ok["fiducials"]["q_onset"]["within_cse_tolerance"])

        # Excessive Q-onset jitter (+/- 20 samples = +/- 40 ms -> SD > 6.5 ms CSE limit)
        test_fids_bad = {
            "q_onset": [460, 1000, 1460, 2000, 2460],
            "j_point": [520, 1020, 1520, 2020, 2520],
            "t_end": [650, 1150, 1650, 2150, 2650],
        }
        cse_bad = AnalysisAPI.evaluate_cse_fiducials(ref_fids, test_fids_bad, fs=fs)
        self.assertFalse(cse_bad["all_within_cse_limits"])
        self.assertFalse(cse_bad["fiducials"]["q_onset"]["within_cse_tolerance"])

        # Episode overlap (epi): ref [10s, 50s], test [15s, 55s] over 100s recording
        epi_res = evaluate_episode_overlap_ec57(
            ref_episodes=[(10.0, 50.0)],
            test_episodes=[(15.0, 55.0)],
            total_duration_sec=100.0,
        )
        self.assertEqual(epi_res["episode_sensitivity_pct"], 100.0)
        self.assertEqual(epi_res["episode_positive_predictivity_pct"], 100.0)
        self.assertAlmostEqual(epi_res["duration_sensitivity_pct"], 87.5, delta=1.0)

        # Synthetic self-certification
        cert = run_synthetic_self_certification(fs=500.0, duration_sec=20.0, heart_rate_bpm=72.0)
        self.assertEqual(cert["status"], "CERTIFIED")
        self.assertGreaterEqual(cert["ec57_qrs"]["f1_score_pct"], 99.0)
        self.assertTrue(cert["cse_fiducials"]["all_within_cse_limits"])

    def test_circadian_day_night_stratification_and_lqt_nocturnal_lengthening(self) -> None:
        """Verifies wall-clock Day/Night partitioning, nocturnal HR dipping, and LQT2/LQT3 nocturnal QTc lengthening."""
        beats: list[dict] = []
        # Daytime beats (start_hour = 21.0 -> first 30 min at 21:00-21:30 is DAY [7, 22))
        for i in range(15):
            rr_s = 0.72 + (i % 5) * 0.02  # ~80 BPM daytime
            qt_ms = 370.0 + (rr_s - 0.72) * 240.0  # steep daytime slope (> 0.211)
            beats.append({
                "beat_index": i,
                "time_sec": float(i * 60.0),  # 0 to 14 minutes -> 21:00 to 21:14 (DAY)
                "beat_class": "N",
                "rr_sec": rr_s,
                "hr_bpm": 60.0 / rr_s,
                "qt_ms": qt_ms,
                "qtc_fridericia_ms": qt_ms / (rr_s ** (1.0 / 3.0)),
                "j_tpeakc_ms": 205.0,
                "tpe_ms": 88.0,
            })

        # Nighttime beats (after 90 min -> 22:30+ is NIGHT) with 18% HR dip and +28 ms nocturnal QTcF lengthening
        for j in range(15):
            idx = 15 + j
            rr_s = 0.92 + (j % 5) * 0.02  # ~63 BPM nighttime
            qt_ms = 438.0 + (j % 3) * 2.0
            beats.append({
                "beat_index": idx,
                "time_sec": 5400.0 + float(j * 60.0),  # 22:30+ (NIGHT)
                "beat_class": "N" if j < 13 else "V",
                "rr_sec": rr_s,
                "hr_bpm": 60.0 / rr_s,
                "qt_ms": qt_ms,
                "qtc_fridericia_ms": qt_ms / (rr_s ** (1.0 / 3.0)),
                "j_tpeakc_ms": 232.0,
                "tpe_ms": 108.0,
            })

        circ = analyze_circadian_repolarization(
            beats,
            metadata={"start_time": "21:00:00"},
            total_duration_sec=7200.0,
        )
        self.assertEqual(circ["status"], "DUAL_EPOCH")
        self.assertEqual(circ["epoch_partition_method"], "WALL_CLOCK")
        self.assertEqual(circ["dipping_category"], "NORMAL_DIPPER")
        self.assertGreater(circ["hr_dip_pct"], 15.0)
        self.assertTrue(circ["nocturnal_qtc_lengthening_flag"])
        self.assertGreaterEqual(circ["delta_qtcf_night_minus_day_ms"], 15.0)
        self.assertTrue(circ["steep_day_qtrr_lqt2_pattern"])
        self.assertEqual(circ["night_pvc_count"], 2)
        self.assertEqual(circ["verdict"], "NOCTURNAL_QTC_PROLONGATION")

    def test_batch_api_multi_file_export_and_fault_isolation(self) -> None:
        """Verifies BatchAPI processes valid ECG files, isolates corrupted files, and writes CSV/JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            _, sig1, _ = StudyAPI.generate_demo_study(duration_sec=10.0, fs=500.0, heart_rate_bpm=70.0)
            _, sig2, _ = StudyAPI.generate_demo_study(duration_sec=10.0, fs=500.0, heart_rate_bpm=82.0)

            ExportAPI.export_study_pecg(tmp_path / "subject_01.pecg", sig1, 500.0, ["Lead II"])
            np.save(tmp_path / "subject_02.npy", sig2)
            # Write an intentionally corrupted .pecg file to verify fault isolation
            (tmp_path / "corrupted_03.pecg").write_bytes(b"NOT_A_VALID_PECG_HEADER")

            csv_out = tmp_path / "cohort_summary.csv"
            json_out = tmp_path / "cohort_summary.json"

            report = BatchAPI.analyze_directory(
                input_dir=tmp_path,
                output_csv_path=csv_out,
                output_json_path=json_out,
            )
            self.assertEqual(report["total_files"], 3)
            self.assertEqual(report["succeeded_count"], 2)
            self.assertEqual(report["failed_count"], 1)
            self.assertTrue(csv_out.exists())
            self.assertTrue(json_out.exists())

            with csv_out.open("r", encoding="utf-8") as cf:
                rows = list(csv.DictReader(cf))
            self.assertEqual(len(rows), 3)
            statuses = {r["file_name"]: r["status"] for r in rows}
            self.assertEqual(statuses["subject_01.pecg"], "OK")
            self.assertEqual(statuses["subject_02.npy"], "OK")
            self.assertEqual(statuses["corrupted_03.pecg"], "ERROR")

            json_payload = json.loads(json_out.read_text(encoding="utf-8"))
            self.assertEqual(json_payload["succeeded_count"], 2)

    def test_plugin_registry_custom_biomarker_and_fault_isolation(self) -> None:
        """Verifies @register_biomarker executes inside analyze_ecg and isolates plugin exceptions."""
        @register_biomarker("custom_qtc_tpe_index")
        def _compute_custom_idx(sig, fs, beats, summary):
            return {
                "index_value": round(float(summary.get("mean_qtc_fridericia_ms", 0.0)) * 0.1, 2),
                "beat_count": len(beats),
            }

        @register_biomarker("faulty_research_hook")
        def _faulty_hook(sig, fs, beats, summary):
            raise RuntimeError("Simulated third-party plugin crash")

        @register_qrs_detector("dummy_qrs")
        def _dummy_qrs(sig, fs):
            return np.array([100, 600], dtype=np.int64)

        @register_t_end_delineator("dummy_tend")
        def _dummy_tend(sig, r_peak, fs):
            return int(r_peak + int(0.28 * fs))

        reg_list = get_registered_plugins()
        self.assertIn("custom_qtc_tpe_index", reg_list["biomarkers"])
        self.assertIn("dummy_qrs", reg_list["qrs_detectors"])
        self.assertIn("dummy_tend", reg_list["t_end_delineators"])

        _, sig, _ = StudyAPI.generate_demo_study(duration_sec=10.0, fs=500.0, heart_rate_bpm=72.0)
        res = AnalysisAPI.analyze_signal(sig, fs=500.0)
        cb = res.get("custom_biomarkers") or {}
        self.assertEqual(cb["custom_qtc_tpe_index"]["status"], "OK")
        self.assertGreater(cb["custom_qtc_tpe_index"]["index_value"], 30.0)
        self.assertEqual(cb["faulty_research_hook"]["status"], "PLUGIN_ERROR")
        self.assertIn("Simulated third-party plugin crash", cb["faulty_research_hook"]["error"])

    def test_cli_benchmark_batch_and_gui_circadian_integration(self) -> None:
        """Verifies CLI benchmark/batch subcommands, version 0.9.6, and GUI lbl_adv_circadian readout."""
        self.assertEqual(repolaris.__version__, "0.9.6")

        buf = io.StringIO()
        with redirect_stdout(buf):
            cli_main(["benchmark", "--duration", "15", "--fs", "500", "--hr", "72"])
        out_str = buf.getvalue()
        self.assertIn("ANSI/AAMI EC57 & CSE Benchmark Report", out_str)
        self.assertIn("Certification Status: CERTIFIED", out_str)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            _, sig, _ = StudyAPI.generate_demo_study(duration_sec=10.0, fs=500.0, heart_rate_bpm=72.0)
            np.save(tmp_path / "clip_01.npy", sig)
            csv_file = tmp_path / "batch_out.csv"
            buf_batch = io.StringIO()
            with redirect_stdout(buf_batch):
                cli_main(["batch", str(tmp_path), "--csv", str(csv_file)])
            self.assertIn("Batch Cohort Summary: 1/1 succeeded", buf_batch.getvalue())
            self.assertTrue(csv_file.exists())

        win = MainWindow()
        self.assertTrue(hasattr(win, "lbl_adv_circadian"))
        _, sig_gui, _ = StudyAPI.generate_demo_study(duration_sec=10.0, fs=500.0, heart_rate_bpm=72.0)
        win.analysis_results = AnalysisAPI.analyze_signal(sig_gui, fs=500.0)
        win._update_cards_and_tables()
        self.assertIn("SINGLE_EPOCH", win.lbl_adv_circadian.text())
        win.close()

    def test_real_world_records_parsers(self) -> None:
        """Verify nested HL7 SLIST_PQ, WFDB 16+offset .mat, Shimmer CSV, and .atr/.ann parsers."""
        import struct
        from repolaris.io.ecg_loader import load_ecg_dataset
        from repolaris.io.ishne_reader import read_ishne_ann
        from repolaris.io.wfdb_reader import read_wfdb_annotations

        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            # 1. Nested HL7 SLIST_PQ with rhythm (20 samples) + representative template (4 samples)
            xml_path = tdir / "nested_slist.xml"
            xml_path.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
                <AnnotatedECG xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                  <component><series><component><sequenceSet>
                    <component><sequence>
                      <code code="TIME_ABSOLUTE"/>
                      <value xsi:type="GLIST_TS"><head value="20021122091000"/><increment value="0.002" unit="s"/></value>
                    </sequence></component>
                    <component><sequence>
                      <code code="MDC_ECG_LEAD_I"/>
                      <value xsi:type="SLIST_PQ">
                        <origin value="0" unit="uV"/><scale value="2.5" unit="uV"/>
                        <digits>0 10 20 30 40 50 60 70 80 90 100 90 80 70 60 50 40 30 20 10</digits>
                      </value>
                    </sequence></component>
                    <component><sequence>
                      <code code="MDC_ECG_LEAD_I"/>
                      <value xsi:type="SLIST_PQ">
                        <origin value="0" unit="uV"/><scale value="2.5" unit="uV"/>
                        <digits>10 20 30 40</digits>
                      </value>
                    </sequence></component>
                  </sequenceSet></component></series></component>
                </AnnotatedECG>"""
            )
            sig_xml, fs_xml, _ = load_ecg_dataset(xml_path)
            self.assertEqual(len(sig_xml), 1)
            self.assertEqual(len(next(iter(sig_xml.values()))), 20)
            self.assertAlmostEqual(fs_xml, 500.0, places=1)

            # 2. WFDB Format 16+192 byte-offset .mat companion
            hea_path = tdir / "sel_test.hea"
            mat_path = tdir / "sel_test.mat"
            hea_path.write_text(
                "sel_test 2 250 10\n"
                "sel_test.mat 16+192 200/mV 16 0 0 0 0 ECG1\n"
                "sel_test.mat 16+192 200/mV 16 0 0 0 0 ECG2\n"
            )
            payload = bytearray(192)
            for i in range(10):
                payload += struct.pack("<hh", i * 20, -i * 20)
            mat_path.write_bytes(bytes(payload))
            sig_mat, fs_mat, _ = load_ecg_dataset(mat_path)
            self.assertEqual(len(sig_mat), 2)
            self.assertEqual(len(next(iter(sig_mat.values()))), 10)
            self.assertAlmostEqual(fs_mat, 250.0, places=1)

            # 3. Shimmer3 sep= clinical CSV with timestamp & units row
            shimmer_csv = tdir / "shimmer.csv"
            lines = [
                "\"sep=\t\"",
                "Shimmer_Timestamp_ms\tShimmer_LA_RA_mV\tShimmer_LL_RA_mV\t",
                "ms\tmV\tmV\t",
            ]
            for i in range(50):
                lines.append(f"2015/06/25 15:39:24.{500 + i:03d}\t{0.1 * (i % 5):.4f}\t{0.2 * (i % 5):.4f}\t")
            shimmer_csv.write_text("\n".join(lines))
            sig_shim, fs_shim, _ = load_ecg_dataset(shimmer_csv)
            self.assertEqual(len(sig_shim), 2)
            self.assertEqual(len(next(iter(sig_shim.values()))), 50)
            self.assertAlmostEqual(fs_shim, 1000.0, delta=5.0)

            # 4. Binary MIT-BIH .atr and ISHNE .ann annotation parsers
            atr_path = tdir / "test.atr"
            # Code 1 (N) at dt=100 -> word = (1 << 10) | 100; Code 5 (V) at dt=200 -> word = (5 << 10) | 200; EOF = 0
            atr_bytes = struct.pack("<HHH", (1 << 10) | 100, (5 << 10) | 200, 0)
            atr_path.write_bytes(atr_bytes)
            wfdb_anns = read_wfdb_annotations(atr_path)
            self.assertEqual(wfdb_anns["r_peaks"], [100, 300])
            self.assertEqual(wfdb_anns["aami_classes"], ["N", "V"])

            ann_path = tdir / "test.ann"
            ann_header = bytearray(b"ANN  1.0  ") + struct.pack("<i", 0) + bytearray(508)
            # Initial sample = 500, followed by N beat (+250) and V beat (+240)
            ann_body = struct.pack("<I", 500) + struct.pack("<ccH", b"N", b" ", 250) + struct.pack("<ccH", b"V", b" ", 240)
            ann_path.write_bytes(bytes(ann_header + ann_body))
            ishne_anns = read_ishne_ann(ann_path)
            self.assertEqual(ishne_anns["r_peaks"], [750, 990])
            self.assertEqual(ishne_anns["aami_classes"], ["N", "V"])


if __name__ == "__main__":
    unittest.main()
