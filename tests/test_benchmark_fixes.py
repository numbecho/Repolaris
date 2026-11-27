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


def test_qrs_adaptive_threshold_recovers_after_artifact_spike_and_is_linear() -> None:
    """A 50x spike must not latch spki permanently, and long silent gaps must stay O(N)."""
    import time

    from repolaris.detection.qrs import _apply_adaptive_threshold_and_t_guard

    fs = 100.0
    n_samples = int(120 * fs)
    env = np.full(n_samples, 0.02, dtype=np.float64)
    abs_diff = np.full(n_samples, 0.01, dtype=np.float64)

    # Regular beats every 0.8s (150 beats total)
    true_peaks = np.arange(int(0.8 * fs), n_samples - int(fs), int(0.8 * fs))
    for p in true_peaks:
        env[p] = 1.0
        abs_diff[p] = 1.0

    # Inject a massive 100x electrode-pop spike at beat 5
    spike_idx = int(true_peaks[5])
    env[spike_idx] = 100.0
    abs_diff[spike_idx] = 100.0

    t0 = time.perf_counter()
    detected = _apply_adaptive_threshold_and_t_guard(
        envelope=env,
        abs_diff=abs_diff,
        fs=fs,
        refractory_ms=200.0,
        t_wave_slope_ratio=0.50,
    )
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.5, f"Adaptive threshold took too long ({elapsed:.2f}s)"
    # Must recover and detect nearly all beats after the spike
    assert len(detected) >= int(0.90 * len(true_peaks))


def test_qrs_searchback_bounded_on_long_silent_gap() -> None:
    """Thousands of sub-threshold noise candidates after a beat must complete in O(N)."""
    import time

    from repolaris.detection.qrs import _apply_adaptive_threshold_and_t_guard

    fs = 100.0
    n_samples = int(600 * fs)  # 10 min at 100 Hz
    rng = np.random.default_rng(42)
    env = rng.uniform(0.0, 0.01, size=n_samples)
    abs_diff = np.full(n_samples, 0.01, dtype=np.float64)
    # Only 3 beats in the first 3 seconds, then 10 minutes of tiny noise ripples
    for p in (80, 160, 240):
        env[p] = 10.0
        abs_diff[p] = 10.0

    t0 = time.perf_counter()
    detected = _apply_adaptive_threshold_and_t_guard(
        envelope=env,
        abs_diff=abs_diff,
        fs=fs,
        refractory_ms=200.0,
        t_wave_slope_ratio=0.50,
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"Searchback O(N^2) regression ({elapsed:.2f}s)"
    tail_fps = [p for p in detected if p > 300]
    assert len(tail_fps) <= 2, f"Unfloored noise-floor collapse: {len(tail_fps)} FPs in silent tail"


def test_read_wfdb_format_310_roundtrip(tmp_path: Path) -> None:
    """Format 310 (3 signed 10-bit samples per 4 bytes) must decode exact multi-channel values."""
    # Pack 6 samples (3 frames x 2 leads): [-512, 511, -1, 0, 123, -256]
    vals = [-512, 511, -1, 0, 123, -256]
    raw_bytes = bytearray()
    for k in range(0, len(vals), 3):
        s0, s1, s2 = (v & 0x3FF for v in vals[k : k + 3])
        w0 = ((s0 & 0x3FF) << 1) | ((s2 & 0x1F) << 11)
        w1 = ((s1 & 0x3FF) << 1) | (((s2 >> 5) & 0x1F) << 11)
        raw_bytes.extend(w0.to_bytes(2, "little"))
        raw_bytes.extend(w1.to_bytes(2, "little"))

    hea = tmp_path / "f310.hea"
    dat = tmp_path / "f310.dat"
    hea.write_text(
        "f310 2 128 3\n"
        "f310.dat 310 100(0)/mV 10 0 0 0 0 MLII\n"
        "f310.dat 310 100(0)/mV 10 0 0 0 0 V1\n",
        encoding="utf-8",
    )
    dat.write_bytes(bytes(raw_bytes))

    rec = read_wfdb(hea)
    assert rec.sampling_rate == 128.0
    assert rec.signals.shape == (2, 3)
    expected = np.array([[-5.12, -0.01, 1.23], [5.11, 0.0, -2.56]], dtype=np.float32)
    np.testing.assert_allclose(rec.signals, expected, atol=1e-4)


def test_hamilton_streaming_carry_over_preserves_normal_template() -> None:
    """Carrying templates across chunks prevents a wide beat at chunk 2 start from flipping the chunk."""
    fs = 250.0
    rr = int(0.8 * fs)
    t_local = np.arange(-int(0.08 * fs), int(0.08 * fs))
    normal_qrs = np.exp(-0.5 * (t_local / (0.012 * fs)) ** 2).astype(np.float32)

    sig1 = np.zeros(12 * rr + int(fs), dtype=np.float32)
    peaks1 = np.array([int(0.5 * fs) + k * rr for k in range(12)], dtype=np.int64)
    for r in peaks1:
        sig1[r - len(t_local) // 2 : r + len(t_local) // 2] += normal_qrs

    clf = HamiltonBeatClassifier(fs=fs)
    _, sum1 = clf.classify_recording(sig1, peaks1, reset_state=True)
    assert sum1["pvc_count"] == 0

    # Chunk 2: identical normal rhythm, but with wider q_onsets (as on ST-shifted chunks)
    q_on2 = peaks1 - int(0.08 * fs)
    _, sum2 = clf.classify_recording(sig1, peaks1, q_onsets=q_on2, reset_state=False)
    assert sum2["pvc_count"] == 0


def test_summarize_beats_beat_array_proxy_matches_dict_list() -> None:
    """Vectorized BeatArrayProxy summarize_beats must match the dict-list implementation."""
    from repolaris.detection.pipeline import BEAT_DTYPE, BeatArrayProxy
    from repolaris.detection.pulse_metrics import summarize_beats

    fs = 250.0
    arr = np.zeros(10, dtype=BEAT_DTYPE)
    for i in range(10):
        r = 200 + i * 200
        arr[i]["r_peak_sample"] = r
        arr[i]["q_onset_sample"] = r - 10
        arr[i]["j_point_sample"] = r + 10
        arr[i]["t_peak_sample"] = r + 60
        arr[i]["t_end_sample"] = r + 85
        arr[i]["rr_sec"] = 0.8 + 0.01 * (i % 3)
        arr[i]["qt_sec"] = 0.38 + 0.005 * (i % 2)
        arr[i]["beat_class_code"] = 0

    proxy = BeatArrayProxy(arr, fs=fs, lead_names=["MLII"], as_classified=False)
    as_dicts = [proxy[i] for i in range(len(proxy))]

    s_proxy = summarize_beats(proxy)
    s_dicts = summarize_beats(as_dicts)

    for k in s_dicts:
        if isinstance(s_dicts[k], float):
            assert np.isclose(s_proxy[k], s_dicts[k], atol=1e-4), f"Mismatch on {k}: {s_proxy[k]} vs {s_dicts[k]}"
        else:
            assert s_proxy[k] == s_dicts[k], f"Mismatch on {k}: {s_proxy[k]} vs {s_dicts[k]}"


def test_qrs_flat_and_microvolt_lead_in_recovers() -> None:
    """Flat (0.0) or microvolt noise lead-ins must not trap spki on the first real beats."""
    from repolaris.detection.qrs import _apply_adaptive_threshold_and_t_guard

    fs = 100.0
    n_samples = int(30 * fs)
    for baseline_noise in (0.0, 1e-5):
        env = np.full(n_samples, baseline_noise, dtype=np.float64)
        abs_diff = np.full(n_samples, baseline_noise, dtype=np.float64)
        # First 6 seconds flat/microvolt, then regular 1.0 beats every 0.8 s
        real_peaks = np.arange(int(6.0 * fs), n_samples - int(fs), int(0.8 * fs))
        for p in real_peaks:
            env[p] = 1.0
            abs_diff[p] = 1.0

        detected = _apply_adaptive_threshold_and_t_guard(
            envelope=env,
            abs_diff=abs_diff,
            fs=fs,
            refractory_ms=200.0,
            t_wave_slope_ratio=0.50,
        )
        assert len(detected) >= int(0.90 * len(real_peaks))


def test_qrs_post_decay_searchback_recovers_without_duplicates() -> None:
    """Searchback after silence decay recovers missed beats strictly past refractory without duplicates."""
    from repolaris.detection.qrs import _apply_adaptive_threshold_and_t_guard

    fs = 100.0
    n_samples = int(20 * fs)
    env = np.full(n_samples, 0.01, dtype=np.float64)
    abs_diff = np.full(n_samples, 0.01, dtype=np.float64)
    # 5 strong beats establish spki ~ 1.0, then a lower-amplitude (0.20) beat at 6.0s, then a noise peak at 6.6s
    for p in (80, 160, 240, 320, 400):
        env[p] = 1.0
        abs_diff[p] = 1.0
    env[580] = 0.20
    abs_diff[580] = 0.80
    env[660] = 0.05
    abs_diff[660] = 0.05

    detected = _apply_adaptive_threshold_and_t_guard(
        envelope=env,
        abs_diff=abs_diff,
        fs=fs,
        refractory_ms=200.0,
        t_wave_slope_ratio=0.50,
    )
    assert detected == sorted(set(detected)), "Detected peaks must be strictly increasing without duplicates"
    assert all(b - a >= int(0.20 * fs) for a, b in zip(detected, detected[1:], strict=False))
    assert 580 in detected


def test_hamilton_max_templates_cap_and_cumulative_streaming_promotion() -> None:
    """Template count stays bounded by max_templates and streaming promotion uses cumulative beat totals."""
    from repolaris.detection.hamilton_classifier import MorphologyTemplate

    fs = 250.0
    clf = HamiltonBeatClassifier(fs=fs, max_templates=4)
    rng = np.random.default_rng(7)
    rr = int(0.8 * fs)
    sig = rng.normal(0.0, 1.0, size=15 * rr + int(fs)).astype(np.float32)
    peaks = np.array([int(0.5 * fs) + k * rr for k in range(15)], dtype=np.int64)
    clf.classify_recording(sig, peaks, reset_state=True)
    assert len(clf.templates) <= 4

    # Streaming cumulative denominator check: 20 NORMAL beats in chunk 1, 4 PVC + 1 NORMAL in chunk 2.
    # PVC template has count=4 (< 45% of 25 total_seen), even though 4 >= 45% of chunk 2's 5 beats.
    clf2 = HamiltonBeatClassifier(fs=fs)
    w = int(0.16 * fs)
    t_ax = np.linspace(-1.0, 1.0, w, dtype=np.float32)
    norm_wave = np.exp(-0.5 * (t_ax / 0.2) ** 2).astype(np.float32)
    pvc_wave = np.sin(np.pi * t_ax).astype(np.float32)
    clf2.templates = [
        MorphologyTemplate(template_id=0, beat_class=BeatClass.NORMAL, waveform=norm_wave, count=20),
        MorphologyTemplate(template_id=1, beat_class=BeatClass.PVC, waveform=pvc_wave, count=1),
    ]
    clf2.rr_history = [0.8] * 8

    sig_tail = np.zeros(5 * rr + int(fs), dtype=np.float32)
    peaks_tail = np.array([int(0.5 * fs) + k * rr for k in range(5)], dtype=np.int64)
    half_w = w // 2
    for idx_k, r in enumerate(peaks_tail):
        wave = pvc_wave if idx_k < 3 else norm_wave
        sig_tail[r - half_w : r - half_w + w] = wave

    _, sum_tail = clf2.classify_recording(sig_tail, peaks_tail, reset_state=False)
    assert clf2.templates[1].beat_class == BeatClass.PVC
    assert sum_tail["pvc_count"] >= 3


def test_pipeline_stream_resets_hamilton_on_lead_failover(monkeypatch) -> None:
    """Switching active_lead_idx in analyze_ecg_stream must reset stream_hamilton_clf."""
    from repolaris.detection import pipeline

    seen_clf_ids: list[int] = []
    orig_analyze = pipeline.analyze_ecg
    call_idx = {"n": 0}

    def spy_analyze(*args, **kwargs):
        clf = kwargs.get("hamilton_clf")
        if clf is not None:
            seen_clf_ids.append(id(clf))
        return orig_analyze(*args, **kwargs)

    def fake_rank(raw_chunk, fs, conditioned_leads=None):
        names = list(raw_chunk.keys())
        idx = call_idx["n"]
        call_idx["n"] += 1
        if idx == 0:
            return {
                "quorum_passed": True,
                "recommended_lead": names[0],
                "per_lead": {names[0]: {"verdict": "EXCELLENT"}, names[1]: {"verdict": "ACCEPTABLE"}},
            }
        # Chunks 1..3: lead 0 degrades to POOR while lead 1 is EXCELLENT (triggers 2-chunk failover)
        return {
            "quorum_passed": True,
            "recommended_lead": names[1],
            "per_lead": {names[0]: {"verdict": "POOR"}, names[1]: {"verdict": "EXCELLENT"}},
        }

    monkeypatch.setattr(pipeline, "analyze_ecg", spy_analyze)
    monkeypatch.setattr(pipeline, "rank_leads_two_stage", fake_rank)

    fs = 250.0
    n_tot = int(120 * fs)
    clean = np.zeros(n_tot, dtype=np.float32)
    for k in range(1, 145):
        c = int(k * 0.8 * fs)
        if c + 20 < n_tot:
            clean[c - 5 : c + 5] = np.hanning(10).astype(np.float32) * 1.5
    multi = np.vstack([clean, clean])

    pipeline.analyze_ecg_stream(multi, fs=fs, chunk_duration_sec=30.0, overlap_sec=2.0, lead="auto")
    assert len(seen_clf_ids) >= 3
    assert len(set(seen_clf_ids)) >= 2


def test_summarize_beats_proxy_nan_zero_and_non_normal_classes() -> None:
    """Vectorized BeatArrayProxy summarize_beats handles NaN/zero RR/QT, rr<=0.15, and codes 0..4."""
    from repolaris.detection.pipeline import BEAT_DTYPE, BeatArrayProxy
    from repolaris.detection.pulse_metrics import summarize_beats

    fs = 250.0
    arr = np.zeros(6, dtype=BEAT_DTYPE)
    rr_vals = [0.0, np.nan, 0.12, 0.80, 0.85, 0.90]
    qt_vals = [0.0, np.nan, 0.30, 0.38, 0.40, 0.41]
    codes = [0, 1, 2, 3, 4, 0]
    for i in range(6):
        r = 200 + i * 200
        arr[i]["r_peak_sample"] = r
        arr[i]["q_onset_sample"] = r - 10
        arr[i]["j_point_sample"] = r + 10
        arr[i]["t_peak_sample"] = r + 55
        arr[i]["t_end_sample"] = r + 80
        arr[i]["rr_sec"] = rr_vals[i]
        arr[i]["qt_sec"] = qt_vals[i]
        arr[i]["beat_class_code"] = codes[i]

    proxy = BeatArrayProxy(arr, fs=fs, lead_names=["MLII"], as_classified=False)
    as_dicts = [proxy[i] for i in range(len(proxy))]
    s_proxy = summarize_beats(proxy)
    s_dicts = summarize_beats(as_dicts)

    for k in s_dicts:
        if isinstance(s_dicts[k], float):
            assert np.isclose(s_proxy[k], s_dicts[k], atol=1e-4), f"Mismatch on {k}: {s_proxy[k]} vs {s_dicts[k]}"
        else:
            assert s_proxy[k] == s_dicts[k], f"Mismatch on {k}: {s_proxy[k]} vs {s_dicts[k]}"


def test_read_wfdb_format_310_bit0_noise_and_truncated_trailing_bytes(tmp_path: Path) -> None:
    """Format 310 must ignore bit-0 noise in uint16 words and silently ignore <4 trailing bytes."""
    vals = [100, -200, 300]
    s0, s1, s2 = (v & 0x3FF for v in vals)
    # Deliberately set unused bit 0 to 1 in both words
    w0 = 1 | ((s0 & 0x3FF) << 1) | ((s2 & 0x1F) << 11)
    w1 = 1 | ((s1 & 0x3FF) << 1) | (((s2 >> 5) & 0x1F) << 11)
    raw = w0.to_bytes(2, "little") + w1.to_bytes(2, "little") + b"\xaa\xbb"  # 2 truncated trailing bytes

    hea = tmp_path / "f310_trunc.hea"
    dat = tmp_path / "f310_trunc.dat"
    hea.write_text(
        "f310_trunc 1 128 3\n"
        "f310_trunc.dat 310 100(0)/mV 10 0 0 0 0 MLII\n",
        encoding="utf-8",
    )
    dat.write_bytes(raw)

    rec = read_wfdb(hea)
    assert rec.signals.shape == (1, 3)
    np.testing.assert_allclose(rec.signals, np.array([[1.0, -2.0, 3.0]], dtype=np.float32), atol=1e-4)
