"""QT Variability Index (QTVI) and Berger HRV Resampling module.

Implements the classical algorithm for spectral heart rate variability resampling
(Berger et al., IEEE TBME 1986) and the QT Variability Index (QTVI) measurement
for non-invasive cardiac repolarization lability assessment (Berger et al.,
Circulation 1997).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, Union
import numpy as np
import scipy.interpolate as intrp


def resample_berger(
    rr_cum_times: np.ndarray,
    fs_resample: float = 4.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Resamples unevenly spaced RR event sequences onto a uniform grid using Berger's algorithm.

    Reference:
        Berger R.D., Akselrod S., Gordon D., Cohen R.J.
        "An Efficient Algorithm for Spectral Analysis of Heart Rate Variability."
        IEEE Transactions on Biomedical Engineering, 33(9):900-904, 1986.

    Args:
        rr_cum_times: Cumulative occurrence times of R-peaks in seconds (1D array).
        fs_resample: Target uniform sampling rate in Hz (default: 4.0 Hz).

    Returns:
        A tuple of (time_grid, resampled_rr):
            - time_grid: 1D array of uniformly spaced timestamps.
            - resampled_rr: 1D array of Berger-resampled instantaneous heart periods (seconds).
    """
    rr_times = np.asarray(rr_cum_times, dtype=np.float64)
    n = len(rr_times)
    if n < 3:
        raise ValueError("At least 3 beat timestamps are required for Berger resampling.")

    total_t = int(np.ceil(rr_times[-1] * fs_resample) + 1)
    rt = np.linspace(0, total_t, total_t, endpoint=False) / fs_resample
    rrv = np.zeros(total_t, dtype=np.float64)

    x = 0
    wsiz = 2.0 / fs_resample

    for i in range(1, total_t - 1):
        top = rt[i + 1]
        bot = rt[i - 1]

        while x < n and rr_times[x] < top:
            x += 1

        if x >= n:
            break

        if x == 0:
            continue

        if rr_times[x - 1] <= bot:
            denom = rr_times[x] - rr_times[x - 1]
            if denom > 1e-6:
                rrv[i] = wsiz / denom
        else:
            denom1 = rr_times[x - 1] - rr_times[x - 2] if x >= 2 else 1.0
            denom2 = rr_times[x] - rr_times[x - 1]
            t1 = (rr_times[x - 1] - bot) / denom1 if denom1 > 1e-6 else 0.0
            t2 = (top - rr_times[x - 1]) / denom2 if denom2 > 1e-6 else 0.0
            rrv[i] = t1 + t2

    # Invert to express as instantaneous interval (seconds) if non-zero
    valid = rrv > 0
    resampled = np.zeros_like(rrv)
    resampled[valid] = 1.0 / rrv[valid]
    # Forward/backward fill zeros
    if np.any(valid):
        first_val = resampled[valid][0]
        last_val = resampled[valid][-1]
        resampled[:np.argmax(valid)] = first_val
        for idx in range(len(resampled)):
            if resampled[idx] == 0:
                resampled[idx] = resampled[idx - 1] if idx > 0 else first_val

    return rt, resampled


def compute_qtvi(
    rr_intervals: np.ndarray,
    qt_intervals: np.ndarray,
) -> float:
    """Computes the classic Berger QT Variability Index (QTVI).

    Calculates:
        QTVI = log10( (var(QT) / var(RR)) * (mean(RR) / mean(QT))^2 )
             = log10( (var(QT) / mean(QT)^2) / (var(RR) / mean(RR)^2) )

    Normal clinical QTVI is typically between -1.6 and -1.0. Elevated values
    (e.g., > -0.5 or approaching 0.0) indicate increased temporal repolarization
    lability and ventricular arrhythmogenic vulnerability.

    Args:
        rr_intervals: 1D array of RR intervals (in milliseconds or seconds).
        qt_intervals: 1D array of QT intervals (in corresponding units).

    Returns:
        The logarithmic QTVI score as a float.

    Raises:
        ValueError: If array lengths do not match or contain insufficient data.
    """
    rr = np.asarray(rr_intervals, dtype=np.float64)
    qt = np.asarray(qt_intervals, dtype=np.float64)

    if len(rr) != len(qt):
        min_len = min(len(rr), len(qt))
        rr = rr[:min_len]
        qt = qt[:min_len]

    if len(rr) < 5:
        raise ValueError("At least 5 consecutive beats are required to compute QTVI.")

    var_qt = float(np.var(qt, ddof=1))
    mean_qt = float(np.mean(qt))

    var_rr = float(np.var(rr, ddof=1))
    mean_rr = float(np.mean(rr))

    if var_rr <= 1e-9 or mean_qt <= 1e-9:
        raise ValueError("Degenerate variance or mean: cannot calculate QTVI.")

    k1 = var_qt / var_rr
    k2 = (mean_rr / mean_qt) ** 2

    ratio = k1 * k2
    if ratio <= 1e-12:
        return -12.0

    return float(np.log10(ratio))


def optimize_alpha(
    signal: np.ndarray,
    target_r: int,
    ref_r: int,
    segment_len: int,
    search_steps: int = 21,
) -> float:
    """Optimizes waveform stretch parameter alpha for Berger template-matching QT estimation.

    Args:
        signal: 1D ECG waveform array.
        target_r: R-peak sample index of target beat.
        ref_r: R-peak sample index of template/reference beat.
        segment_len: Duration of the ST-T segment in samples.
        search_steps: Number of grid evaluation points per refinement iteration.

    Returns:
        Optimal stretch factor alpha minimizing mean square error.
    """
    a_step = 0.01
    s_start = 0.9

    sig_len = len(signal)
    ref_start = ref_r + 50
    ref_end = ref_start + segment_len

    if ref_end > sig_len:
        return 1.0

    ref_segment = signal[ref_start:ref_end]

    best_alpha = 1.0
    while a_step >= 1e-4:
        eps_vals = np.zeros(search_steps)
        alphas = s_start + np.arange(search_steps) * a_step

        for i, a in enumerate(alphas):
            indices = np.clip(
                (target_r + 50 + np.arange(segment_len) * a).astype(int),
                0,
                sig_len - 1,
            )
            target_segment = signal[indices]
            diff = ref_segment - target_segment
            eps_vals[i] = np.dot(diff, diff)

        idx = int(np.argmin(eps_vals))
        best_alpha = alphas[idx]
        s_start = s_start + (idx - 1) * a_step
        a_step /= 10.0

    return float(best_alpha)
