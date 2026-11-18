"""Q-Wave Onset and QRS Offset (J-Point) Fiducial Delineation module.

Provides deterministic, gradient-inflection locators for:
1. Q-onset (`detect_q_onset`): Beginning of ventricular depolarization prior to the R-peak.
2. J-point (`detect_j_point`): End of ventricular depolarization (QRS offset) and junction
   with the ST segment, required for FDA CiPA J-Tpeakc sub-interval decomposition
   (Johannesen et al., CPT 2014 / JAHA 2016).
"""

from __future__ import annotations

import numpy as np


def detect_q_onset(signal: np.ndarray, r_peak: int, fs: float, search_window_ms: float = 100.0) -> int:
    """Finds the Q-wave trough and Q-onset (inflection point prior to depolarization)."""
    window_samples = int((search_window_ms / 1000.0) * fs)
    start_idx = max(0, r_peak - window_samples)

    segment = signal[start_idx:r_peak]
    if len(segment) < 4:
        return max(0, r_peak - 1)

    # Q-trough is the minimum voltage immediately before the R-peak
    q_trough_rel = int(np.argmin(segment))

    # Find onset before Q-trough by searching for flat baseline derivative
    pre_q = segment[:q_trough_rel] if q_trough_rel > 2 else segment
    grad = np.abs(np.gradient(pre_q))
    onset_rel = int(np.argmin(grad)) if len(grad) > 0 else 0

    return int(start_idx + onset_rel)


def detect_j_point(
    signal: np.ndarray,
    r_peak: int,
    fs: float,
    search_window_ms: float = 100.0,
) -> int:
    """Locates the J-point (QRS offset / ST-segment junction) following an R-peak.

    Searches forward from the R-peak to locate the S-wave nadir within the initial
    60 ms post-R window, then identifies the inflection point where the recovery slope
    flattens into the ST segment.

    Args:
        signal: 1D conditioned ECG signal array.
        r_peak: Sample index of the R-wave peak.
        fs: Sampling frequency in Hz.
        search_window_ms: Post-R search horizon in milliseconds (default: 100.0 ms).

    Returns:
        Sample index of the J-point bounded within physiological limits after `r_peak`.
    """
    n_samples = len(signal)
    if n_samples == 0:
        return 0

    min_offset = max(1, int(round(0.014 * fs)))
    max_offset = max(min_offset + 2, int(round(min(search_window_ms, 65.0) / 1000.0 * fs)))

    start_idx = min(n_samples - 1, max(0, int(r_peak) + min_offset))
    end_idx = min(n_samples, max(start_idx + 1, int(r_peak) + max_offset))

    segment = signal[start_idx:end_idx]
    if len(segment) < 4:
        return min(n_samples - 1, int(r_peak) + max(1, int(round(0.036 * fs))))

    # Locate S-wave trough within [14 ms, 44 ms] post-R
    s_search_len = min(len(segment), max(2, int(round(0.030 * fs))))
    s_trough_rel = int(np.argmin(segment[:s_search_len]))

    recovery_horizon = min(len(segment) - s_trough_rel, max(3, int(round(0.026 * fs))))
    post_s = segment[s_trough_rel : s_trough_rel + recovery_horizon]
    if len(post_s) < 3:
        j_idx = start_idx + s_trough_rel
        return int(np.clip(j_idx, min(n_samples - 1, int(r_peak) + min_offset), n_samples - 1))

    grad = np.abs(np.gradient(post_s))
    max_grad = float(np.max(grad))
    if max_grad > 1e-6:
        # First sample after peak recovery slope where derivative drops below 18% of max slope
        peak_slope_rel = int(np.argmax(grad))
        tail_grad = grad[peak_slope_rel:]
        below = np.where(tail_grad <= 0.18 * max_grad)[0]
        if len(below) > 0:
            j_rel = s_trough_rel + peak_slope_rel + int(below[0])
        else:
            j_rel = s_trough_rel + peak_slope_rel + int(np.argmin(tail_grad))
    else:
        j_rel = s_trough_rel + int(np.argmin(grad))

    phys_max = min(n_samples - 1, int(r_peak) + max(2, int(round(0.056 * fs))))
    phys_min = min(phys_max, int(r_peak) + max(1, int(round(0.018 * fs))))
    return int(np.clip(start_idx + j_rel, phys_min, phys_max))
