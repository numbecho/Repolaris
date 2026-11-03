"""T-Wave Peak and Offset (T-End) Delineation module.

Supports four complementary peer-reviewed delineation modes:
1. 'hybrid' (Default): Steepest-descent tangent intersection blended with amplitude threshold
   and sliding-window area fallback for flat or notched T-waves.
2. 'tangent': ICH E14 steepest-descent tangent intersection with the post-T isoelectric baseline
   (Lepeschkin & Surawicz, 1952; Badilini et al., 2005).
3. 'zhang_area': Sliding-Window Area (SWA) integration algorithm (Zhang, Manriquez, Médigue,
   Papelier & Sorine, IEEE Trans. Biomed. Eng. 53(12):2544-2552, 2006) for biphasic/notched T-waves.
4. 'threshold': Isoelectric amplitude fraction crossing fallback.
"""

from __future__ import annotations

import numpy as np


def _detect_t_end_zhang_area(
    segment: np.ndarray,
    t_peak_rel: int,
    fs: float,
    baseline_level: float,
) -> int:
    """Implements Zhang et al. (2006, IEEE TBME) sliding-window area T-wave offset locator.

    Evaluates the integrated area under the T-wave trailing limb within a sliding window W
    relative to a local trailing reference level, maximizing |A(k)| after T-peak.
    """
    n_seg = len(segment)
    w_len = max(4, min(int(round(0.100 * fs)), max(4, (n_seg - t_peak_rel) // 2)))
    p_ref = max(2, int(round(0.016 * fs)))

    search_start = min(n_seg - 2, t_peak_rel + max(2, int(round(0.015 * fs))))
    search_end = n_seg - p_ref
    if search_start >= search_end:
        return min(n_seg - 1, t_peak_rel + max(2, (n_seg - t_peak_rel) // 2))

    # Precompute cumulative sum for O(1) sliding window integration
    csum = np.concatenate([[0.0], np.cumsum(segment, dtype=np.float64)])
    best_k = search_start
    best_area = -1.0

    # Polarity sign relative to post-T baseline
    polarity = 1.0 if float(segment[t_peak_rel]) >= baseline_level else -1.0

    for k in range(search_start, search_end):
        w_start = max(t_peak_rel, k - w_len + 1)
        eff_w = k - w_start + 1
        if eff_w <= 0:
            continue
        win_sum = csum[k + 1] - csum[w_start]
        ref_end = min(n_seg, k + p_ref)
        s_bar = (csum[ref_end] - csum[k]) / float(max(1, ref_end - k))
        area_val = polarity * (win_sum - eff_w * s_bar)
        if area_val > best_area:
            best_area = area_val
            best_k = k

    return int(np.clip(best_k, t_peak_rel + 1, n_seg - 1))


def detect_t_end(
    signal: np.ndarray,
    r_peak: int,
    fs: float,
    search_window_ms: float = 450.0,
    threshold_ratio: float = 0.15,
    method: str = "hybrid",
) -> tuple[int, int]:
    """Locates the T-wave peak and T-wave offset using tangent, Zhang (2006) area, threshold, or hybrid methods."""
    start_offset = int(0.100 * fs)  # Skip QRS recovery
    max_search = int((search_window_ms / 1000.0) * fs)

    start_idx = r_peak + start_offset
    end_idx = min(len(signal), r_peak + max_search)

    if start_idx >= end_idx or (end_idx - start_idx) < 10:
        return r_peak + start_offset, r_peak + start_offset + 5

    segment = signal[start_idx:end_idx]
    baseline_level = float(np.median(segment[-int(len(segment) * 0.2) :])) if len(segment) > 10 else 0.0

    # Support both positive and inverted T-waves by locating dominant deflection from baseline
    dev = segment - baseline_level
    t_peak_rel = int(np.argmax(segment)) if np.max(dev) >= abs(np.min(dev)) * 0.5 else int(np.argmin(segment))
    t_peak_idx = start_idx + t_peak_rel

    descending = segment[t_peak_rel:]
    if len(descending) < 4:
        return t_peak_idx, min(len(signal) - 1, t_peak_idx + int(0.08 * fs))

    method_lower = method.lower()

    # Zhang et al. (2006) sliding-window area delineation
    if method_lower in ("zhang_area", "area", "swa"):
        zhang_rel = _detect_t_end_zhang_area(segment, t_peak_rel, fs, baseline_level)
        return t_peak_idx, min(len(signal) - 1, start_idx + zhang_rel)

    t_amp = float(segment[t_peak_rel])

    # 1. Amplitude threshold estimate
    cutoff = baseline_level + threshold_ratio * (t_amp - baseline_level)
    if t_amp >= baseline_level:
        below_thresh = np.where(descending <= cutoff)[0]
    else:
        below_thresh = np.where(descending >= cutoff)[0]

    if len(below_thresh) > 0:
        thresh_rel = t_peak_rel + int(below_thresh[0])
    else:
        grad_abs = np.abs(np.gradient(descending))
        thresh_rel = t_peak_rel + int(np.argmin(grad_abs))

    if method_lower == "threshold":
        t_end_idx = min(len(signal) - 1, start_idx + thresh_rel)
        return t_peak_idx, t_end_idx

    # 2. Steepest-descent tangent intersection with isoelectric baseline
    deriv = np.gradient(descending)
    steep_idx = int(np.argmin(deriv)) if t_amp >= baseline_level else int(np.argmax(deriv))
    min_slope = float(deriv[steep_idx])
    v_steep = float(descending[steep_idx])

    if abs(min_slope) > 1e-6 and abs(t_amp - baseline_level) > 0.02:
        intersect_offset = (baseline_level - v_steep) / min_slope
        tangent_rel = t_peak_rel + int(round(steep_idx + intersect_offset))
        if t_peak_rel < tangent_rel < len(segment):
            if method_lower == "tangent":
                return t_peak_idx, min(len(signal) - 1, start_idx + tangent_rel)
            # Hybrid consensus: blend tangent intersection and threshold within physiological bounds
            hybrid_rel = int(round(0.5 * (tangent_rel + thresh_rel)))
            return t_peak_idx, min(len(signal) - 1, start_idx + max(t_peak_rel + 1, hybrid_rel))

    # Fallback to Zhang (2006) sliding-window area when tangent slope is flat/ill-conditioned
    zhang_rel = _detect_t_end_zhang_area(segment, t_peak_rel, fs, baseline_level)
    fallback_rel = int(round(0.5 * (thresh_rel + zhang_rel)))
    t_end_idx = min(len(signal) - 1, start_idx + max(t_peak_rel + 1, fallback_rel))
    return t_peak_idx, t_end_idx
