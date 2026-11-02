"""T-Wave Peak and Offset (T-End) Delineation module.

Implements hybrid steepest-descent tangent intersection with the isoelectric baseline
complemented by an amplitude-threshold fallback for flat or biphasic T-waves.
"""

from __future__ import annotations

import numpy as np


def detect_t_end(
    signal: np.ndarray,
    r_peak: int,
    fs: float,
    search_window_ms: float = 450.0,
    threshold_ratio: float = 0.15,
    method: str = "hybrid",
) -> tuple[int, int]:
    """Locates the T-wave peak and T-wave offset using steepest-descent tangent and threshold methods."""
    start_offset = int(0.100 * fs)  # Skip QRS recovery
    max_search = int((search_window_ms / 1000.0) * fs)

    start_idx = r_peak + start_offset
    end_idx = min(len(signal), r_peak + max_search)

    if start_idx >= end_idx or (end_idx - start_idx) < 10:
        return r_peak + start_offset, r_peak + start_offset + 5

    segment = signal[start_idx:end_idx]
    t_peak_rel = int(np.argmax(segment))
    t_peak_idx = start_idx + t_peak_rel

    # Analyze descending slope after T-peak
    descending = segment[t_peak_rel:]
    if len(descending) < 4:
        return t_peak_idx, min(len(signal) - 1, t_peak_idx + int(0.08 * fs))

    t_amp = float(segment[t_peak_rel])
    baseline_level = float(np.median(segment[-int(len(segment) * 0.2) :])) if len(segment) > 10 else 0.0

    # 1. Amplitude threshold estimate
    cutoff = baseline_level + threshold_ratio * (t_amp - baseline_level)
    below_thresh = np.where(descending <= cutoff)[0]
    if len(below_thresh) > 0:
        thresh_rel = t_peak_rel + int(below_thresh[0])
    else:
        grad_abs = np.abs(np.gradient(descending))
        thresh_rel = t_peak_rel + int(np.argmin(grad_abs))

    if method == "threshold":
        t_end_idx = min(len(signal) - 1, start_idx + thresh_rel)
        return t_peak_idx, t_end_idx

    # 2. Steepest-descent tangent intersection with isoelectric baseline
    deriv = np.gradient(descending)
    steep_idx = int(np.argmin(deriv))
    min_slope = float(deriv[steep_idx])
    v_steep = float(descending[steep_idx])

    if min_slope < -1e-6 and (t_amp - baseline_level) > 0.02:
        # Solve: v_steep + min_slope * (x - steep_idx) = baseline_level
        intersect_offset = (baseline_level - v_steep) / min_slope
        tangent_rel = t_peak_rel + int(round(steep_idx + intersect_offset))
        if t_peak_rel < tangent_rel < len(segment):
            if method == "tangent":
                return t_peak_idx, min(len(signal) - 1, start_idx + tangent_rel)
            # Hybrid consensus: blend tangent intersection and threshold within physiological bounds
            hybrid_rel = int(round(0.5 * (tangent_rel + thresh_rel)))
            return t_peak_idx, min(len(signal) - 1, start_idx + max(t_peak_rel + 1, hybrid_rel))

    t_end_idx = min(len(signal) - 1, start_idx + thresh_rel)
    return t_peak_idx, t_end_idx
