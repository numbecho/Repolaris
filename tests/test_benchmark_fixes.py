"""Regression tests for WFDB fractional-fs headers and Hamilton dominant-cluster classification."""

from pathlib import Path
import numpy as np

from repolaris.detection.classifier import BeatClass
from repolaris.detection.hamilton_classifier import HamiltonBeatClassifier
from repolaris.io.wfdb_reader import read_wfdb


def test_read_wfdb_fractional_sampling_rate(tmp_path: Path) -> None:
    """Native WFDB parser should parse QTDB-style '250/360' and '250/128' header rates."""
    hea = tmp_path / "sel_test.hea"
    dat = tmp_path / "sel_test.dat"

    hea.write_text(
        "sel_test 2 250/360 100\n"
        "sel_test.dat 16 200(0)/mV 16 0 0 0 0 MLII\n"
        "sel_test.dat 16 200(0)/mV 16 0 0 0 0 V1\n",
        encoding="utf-8",
    )
    samples = np.zeros((100, 2), dtype="<i2")
    dat.write_bytes(samples.tobytes())

    rec = read_wfdb(hea)
    assert rec.sampling_rate == 250.0
    assert rec.num_signals == 2
    assert rec.signals.shape == (2, 100)


def test_hamilton_dominant_wide_qrs_not_all_pvc() -> None:
    """A regular dominant wide-QRS rhythm (e.g., BBB) must not be labeled 100% PVC."""
    fs = 360.0
    n_beats = 20
    rr = int(0.85 * fs)
    sig = np.zeros(n_beats * rr + int(fs), dtype=np.float32)
    r_peaks = np.array([int(0.5 * fs) + k * rr for k in range(n_beats)], dtype=np.int64)
    q_onsets = r_peaks - int(0.08 * fs)

    t_local = np.arange(-int(0.08 * fs), int(0.08 * fs))
    wide_qrs = np.exp(-0.5 * (t_local / (0.025 * fs)) ** 2).astype(np.float32)
    for r in r_peaks:
        sig[r - len(t_local) // 2 : r + len(t_local) // 2] += wide_qrs

    clf = HamiltonBeatClassifier(fs=fs)
    beats, summary = clf.classify_recording(sig, r_peaks, q_onsets=q_onsets)

    assert len(beats) == n_beats
    assert summary["pvc_count"] == 0
    assert all(b.beat_class == BeatClass.NORMAL for b in beats)
