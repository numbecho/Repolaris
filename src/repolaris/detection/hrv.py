"""Comprehensive Heart Rate Variability (HRV) Autonomic Analysis Suite.

Implements international Task Force of the ESC and NASPE (1996) standards for:
1. Time-Domain HRV: SDNN, RMSSD, pNN50, SDANN, SDNN_index, Mean NN, and CV%.
2. Frequency-Domain HRV: Welch PSD over 4.0 Hz Berger step-integrated series across
   ULF (<0.0033 Hz), VLF (0.0033-0.04 Hz), LF (0.04-0.15 Hz), HF (0.15-0.40 Hz),
   LF/HF ratio, and normalized units (LF_nu, HF_nu).
3. Non-Linear Dynamics: Poincaré Plot ellipse geometry (SD1, SD2, SD1/SD2),
   Sample Entropy (SampEn, m=2, r=0.2*SDNN), and Detrended Fluctuation Analysis (DFA alpha1, alpha2).

References:
    - Task Force of the European Society of Cardiology and the North American Society
      of Pacing and Electrophysiology (1996). Heart rate variability: standards of
      measurement, physiological interpretation and clinical use. Circulation, 93(5), 1043-1065.
    - Brennan, M., Palaniswami, M., & Kamen, P. (2001). Do existing measures of Poincaré
      plot geometry reflect nonlinear features of heart rate variability? IEEE TBME, 48(11), 1342-1347.
"""

from __future__ import annotations

from typing import Any
import numpy as np
from scipy.signal import welch

from repolaris.detection.qtvi import resample_berger


def _to_ms_array(nn_intervals: np.ndarray | list[float]) -> np.ndarray:
    """Converts input NN interval array to milliseconds (auto-detects seconds if median < 5.0)."""
    arr = np.asarray(nn_intervals, dtype=np.float64)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if len(arr) == 0:
        return arr
    if float(np.median(arr)) < 10.0:
        return arr * 1000.0
    return arr


def compute_time_domain_hrv(nn_intervals_ms: np.ndarray | list[float]) -> dict[str, float | None]:
    """Computes standard time-domain autonomic metrics over Normal-to-Normal (NN) intervals.

    Args:
        nn_intervals_ms: 1D array of normal-to-normal intervals in ms (or seconds).

    Returns:
        Dictionary with 'sdnn', 'rmssd', 'pnn50', 'mean_nn', 'median_nn', 'cv_percent',
        'sdann', and 'sdnn_index'.
    """
    nn = _to_ms_array(nn_intervals_ms)
    n = len(nn)
    if n < 2:
        return {
            "sdnn": 0.0,
            "rmssd": 0.0,
            "pnn50": 0.0,
            "mean_nn": float(nn[0]) if n == 1 else 0.0,
            "median_nn": float(nn[0]) if n == 1 else 0.0,
            "cv_percent": 0.0,
            "sdann": None,
            "sdnn_index": None,
        }

    mean_nn = float(np.mean(nn))
    median_nn = float(np.median(nn))
    sdnn = float(np.std(nn, ddof=1))
    diffs = np.diff(nn)
    rmssd = float(np.sqrt(np.mean(diffs ** 2)))
    pnn50 = float(np.sum(np.abs(diffs) > 50.0) / float(len(diffs)) * 100.0)
    cv_percent = float((sdnn / mean_nn) * 100.0) if mean_nn > 0 else 0.0

    # 5-minute (300,000 ms) circadian segment metrics (SDANN and SDNN_index)
    cum_ms = np.cumsum(nn)
    seg_duration_ms = 300_000.0
    n_segs = int(cum_ms[-1] // seg_duration_ms)
    sdann: float | None = None
    sdnn_index: float | None = None

    if n_segs >= 2:
        seg_means: list[float] = []
        seg_stds: list[float] = []
        for s_idx in range(n_segs):
            low_t = s_idx * seg_duration_ms
            high_t = (s_idx + 1) * seg_duration_ms
            seg_vals = nn[(cum_ms > low_t) & (cum_ms <= high_t)]
            if len(seg_vals) >= 5:
                seg_means.append(float(np.mean(seg_vals)))
                seg_stds.append(float(np.std(seg_vals, ddof=1)))
        if len(seg_means) >= 2:
            sdann = float(np.std(seg_means, ddof=1))
            sdnn_index = float(np.mean(seg_stds))

    return {
        "sdnn": sdnn,
        "rmssd": rmssd,
        "pnn50": pnn50,
        "mean_nn": mean_nn,
        "median_nn": median_nn,
        "cv_percent": cv_percent,
        "sdann": sdann,
        "sdnn_index": sdnn_index,
    }


def compute_frequency_domain_hrv(
    nn_intervals_ms: np.ndarray | list[float],
    fs_resample: float = 4.0,
) -> dict[str, Any]:
    """Computes Welch power spectral density metrics over 4 Hz Berger-resampled NN series.

    Args:
        nn_intervals_ms: 1D array of NN intervals in ms (or seconds).
        fs_resample: Uniform Berger resampling frequency in Hz (default: 4.0 Hz).

    Returns:
        Dictionary containing 'ulf_power', 'vlf_power', 'lf_power', 'hf_power',
        'total_power', 'lf_hf_ratio', 'lf_nu', 'hf_nu', 'frequencies_hz', and 'psd_ms2_hz'.
    """
    nn_ms = _to_ms_array(nn_intervals_ms)
    if len(nn_ms) < 4:
        return {
            "ulf_power": 0.0,
            "vlf_power": 0.0,
            "lf_power": 0.0,
            "hf_power": 0.0,
            "total_power": 0.0,
            "lf_hf_ratio": 0.0,
            "lf_nu": 0.0,
            "hf_nu": 0.0,
            "frequencies_hz": np.zeros(0, dtype=np.float64),
            "psd_ms2_hz": np.zeros(0, dtype=np.float64),
        }

    cum_sec = np.cumsum(nn_ms / 1000.0)
    t_grid, rr_resampled_sec = resample_berger(cum_sec, fs_resample=fs_resample)
    rr_resampled_ms = rr_resampled_sec * 1000.0
    # Detrend mean before Welch periodogram
    rr_detrended = rr_resampled_ms - np.mean(rr_resampled_ms)

    nperseg = min(len(rr_detrended), 256)
    freqs, psd = welch(rr_detrended, fs=fs_resample, nperseg=nperseg)

    trapz_fn = getattr(np, "trapezoid", getattr(np, "trapz", None))

    def _band_power(f_low: float, f_high: float) -> float:
        mask = (freqs >= f_low) & (freqs <= f_high)
        if np.sum(mask) < 2:
            # Fallback to sum of discrete bins * df if band has 1 bin
            if np.sum(mask) == 1 and len(freqs) > 1:
                df = float(freqs[1] - freqs[0])
                return float(np.sum(psd[mask]) * df)
            return 0.0
        return float(trapz_fn(psd[mask], freqs[mask]))

    ulf = _band_power(0.0, 0.0033)
    vlf = _band_power(0.0033, 0.04)
    lf = _band_power(0.04, 0.15)
    hf = _band_power(0.15, 0.40)
    total_power = ulf + vlf + lf + hf

    lf_hf_ratio = float(lf / hf) if hf > 1e-9 else 0.0
    lf_hf_sum = lf + hf
    lf_nu = float((lf / lf_hf_sum) * 100.0) if lf_hf_sum > 1e-9 else 0.0
    hf_nu = float((hf / lf_hf_sum) * 100.0) if lf_hf_sum > 1e-9 else 0.0

    return {
        "ulf_power": ulf,
        "vlf_power": vlf,
        "lf_power": lf,
        "hf_power": hf,
        "total_power": total_power,
        "lf_hf_ratio": lf_hf_ratio,
        "lf_nu": lf_nu,
        "hf_nu": hf_nu,
        "frequencies_hz": freqs,
        "psd_ms2_hz": psd,
    }


def _compute_sample_entropy(series: np.ndarray, m: int = 2, r_factor: float = 0.2) -> float:
    """Computes Sample Entropy SampEn(m, r) according to Richman & Moorman (2000)."""
    x = np.asarray(series, dtype=np.float64)
    n = len(x)
    if n < m + 2:
        return 0.0
    # Cap length at 300 for fast O(N^2) evaluation
    if n > 300:
        x = x[:300]
        n = 300

    std_val = float(np.std(x, ddof=1))
    if std_val <= 1e-9:
        return 0.0
    tol = r_factor * std_val

    def _count_matches(emb_dim: int) -> int:
        n_vec = n - emb_dim
        templates = np.array([x[i : i + emb_dim] for i in range(n_vec)])
        # Chebyshev (max norm) distance matrix
        diffs = np.max(np.abs(templates[:, None, :] - templates[None, :, :]), axis=2)
        # Exclude self-matches on diagonal
        matches = np.sum(diffs <= tol) - n_vec
        return int(matches)

    b_matches = _count_matches(m)
    a_matches = _count_matches(m + 1)
    if b_matches <= 0 or a_matches <= 0:
        return 0.0
    return float(-np.log(float(a_matches) / float(b_matches)))


def _compute_dfa_exponent(series: np.ndarray, scale_min: int, scale_max: int) -> float:
    """Computes Detrended Fluctuation Analysis (DFA) scaling exponent over [scale_min, scale_max]."""
    x = np.asarray(series, dtype=np.float64)
    n = len(x)
    if n < scale_min + 2:
        return 1.0
    y = np.cumsum(x - np.mean(x))

    eff_max = min(scale_max, n // 2)
    if eff_max <= scale_min:
        return 1.0

    scales = np.unique(np.linspace(scale_min, eff_max, num=min(8, eff_max - scale_min + 1), dtype=int))
    flucts: list[float] = []
    valid_scales: list[int] = []

    for s in scales:
        n_segs = n // s
        if n_segs < 1:
            continue
        rms_vals: list[float] = []
        t_idx = np.arange(s, dtype=np.float64)
        for k in range(n_segs):
            seg = y[k * s : (k + 1) * s]
            poly = np.polyfit(t_idx, seg, 1)
            trend = poly[0] * t_idx + poly[1]
            rms_vals.append(float(np.mean((seg - trend) ** 2)))
        f_s = float(np.sqrt(np.mean(rms_vals)))
        if f_s > 1e-9:
            flucts.append(f_s)
            valid_scales.append(int(s))

    if len(valid_scales) < 2:
        return 1.0
    slope = float(np.polyfit(np.log10(valid_scales), np.log10(flucts), 1)[0])
    return slope


def compute_nonlinear_hrv(nn_intervals_ms: np.ndarray | list[float]) -> dict[str, float]:
    """Evaluates non-linear autonomic dynamics (Poincaré SD1/SD2, Sample Entropy, and DFA).

    Args:
        nn_intervals_ms: 1D array of NN intervals in ms (or seconds).

    Returns:
        Dictionary containing 'sd1', 'sd2', 'sd1_sd2_ratio', 'ellipse_area_ms2',
        'sampen', 'alpha_1', and 'alpha_2'.
    """
    nn = _to_ms_array(nn_intervals_ms)
    if len(nn) < 3:
        return {
            "sd1": 0.0,
            "sd2": 0.0,
            "sd1_sd2_ratio": 0.0,
            "ellipse_area_ms2": 0.0,
            "sampen": 0.0,
            "alpha_1": 0.0,
            "alpha_2": 0.0,
        }

    diffs = np.diff(nn)
    var_nn = float(np.var(nn, ddof=1))
    var_diff = float(np.var(diffs, ddof=1))

    sd1 = float(np.sqrt(0.5 * var_diff))
    sd2_sq = max(0.0, 2.0 * var_nn - 0.5 * var_diff)
    sd2 = float(np.sqrt(sd2_sq))
    sd1_sd2_ratio = float(sd1 / sd2) if sd2 > 1e-9 else 0.0
    ellipse_area = float(np.pi * sd1 * sd2)

    sampen = _compute_sample_entropy(nn, m=2, r_factor=0.2)
    alpha_1 = _compute_dfa_exponent(nn, scale_min=4, scale_max=11)
    alpha_2 = _compute_dfa_exponent(nn, scale_min=12, scale_max=64)

    return {
        "sd1": sd1,
        "sd2": sd2,
        "sd1_sd2_ratio": sd1_sd2_ratio,
        "ellipse_area_ms2": ellipse_area,
        "sampen": sampen,
        "alpha_1": alpha_1,
        "alpha_2": alpha_2,
    }


def compute_comprehensive_hrv(
    nn_intervals_ms: np.ndarray | list[float],
    fs_resample: float = 4.0,
) -> dict[str, Any]:
    """Executes complete Time-Domain, Frequency-Domain, and Non-Linear HRV analysis."""
    return {
        "time_domain": compute_time_domain_hrv(nn_intervals_ms),
        "frequency_domain": compute_frequency_domain_hrv(nn_intervals_ms, fs_resample=fs_resample),
        "nonlinear": compute_nonlinear_hrv(nn_intervals_ms),
    }
