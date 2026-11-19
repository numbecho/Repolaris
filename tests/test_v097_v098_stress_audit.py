"""Stage 1 (v0.9.7) & Stage 2 (v0.9.8) Stress-Test Suite: Pathological Signals, Streaming Parity & Multi-Format Batch."""

import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np

from repolaris.api.batch import BatchAPI
from repolaris.api.export import ExportAPI
from repolaris.detection.pipeline import analyze_ecg, analyze_ecg_stream
from repolaris.io.pecg_format import save_pecg
from repolaris.utils.signal import generate_synthetic_ecg


class TestStage1PathologicalSignals(unittest.TestCase):
    """Stage 1 (v0.9.7): Extreme rhythms, flatlines, NaN/Inf glitches, inverted morphology & sampling rates."""

    def test_flatline_zero_and_constant_lead_off_produce_zero_beats(self) -> None:
        r_zero = analyze_ecg(np.zeros(2500), fs=250.0)
        self.assertEqual(len(r_zero["beats"]), 0)

        r_const = analyze_ecg(np.ones(5000) * 1.234, fs=500.0)
        self.assertEqual(len(r_const["beats"]), 0)

    def test_midstream_nan_and_inf_glitches_recover_without_warnings(self) -> None:
        _, sig, _ = generate_synthetic_ecg(15.0, fs=250.0, heart_rate_bpm=72.0)
        corrupted = sig.copy()
        corrupted[1000:1020] = np.nan
        corrupted[2000:2005] = np.inf

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            res = analyze_ecg(corrupted, fs=250.0)

        self.assertGreaterEqual(len(res["beats"]), 15)
        self.assertEqual(len(caught), 0)

    def test_extreme_rhythms_bradycardia_tachycardia_af_pause_and_inverted(self) -> None:
        _, s_30, _ = generate_synthetic_ecg(20.0, fs=250.0, heart_rate_bpm=30.0)
        r_30 = analyze_ecg(s_30, fs=250.0)
        self.assertGreaterEqual(len(r_30["beats"]), 8)

        _, s_220, _ = generate_synthetic_ecg(15.0, fs=500.0, heart_rate_bpm=220.0)
        r_220 = analyze_ecg(s_220, fs=500.0)
        self.assertGreaterEqual(len(r_220["beats"]), 40)

        _, s_inv, _ = generate_synthetic_ecg(15.0, fs=500.0, heart_rate_bpm=70.0)
        r_inv = analyze_ecg(-s_inv, fs=500.0)
        self.assertGreaterEqual(len(r_inv["beats"]), 14)

        _, s_pause, _ = generate_synthetic_ecg(20.0, fs=250.0, heart_rate_bpm=72.0)
        s_pause = s_pause.copy()
        s_pause[1500:3000] = 0.0  # 6.0s asystole pause
        r_pause = analyze_ecg(s_pause, fs=250.0)
        self.assertGreaterEqual(len(r_pause["beats"]), 12)

        # 100% irregular AF-like RR sequence
        rng = np.random.default_rng(42)
        _, one_beat, _ = generate_synthetic_ecg(1.2, fs=250.0, heart_rate_bpm=60.0)
        af_chunks = []
        for _ in range(90):
            n_s = int(rng.uniform(0.38, 1.05) * 250.0)
            seg = np.zeros(n_s)
            copy_len = min(n_s, len(one_beat))
            seg[:copy_len] = one_beat[:copy_len]
            af_chunks.append(seg)
        r_af = analyze_ecg(np.concatenate(af_chunks), fs=250.0)
        self.assertGreater(r_af["af_report"]["af_burden_pct"], 80.0)

    def test_sampling_rates_and_ultra_short_clips(self) -> None:
        for fs_val in (125.0, 128.0, 200.0, 360.0, 1000.0, 2000.0):
            _, s_fs, _ = generate_synthetic_ecg(12.0, fs=fs_val, heart_rate_bpm=75.0)
            res = analyze_ecg(s_fs, fs=fs_val)
            self.assertGreaterEqual(len(res["beats"]), 12)

        _, s_short, _ = generate_synthetic_ecg(1.5, fs=500.0, heart_rate_bpm=60.0)
        res_short = analyze_ecg(s_short, fs=500.0)
        self.assertGreaterEqual(len(res_short["beats"]), 1)


class TestStage2StreamingAndMultiFormatBatch(unittest.TestCase):
    """Stage 2 (v0.9.8): In-memory vs streaming parity and multi-format cohort batch + PDF export."""

    def test_in_memory_vs_streaming_beat_and_key_parity(self) -> None:
        _, sig, _ = generate_synthetic_ecg(600.0, fs=250.0, heart_rate_bpm=72.0)
        r_mem = analyze_ecg(sig, fs=250.0)
        r_str = analyze_ecg_stream(sig, fs=250.0, chunk_duration_sec=120.0, overlap_sec=5.0)

        self.assertEqual(len(r_mem["beats"]), len(r_str["beats"]))
        self.assertTrue(set(r_mem.keys()).issubset(set(r_str.keys())))

    def test_multi_format_batch_and_pdf_export(self) -> None:
        _, sig, _ = generate_synthetic_ecg(12.0, fs=250.0, heart_rate_bpm=72.0)
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            np.save(tdir / "rec.npy", sig)
            np.savetxt(tdir / "rec.csv", sig, delimiter=",")
            save_pecg(tdir / "rec.pecg", sig[None, :], 250.0, ["I"])
            (tdir / "rec_wfdb.hea").write_text(
                f"rec_wfdb 1 250 {len(sig)}\nrec_wfdb.dat 16 200/mV 16 0 0 0 0 I\n"
            )
            (tdir / "rec_wfdb.dat").write_bytes((sig * 200).astype("<i2").tobytes())
            digits = " ".join(str(int(v * 200)) for v in sig)
            (tdir / "rec.xml").write_text(
                f"""<?xml version="1.0" encoding="UTF-8"?>
<AnnotatedECG xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <component><series><component><sequenceSet>
    <component><sequence><code code="TIME_ABSOLUTE"/><value xsi:type="GLIST_TS"><head value="20200101000000"/><increment value="0.004" unit="s"/></value></sequence></component>
    <component><sequence><code code="MDC_ECG_LEAD_I"/><value xsi:type="SLIST_PQ"><origin value="0" unit="uV"/><scale value="5.0" unit="uV"/><digits>{digits}</digits></value></sequence></component>
  </sequenceSet></component></series></component>
</AnnotatedECG>"""
            )
            batch_res = BatchAPI.analyze_directory(
                tdir,
                output_csv_path=tdir / "cohort.csv",
                output_json_path=tdir / "cohort.json",
            )
            self.assertEqual(batch_res["total_files"], 5)
            self.assertEqual(batch_res["failed_count"], 0)
            self.assertTrue((tdir / "cohort.csv").is_file())
            self.assertTrue((tdir / "cohort.json").is_file())

            r_ok = analyze_ecg(sig, fs=250.0)
            pdf_path = tdir / "stress_report.pdf"
            ExportAPI.export_clinical_pdf(pdf_path, r_ok, fs=250.0, lead_name="I")
            self.assertGreater(pdf_path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
