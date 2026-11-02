"""Microvolt T-Wave Alternans (TWA) Detection module.

Implements dual analytical pathways for beat-to-beat ABAB repolarization alternans:
1. Spectral FFT Method (Smith et al., Circulation 1988; Rosenbaum et al., NEJM 1994):
   128-beat ensemble periodogram at 0.5 cycles/beat with alternans ratio k >= 3.0
   and V_alt >= 1.9 uV significance criteria, incorporating sub-sample parabolic
   fiducial alignment to eliminate sampling-grid phase jitter.
2. Modified Moving Average (MMA) Method (Nearing & Verrier, J Appl Physiol 2002;
   Verrier et al., JACC 2011): Continuous recursive odd/even beat template tracking
   for non-stationary ambulatory Holter recordings.
"""

from __future__ import annotations

from typing import Any
import numpy as np


def _refine_r_peak_subsample(sig: np.ndarray, r_idx: int, radius: int = 3) -> float:
    """Refines integer R-peak index to sub-sample precision via 3-point parabolic interpolation."""
    n = len(sig)
    s0 = max(1, r_idx - radius)
    s1 = min(n - 2, r_idx + radius)
    if s1 > s0:
        r_idx = s0 + int(np.argmax(sig[s0 : s1 + 1]))
    if 0 < r_idx < n - 1:
        y_m1 = float(sig[r_idx - 1])
        y_0 = float(sig[r_idx])
        y_p1 = float(sig[r_idx + 1])
        denom = y_m1 - 2.0 * y_0 + y_p1
        if abs(denom) > 1e-12:
            delta = 0.5 * (y_m1 - y_p1) / denom
            if abs(delta) <= 1.0:
                return float(r_idx) + delta
    return float(r_idx)


def _extract_stt_matrix(
    signal: np.ndarray,
    r_peaks: np.ndarray,
    fs: float,
    stt_start_ms: float = 80.0,
    stt_duration_ms: float = 320.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Extracts sub-sample aligned, baseline-corrected ST-T segment matrix across consecutive beats.

    Returns:
        Tuple of (stt_matrix_uv, valid_r_peaks) where stt_matrix_uv has shape
        (n_valid_beats, n_stt_samples) calibrated in microvolts (uV).
    """
    sig = np.asarray(signal, dtype=np.float64)
    peaks = np.asarray(r_peaks, dtype=int)
    n_samples = len(sig)

    start_off = max(1, int((stt_start_ms / 1000.0) * fs))
    seg_len = max(8, int((stt_duration_ms / 1000.0) * fs))
    iso_off = max(1, int(0.040 * fs))

    # Auto-detect whether signal is in mV (typical peak ~1 mV) or already in uV
    scale_to_uv = 1000.0 if np.percentile(np.abs(sig), 99) < 50.0 else 1.0
    sample_grid = np.arange(n_samples, dtype=np.float64)
    rel_offsets = np.arange(seg_len, dtype=np.float64)

    rows: list[np.ndarray] = []
    kept_peaks: list[int] = []

    for r_idx in peaks:
        if int(r_idx) + start_off + seg_len >= n_samples or int(r_idx) < int(0.080 * fs):
            continue

        r_exact = _refine_r_peak_subsample(sig, int(r_idx))
        target_coords = r_exact + float(start_off) + rel_offsets

        # Subtract local PR isoelectric reference to suppress residual baseline drift
        iso_start = max(0, int(round(r_exact)) - int(0.080 * fs))
        iso_end = max(iso_start + 1, int(round(r_exact)) - iso_off)
        iso_level = float(np.median(sig[iso_start:iso_end]))

        interpolated = np.interp(target_coords, sample_grid, sig)
        segment_uv = (interpolated - iso_level) * scale_to_uv
        rows.append(segment_uv)
        kept_peaks.append(int(r_idx))

    if not rows:
        return np.empty((0, seg_len), dtype=np.float64), np.empty(0, dtype=int)

    return np.vstack(rows), np.asarray(kept_peaks, dtype=int)


def compute_spectral_twa(
    lead_signal: np.ndarray,
    fs: float,
    r_peaks: np.ndarray,
    beat_classes: list[str] | None = None,
    window_beats: int = 128,
    stt_start_ms: float = 80.0,
    stt_duration_ms: float = 320.0,
) -> dict[str, Any]:
    """Quantifies microvolt T-wave alternans using Spectral FFT analysis at 0.5 cycles/beat.

    Args:
        lead_signal: 1D calibrated ECG signal array (mV or uV).
        fs: Sampling frequency in Hz.
        r_peaks: 1D array of R-peak sample indices.
        beat_classes: Optional list of AAMI EC57 beat class codes ('N', 'V', etc.).
        window_beats: Beat ensemble window length (default: 128; automatically adapts
            to largest even count >= 16 if recording is shorter).
        stt_start_ms: Offset after R-peak to start ST-T window (default: 80.0 ms).
        stt_duration_ms: Duration of ST-T alignment window (default: 320.0 ms).

    Returns:
        Dictionary containing:
            - 'v_alt_uv': Alternans voltage in microvolts (uV).
            - 'k_score': Alternans ratio (signal-to-noise significance score at 0.5 cpb).
            - 'is_positive': True if v_alt_uv >= 1.9 uV and k_score >= 3.0.
            - 'power_05_cpb': Spectral power at 0.5 cycles/beat (uV^2).
            - 'noise_mean': Mean spectral noise power in [0.33, 0.48] cpb band.
            - 'noise_std': Standard deviation of noise band power.
            - 'ectopic_fraction': Fraction of non-sinus beats in analyzed sequence.
            - 'beats_analyzed': Number of beats included in FFT ensemble.
    """
    peaks = np.asarray(r_peaks, dtype=int)
    ectopic_fraction = 0.0
    if beat_classes is not None and len(beat_classes) == len(peaks) and len(peaks) > 0:
        non_sinus = sum(1 for c in beat_classes if str(c).upper() != "N")
        ectopic_fraction = float(non_sinus) / float(len(peaks))

    stt_mat, _ = _extract_stt_matrix(
        lead_signal, peaks, fs, stt_start_ms=stt_start_ms, stt_duration_ms=stt_duration_ms
    )
    n_avail = stt_mat.shape[0]
    if n_avail < 8:
        return {
            "v_alt_uv": 0.0,
            "k_score": 0.0,
            "is_positive": False,
            "power_05_cpb": 0.0,
            "noise_mean": 0.0,
            "noise_std": 0.0,
            "ectopic_fraction": ectopic_fraction,
            "beats_analyzed": n_avail,
        }

    # Ensure even window length M <= n_avail
    m_win = min(int(window_beats), n_avail)
    if m_win % 2 != 0:
        m_win -= 1

    ensemble = stt_mat[:m_win, :]
    # Detrend beat-to-beat DC offset at each time point across the M beats
    ensemble = ensemble - np.mean(ensemble, axis=0, keepdims=True)

    # Compute FFT along beat axis (axis=0); normalized power spectrum
    fft_vals = np.fft.rfft(ensemble, axis=0)
    psd = (np.abs(fft_vals) ** 2) / float(m_win ** 2)
    # Average spectrum across all ST-T time points
    avg_spectrum = np.mean(psd, axis=1)
    freqs = np.fft.rfftfreq(m_win, d=1.0)  # cycles per beat (0.0 to 0.5 cpb)

    # Alternans frequency is strictly Nyquist bin f = 0.5 cpb (last index of rfft)
    p_05 = float(avg_spectrum[-1])

    # Noise reference band: [0.33, 0.49) cpb (excluding the 0.5 cpb Nyquist bin)
    noise_mask = (freqs >= 0.30) & (freqs < 0.49)
    if np.sum(noise_mask) < 2:
        noise_bins = avg_spectrum[1:-1]
    else:
        noise_bins = avg_spectrum[noise_mask]

    noise_mean = float(np.mean(noise_bins)) if len(noise_bins) > 0 else 0.0
    noise_std = float(np.std(noise_bins, ddof=1)) if len(noise_bins) > 1 else 1e-6
    noise_std = max(noise_std, 1e-6)

    net_power = max(0.0, p_05 - noise_mean)
    v_alt_uv = float(np.sqrt(net_power) * 2.0)
    k_score = float((p_05 - noise_mean) / noise_std)
    is_positive = bool(v_alt_uv >= 1.9 and k_score >= 3.0 and ectopic_fraction <= 0.10)

    return {
        "v_alt_uv": v_alt_uv,
        "k_score": k_score,
        "is_positive": is_positive,
        "power_05_cpb": p_05,
        "noise_mean": noise_mean,
        "noise_std": noise_std,
        "ectopic_fraction": ectopic_fraction,
        "beats_analyzed": m_win,
        "frequencies_cpb": freqs,
        "spectrum_uv2": avg_spectrum,
    }


def compute_mma_twa(
    lead_signal: np.ndarray,
    fs: float,
    r_peaks: np.ndarray,
    update_fraction: int = 8,
    max_step_uv: float = 32.0,
    stt_start_ms: float = 80.0,
    stt_duration_ms: float = 320.0,
) -> dict[str, Any]:
    """Continuously tracks T-Wave Alternans using the Modified Moving Average (MMA) method.

    Args:
        lead_signal: 1D calibrated ECG signal array (mV or uV).
        fs: Sampling frequency in Hz.
        r_peaks: 1D array of R-peak sample indices.
        update_fraction: Scaling denominator (typically 8, 16, or 32) for template recursion.
        max_step_uv: Nonlinear noise limiter bounding per-beat template update in uV (default: 32.0).
        stt_start_ms: Offset after R-peak to start ST-T window (default: 80.0 ms).
        stt_duration_ms: Duration of ST-T window (default: 320.0 ms).

    Returns:
        Dictionary containing:
            - 'v_mma_series_uv': 1D array of beat-by-beat MMA alternans voltages (uV).
            - 'timestamps_sec': 1D array of beat timestamps (seconds).
            - 'max_v_mma_uv': Peak MMA alternans voltage across the recording (uV).
            - 'mean_v_mma_uv': Mean MMA alternans voltage (uV).
            - 'odd_template_uv': Final recursive odd-beat ST-T template (uV).
            - 'even_template_uv': Final recursive even-beat ST-T template (uV).
            - 'risk_level': Clinical stratification ('NORMAL' < 47 uV, 'ABNORMAL' 47-65 uV, 'SEVERE' >= 65 uV).
    """
    stt_mat, valid_peaks = _extract_stt_matrix(
        lead_signal, r_peaks, fs, stt_start_ms=stt_start_ms, stt_duration_ms=stt_duration_ms
    )
    n_beats, seg_len = stt_mat.shape
    if n_beats < 4:
        return {
            "v_mma_series_uv": np.zeros(0, dtype=np.float64),
            "timestamps_sec": np.zeros(0, dtype=np.float64),
            "max_v_mma_uv": 0.0,
            "mean_v_mma_uv": 0.0,
            "odd_template_uv": np.zeros(seg_len, dtype=np.float64),
            "even_template_uv": np.zeros(seg_len, dtype=np.float64),
            "risk_level": "NORMAL",
        }

    denom = float(max(2, int(update_fraction)))
    t_even = stt_mat[0].copy()
    t_odd = stt_mat[1].copy()

    v_mma_list: list[float] = []
    ts_list: list[float] = []

    for idx in range(n_beats):
        beat_stt = stt_mat[idx]
        if idx % 2 == 0:
            delta = (beat_stt - t_even) / denom
            delta = np.clip(delta, -max_step_uv, max_step_uv)
            t_even = t_even + delta
        else:
            delta = (beat_stt - t_odd) / denom
            delta = np.clip(delta, -max_step_uv, max_step_uv)
            t_odd = t_odd + delta

        if idx >= 1:
            v_mma = float(np.max(np.abs(t_odd - t_even)))
            v_mma_list.append(v_mma)
            ts_list.append(float(valid_peaks[idx] / fs))

    v_series = np.asarray(v_mma_list, dtype=np.float64)
    ts_series = np.asarray(ts_list, dtype=np.float64)
    max_v = float(np.max(v_series)) if len(v_series) > 0 else 0.0
    mean_v = float(np.mean(v_series)) if len(v_series) > 0 else 0.0

    if max_v >= 65.0:
        risk = "SEVERE"
    elif max_v >= 47.0:
        risk = "ABNORMAL"
    else:
        risk = "NORMAL"

    return {
        "v_mma_series_uv": v_series,
        "timestamps_sec": ts_series,
        "max_v_mma_uv": max_v,
        "mean_v_mma_uv": mean_v,
        "odd_template_uv": t_odd,
        "even_template_uv": t_even,
        "risk_level": risk,
    }
