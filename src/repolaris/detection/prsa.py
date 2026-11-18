"""Phase-Rectified Signal Averaging (PRSA) Deceleration & Acceleration Capacity module.

Implements non-stationary autonomic vagal and sympathetic quantification from continuous
Holter recordings via Phase-Rectified Signal Averaging (Bauer et al., The Lancet 2006).

Unlike Heart Rate Turbulence (HRT), which requires spontaneous solitary PVCs, PRSA
Deceleration Capacity (DC) and Acceleration Capacity (AC) operate on any sinus recording
regardless of ectopy burden while suppressing non-stationary daily activity and noise.

References:
    - Bauer A., Kantelhardt J.W., Barthel P., et al. (2006). "Deceleration capacity of
      heart rate as a predictor of mortality after myocardial infarction: cohort study."
      The Lancet, 367(9523), 1674-1681.
    - Kantelhardt J.W., Bauer A., Schumann A.Y., et al. (2007). "Phase-rectified signal
      averaging for the detection of quasi-periodicities and the prediction of
      cardiovascular risk." Chaos, 17(1), 015112.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def compute_prsa_capacity(
    rr_intervals_ms: np.ndarray | list[float],
    beat_classes: list[str] | None = None,
    window_half_width: int = 16,
    anchor_filter_t: int = 1,
    wavelet_scale_s: int = 2,
    max_change_ratio: float = 0.20,
) -> dict[str, Any]:
    """Computes Deceleration Capacity (DC) and Acceleration Capacity (AC) of heart rate via PRSA.

    Formulas (Haar wavelet evaluation at scale s=2):
        DC = (X_dec[0] + X_dec[1] - X_dec[-1] - X_dec[-2]) / 4
        AC = (X_acc[0] + X_acc[1] - X_acc[-1] - X_acc[-2]) / 4

    Validated Bauer et al. (2006) Post-MI Mortality Risk Cutoffs for DC:
        - Low Risk (preserved vagal tone): DC > 4.5 ms
        - Intermediate Risk: 2.5 ms < DC <= 4.5 ms
        - High Risk (severe vagal impairment): DC <= 2.5 ms

    Args:
        rr_intervals_ms: 1D sequence of RR/NN intervals in milliseconds (auto-scaled from
            seconds if median < 3.0).
        beat_classes: Optional list of AAMI beat class codes ('N', 'V', 'S', 'F', 'Q') to
            filter out ectopic steps before anchor selection.
        window_half_width: Half-length L of the phase-rectified averaging window [-L, L-1]
            (default: 16; automatically shrinks on short recordings).
        anchor_filter_t: Anchor averaging length T (default: 1).
        wavelet_scale_s: Central Haar wavelet scale s (default: 2).
        max_change_ratio: Maximum allowed beat-to-beat step ratio to reject artifacts/ectopy
            (default: 0.20 = 20%).

    Returns:
        Dictionary with `dc_ms`, `ac_ms`, `deceleration_anchors`, `acceleration_anchors`,
        `prsa_deceleration_curve`, `prsa_acceleration_curve`, `risk_category`, and `valid`.
    """
    raw_rr = np.asarray(rr_intervals_ms, dtype=np.float64)
    finite_mask = np.isfinite(raw_rr) & (raw_rr > 0)
    if int(np.sum(finite_mask)) < 6:
        return {
            "valid": False,
            "dc_ms": 0.0,
            "ac_ms": 0.0,
            "deceleration_anchors": 0,
            "acceleration_anchors": 0,
            "prsa_deceleration_curve": [],
            "prsa_acceleration_curve": [],
            "risk_category": "INSUFFICIENT_DATA",
        }

    if float(np.median(raw_rr[finite_mask])) < 3.0:
        raw_rr = raw_rr * 1000.0

    # Keep physiological intervals (250 ms to 2500 ms) and mark normal sinus positions
    n_tot = len(raw_rr)
    is_sinus = np.ones(n_tot, dtype=bool)
    if beat_classes is not None and len(beat_classes) == n_tot:
        sinus_flags = np.array([str(c).upper() == "N" for c in beat_classes], dtype=bool)
        if int(np.sum(sinus_flags)) >= 6:
            is_sinus = sinus_flags

    phys_valid = np.isfinite(raw_rr) & (raw_rr >= 250.0) & (raw_rr <= 2500.0) & is_sinus
    rr_clean = raw_rr[phys_valid]
    n_clean = len(rr_clean)
    if n_clean < 6:
        return {
            "valid": False,
            "dc_ms": 0.0,
            "ac_ms": 0.0,
            "deceleration_anchors": 0,
            "acceleration_anchors": 0,
            "prsa_deceleration_curve": [],
            "prsa_acceleration_curve": [],
            "risk_category": "INSUFFICIENT_DATA",
        }

    s = max(1, int(wavelet_scale_s))
    t_filt = max(1, int(anchor_filter_t))
    half_l = max(s, min(int(window_half_width), (n_clean - 2) // 2))
    if half_l < s:
        s = max(1, half_l)

    dec_windows: list[np.ndarray] = []
    acc_windows: list[np.ndarray] = []

    start_idx = max(half_l, t_filt)
    end_idx = n_clean - max(half_l, t_filt)

    for idx in range(start_idx, end_idx):
        prev_val = float(rr_clean[idx - 1])
        curr_val = float(rr_clean[idx])
        if prev_val <= 1e-6:
            continue
        rel_change = abs(curr_val - prev_val) / prev_val
        if rel_change > max_change_ratio or rel_change < 1e-7:
            continue

        left_mean = float(np.mean(rr_clean[idx - t_filt : idx]))
        right_mean = float(np.mean(rr_clean[idx : idx + t_filt]))

        win = rr_clean[idx - half_l : idx + half_l]
        if len(win) != 2 * half_l:
            continue

        if right_mean > left_mean:
            dec_windows.append(win)
        elif right_mean < left_mean:
            acc_windows.append(win)

    if dec_windows:
        dec_curve = np.mean(np.stack(dec_windows, axis=0), axis=0)
        right_sum = float(np.sum(dec_curve[half_l : half_l + s]))
        left_sum = float(np.sum(dec_curve[half_l - s : half_l]))
        dc_ms = (right_sum - left_sum) / (2.0 * s)
    else:
        dec_curve = np.zeros(2 * half_l, dtype=np.float64)
        dc_ms = 0.0

    if acc_windows:
        acc_curve = np.mean(np.stack(acc_windows, axis=0), axis=0)
        right_sum_a = float(np.sum(acc_curve[half_l : half_l + s]))
        left_sum_a = float(np.sum(acc_curve[half_l - s : half_l]))
        ac_ms = (right_sum_a - left_sum_a) / (2.0 * s)
    else:
        acc_curve = np.zeros(2 * half_l, dtype=np.float64)
        ac_ms = 0.0

    if not dec_windows:
        risk_cat = "INSUFFICIENT_ANCHORS"
    elif dc_ms <= 2.5:
        risk_cat = "HIGH_RISK"
    elif dc_ms <= 4.5:
        risk_cat = "INTERMEDIATE_RISK"
    else:
        risk_cat = "LOW_RISK"

    return {
        "valid": bool(len(dec_windows) > 0),
        "dc_ms": round(float(dc_ms), 3),
        "ac_ms": round(float(ac_ms), 3),
        "deceleration_anchors": len(dec_windows),
        "acceleration_anchors": len(acc_windows),
        "window_half_width": int(half_l),
        "wavelet_scale_s": int(s),
        "prsa_deceleration_curve": [round(float(v), 3) for v in dec_curve],
        "prsa_acceleration_curve": [round(float(v), 3) for v in acc_curve],
        "risk_category": risk_cat,
    }
