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


def test_qrs_clean_high_snr_prominent_p_wave_no_lock_on() -> None:
    """Clean high-SNR ECG with prominent P-waves (mitdb/100 MLII signature) must not lock onto P-waves."""
    from repolaris.detection.qrs import detect_r_peaks

    fs = 360.0
    duration_sec = 40.0
    n_samples = int(duration_sec * fs)
    sig = np.zeros(n_samples, dtype=np.float64)
    rr = int(0.80 * fs)
    true_r = np.arange(int(0.25 * fs), n_samples - int(0.5 * fs), rr)
    t_win = np.arange(-int(0.06 * fs), int(0.06 * fs))
    p_wave = 0.12 * np.exp(-0.5 * (t_win / (0.018 * fs)) ** 2)
    qrs_wave = 1.40 * np.exp(-0.5 * (t_win / (0.008 * fs)) ** 2)

    for r in true_r:
        p_c = r - int(0.14 * fs)
        if p_c - len(t_win) // 2 >= 0:
            sig[p_c - len(t_win) // 2 : p_c + len(t_win) // 2] += p_wave
        sig[r - len(t_win) // 2 : r + len(t_win) // 2] += qrs_wave

    detected = detect_r_peaks(sig, fs=fs)
    assert len(detected) == len(true_r)
    errs_ms = (detected - true_r) / fs * 1000.0
    assert abs(float(np.mean(errs_ms))) < 10.0
    assert float(np.max(np.abs(errs_ms))) < 15.0


def test_qrs_pause_and_asystole_150uv_safety_floor() -> None:
    """A 4-second <50 uV pause after sinus rhythm must generate 0 false beats."""
    from repolaris.detection.qrs import detect_r_peaks

    fs = 250.0
    n_samples = int(16.0 * fs)
    rng = np.random.default_rng(123)
    sig = rng.normal(0.0, 0.008, size=n_samples)  # ~40 uV p2p baseline noise
    t_win = np.arange(-int(0.04 * fs), int(0.04 * fs))
    qrs_wave = 1.2 * np.exp(-0.5 * (t_win / (0.008 * fs)) ** 2)

    # Normal beats 0.5..5.5s, then 4.5s asystole pause (5.5..10.0s), then resume 10.5..15.0s
    beat_secs = [0.5, 1.3, 2.1, 2.9, 3.7, 4.5, 5.3, 10.5, 11.3, 12.1, 12.9, 13.7, 14.5]
    for sec in beat_secs:
        c = int(sec * fs)
        sig[c - len(t_win) // 2 : c + len(t_win) // 2] += qrs_wave

    detected = detect_r_peaks(sig, fs=fs)
    pause_fps = [int(p) for p in detected if int(5.6 * fs) <= int(p) <= int(10.1 * fs)]
    assert len(pause_fps) == 0, f"False beats detected during asystole pause: {pause_fps}"
    assert len(detected) >= len(beat_secs) - 1


def test_qrs_short_empty_and_flatline_chunks() -> None:
    """Empty, <4 s, and flatline chunks must never raise and return 0 beats on flatline."""
    from repolaris.detection.qrs import detect_r_peaks

    assert len(detect_r_peaks(np.array([], dtype=np.float64), fs=250.0)) == 0
    assert len(detect_r_peaks(np.zeros(int(2.0 * 250), dtype=np.float64), fs=250.0)) == 0
    assert len(detect_r_peaks(np.zeros(int(10.0 * 250), dtype=np.float64), fs=250.0)) == 0


def test_qrs_16x_squared_energy_drop_recovers_fast() -> None:
    """A 4x amplitude drop (16x squared-energy drop) must recover quickly via 1-beat silence re-seed."""
    from repolaris.detection.qrs import detect_r_peaks

    fs = 250.0
    n_samples = int(30.0 * fs)
    sig = np.zeros(n_samples, dtype=np.float64)
    t_win = np.arange(-int(0.04 * fs), int(0.04 * fs))
    base_qrs = np.exp(-0.5 * (t_win / (0.008 * fs)) ** 2)

    rr = int(0.8 * fs)
    true_r = np.arange(int(0.5 * fs), n_samples - int(0.5 * fs), rr)
    for k, r in enumerate(true_r):
        amp = 2.0 if k < 10 else 0.5  # 4x amplitude drop -> 16x squared-energy drop
        sig[r - len(t_win) // 2 : r + len(t_win) // 2] += amp * base_qrs

    detected = detect_r_peaks(sig, fs=fs)
    # Must recover almost all beats after the 4x amplitude drop (allow <=2 transition beats)
    assert len(detected) >= len(true_r) - 2


def test_hamilton_streaming_afib_drift_and_reset_state_contract() -> None:
    """Multi-chunk streaming AFib with >24 morphology drift steps stays <5% PVC and bounds templates."""
    fs = 128.0
    clf = HamiltonBeatClassifier(fs=fs, max_templates=8)
    rng = np.random.default_rng(99)
    w = int(0.16 * fs)
    half_w = w // 2
    t_ax = np.linspace(-1.0, 1.0, w, dtype=np.float32)

    total_beats = 0
    total_pvcs = 0
    for chunk_idx in range(6):
        # Irregular AFib RRs (0.45s to 1.15s) + gradual morphology drift across 30+ distinct shifts
        n_chunk_beats = 30
        rrs = rng.uniform(0.45, 1.15, size=n_chunk_beats)
        peaks = np.cumsum((rrs * fs).astype(np.int64))
        sig = np.zeros(int(peaks[-1]) + int(fs), dtype=np.float32)
        for b_idx, r in enumerate(peaks):
            shift = -0.25 + 0.50 * ((chunk_idx * n_chunk_beats + b_idx) / 180.0)
            wave = np.exp(-0.5 * ((t_ax - shift) / 0.18) ** 2).astype(np.float32)
            sig[r - half_w : r - half_w + w] = wave

        _, summary = clf.classify_recording(sig, peaks, reset_state=(chunk_idx == 0))
        total_beats += summary["total_beats"]
        total_pvcs += summary["pvc_count"]
        assert len(clf.templates) <= 8

    assert total_pvcs / total_beats < 0.05
    assert clf._next_template_id >= len(clf.templates)
    # Verify reset_state=True clears all persistent streaming state
    _, sum_reset = clf.classify_recording(sig[: int(peaks[2]) + int(fs)], peaks[:3], reset_state=True)
    assert sum_reset["total_beats"] == 3
    assert len(clf.recent_template_ids) == 3


def test_hamilton_positive_pvc_recall_in_sinus_and_afib_and_tachycardia() -> None:
    """True wide/divergent PVCs must remain detected in both sinus rhythm and AFib, and 220 bpm keeps rr_history fresh."""
    fs = 250.0
    w = int(0.16 * fs)
    half_w = w // 2
    t_ax = np.linspace(-1.0, 1.0, w, dtype=np.float32)
    norm_wave = np.exp(-0.5 * (t_ax / 0.16) ** 2).astype(np.float32)
    pvc_wave = (-1.2 * np.sin(np.pi * t_ax)).astype(np.float32)

    # 1. Normal sinus rhythm with 4 premature wide/divergent PVCs
    rr = int(0.80 * fs)
    pvc_indices = {6, 11, 16, 21}
    peaks_list = [int(0.5 * fs)]
    for k in range(1, 25):
        step = int(0.58 * fs) if k in pvc_indices else (int(1.02 * fs) if (k - 1) in pvc_indices else rr)
        peaks_list.append(peaks_list[-1] + step)
    peaks = np.array(peaks_list, dtype=np.int64)
    q_onsets = np.array(
        [int(r - (0.09 * fs if k in pvc_indices else 0.03 * fs)) for k, r in enumerate(peaks)],
        dtype=np.int64,
    )
    sig = np.zeros(int(peaks[-1]) + int(fs), dtype=np.float32)
    for k, r in enumerate(peaks):
        sig[r - half_w : r - half_w + w] = pvc_wave if k in pvc_indices else norm_wave

    clf = HamiltonBeatClassifier(fs=fs)
    beats, _ = clf.classify_recording(sig, peaks, q_onsets=q_onsets, reset_state=True)
    detected_pvcs = {i for i, b in enumerate(beats) if b.beat_class == BeatClass.PVC}
    assert len(detected_pvcs & pvc_indices) >= 4

    # 2. AFib with 4 wide/divergent PVCs must still detect them
    rng = np.random.default_rng(77)
    af_rrs = rng.uniform(0.45, 1.10, size=30)
    af_peaks = np.cumsum((af_rrs * fs).astype(np.int64))
    af_pvc_idx = {14, 18, 22, 26}
    af_q_on = np.array(
        [int(r - (0.09 * fs if k in af_pvc_idx else 0.03 * fs)) for k, r in enumerate(af_peaks)],
        dtype=np.int64,
    )
    af_sig = np.zeros(int(af_peaks[-1]) + int(fs), dtype=np.float32)
    for k, r in enumerate(af_peaks):
        af_sig[r - half_w : r - half_w + w] = pvc_wave if k in af_pvc_idx else norm_wave

    clf_af = HamiltonBeatClassifier(fs=fs)
    af_beats, _ = clf_af.classify_recording(af_sig, af_peaks, q_onsets=af_q_on, reset_state=True)
    af_det_pvcs = {i for i, b in enumerate(af_beats) if b.beat_class == BeatClass.PVC}
    assert len(af_det_pvcs & af_pvc_idx) >= 4

    # 3. 220 bpm tachycardia (RR ~ 0.27s) keeps rr_history updated rather than freezing
    tachy_rr = int(0.27 * fs)
    tachy_peaks = np.array([int(0.5 * fs) + k * tachy_rr for k in range(20)], dtype=np.int64)
    tachy_sig = np.zeros(int(tachy_peaks[-1]) + int(fs), dtype=np.float32)
    for r in tachy_peaks:
        tachy_sig[r - half_w : r - half_w + w] = norm_wave
    clf_tachy = HamiltonBeatClassifier(fs=fs)
    clf_tachy.classify_recording(tachy_sig, tachy_peaks, reset_state=True)
    assert float(np.median(clf_tachy.rr_history)) < 0.32


def test_hamilton_rr_history_fallback_on_sinus_to_vt_transition() -> None:
    """Sustained >=8 non-NORMAL beats (220 bpm VT) after 0.8s sinus must update rr_history via fallback."""
    fs = 250.0
    w = int(0.16 * fs)
    half_w = w // 2
    t_ax = np.linspace(-1.0, 1.0, w, dtype=np.float32)
    norm_wave = np.exp(-0.5 * (t_ax / 0.16) ** 2).astype(np.float32)
    vt_wave = (-1.3 * np.sin(np.pi * t_ax)).astype(np.float32)

    # 20 normal beats at 0.80 s RR, then 12 consecutive wide/divergent VT beats at 0.27 s RR (~222 bpm)
    # (12/32 = 37.5% < 45% BBB dominant-cluster threshold, while 12 >= 8 exercises the fallback path)
    peaks_list = [int(0.5 * fs)]
    for k in range(1, 32):
        step = int(0.80 * fs) if k < 20 else int(0.27 * fs)
        peaks_list.append(peaks_list[-1] + step)
    peaks = np.array(peaks_list, dtype=np.int64)
    q_onsets = np.array(
        [int(r - (0.03 * fs if k < 20 else 0.09 * fs)) for k, r in enumerate(peaks)],
        dtype=np.int64,
    )
    sig = np.zeros(int(peaks[-1]) + int(fs), dtype=np.float32)
    for k, r in enumerate(peaks):
        sig[r - half_w : r - half_w + w] = norm_wave if k < 20 else vt_wave

    clf = HamiltonBeatClassifier(fs=fs)
    beats, _ = clf.classify_recording(sig, peaks, q_onsets=q_onsets, reset_state=True)
    # Verify VT beats were classified non-NORMAL (exercising _beats_since_normal >= 8) and rr_history adapted
    vt_classes = [b.beat_class for b in beats[20:]]
    assert sum(1 for c in vt_classes if c != BeatClass.NORMAL) >= 10
    assert float(np.median(clf.rr_history)) < 0.35


def test_qrs_lead_in_silence_recovery_after_cold_start_spike() -> None:
    """A giant spike in the first 4s followed by silence must recover real beats via in_lead_in_silence."""
    from repolaris.detection.qrs import _apply_adaptive_threshold_and_t_guard

    fs = 100.0
    n_samples = int(20 * fs)
    env = np.full(n_samples, 0.005, dtype=np.float64)
    abs_diff = np.full(n_samples, 0.005, dtype=np.float64)
    # Cold-start spike seeds spki = 50.0, then normal 1.0 beats begin after 4.5s (past init_silence_samples)
    env[50] = 50.0
    abs_diff[50] = 50.0
    env[120] = 50.0
    abs_diff[120] = 50.0
    # Clear the spikes out of candidates by making them 1-sample flat plateau? Instead test via real lower-amp beats:
    # Actually place real beats at 5.0s..18.0s with height 1.0 (below thr1=12.5 and thr2=5.0, above 0.2*thr2=1.0)
    env[50] = 40.0
    env[120] = 40.0
    real_peaks = np.arange(int(5.0 * fs), int(18.0 * fs), int(0.8 * fs))
    for p in real_peaks:
        env[p] = 1.2
        abs_diff[p] = 1.2

    detected = _apply_adaptive_threshold_and_t_guard(
        envelope=env,
        abs_diff=abs_diff,
        fs=fs,
        refractory_ms=200.0,
        t_wave_slope_ratio=0.50,
    )
    recovered_real = [p for p in detected if p >= int(5.0 * fs)]
    assert len(recovered_real) >= int(0.85 * len(real_peaks))


def test_qrs_nan_contaminated_signal_recovers() -> None:
    """NaN samples in the first 4s must not poison adaptive thresholds to NaN."""
    from repolaris.detection.qrs import detect_r_peaks

    fs = 250.0
    n_samples = int(20.0 * fs)
    sig = np.zeros(n_samples, dtype=np.float64)
    t_win = np.arange(-int(0.04 * fs), int(0.04 * fs))
    qrs_wave = 1.2 * np.exp(-0.5 * (t_win / (0.008 * fs)) ** 2)
    true_r = np.arange(int(0.5 * fs), n_samples - int(0.5 * fs), int(0.8 * fs))
    for r in true_r:
        sig[r - len(t_win) // 2 : r + len(t_win) // 2] += qrs_wave

    # Inject NaNs in the cold-start init window
    sig[10:25] = np.nan
    sig[300] = np.inf
    detected = detect_r_peaks(sig, fs=fs)
    assert len(detected) >= int(0.95 * len(true_r))


def test_hamilton_empty_chunk_reset_state_isolation() -> None:
    """Empty r_peaks with reset_state=True must clear prior state; reset_state=False must preserve count."""
    fs = 250.0
    rr = int(0.8 * fs)
    w = int(0.16 * fs)
    half_w = w // 2
    t_ax = np.linspace(-1.0, 1.0, w, dtype=np.float32)
    norm_wave = np.exp(-0.5 * (t_ax / 0.16) ** 2).astype(np.float32)

    peaks = np.array([int(0.5 * fs) + k * rr for k in range(10)], dtype=np.int64)
    sig = np.zeros(int(peaks[-1]) + int(fs), dtype=np.float32)
    for r in peaks:
        sig[r - half_w : r - half_w + w] = norm_wave

    clf = HamiltonBeatClassifier(fs=fs)
    clf.classify_recording(sig, peaks, reset_state=True)
    assert len(clf.templates) >= 1

    # Empty chunk with reset_state=False preserves templates and reports accurate template_cluster_count
    _, sum_keep = clf.classify_recording(sig, np.array([], dtype=np.int64), reset_state=False)
    assert sum_keep["template_cluster_count"] == len(clf.templates)
    assert len(clf.templates) >= 1

    # Empty chunk with reset_state=True clears all persistent state
    _, sum_clear = clf.classify_recording(sig, np.array([], dtype=np.int64), reset_state=True)
    assert sum_clear["template_cluster_count"] == 0
    assert len(clf.templates) == 0
    assert len(clf.recent_template_ids) == 0
    assert len(clf.recent_rr_irregular) == 0
    assert clf._next_template_id == 0
    assert clf._global_beat_idx == 0
