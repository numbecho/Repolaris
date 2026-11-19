"""ANSI/AAMI EC57 Beat/Episode Evaluator and CSE Fiducial Delineation Benchmark Engine.

Implements:
1. 1-to-1 Monotonic Bipartite Beat Matching (`bxb`) within the AAMI EC57 +/- 150 ms
   tolerance window, computing TP, FP, FN, Sensitivity (Se), Positive Predictivity (+P),
   Detection Error Rate (DER), F1 score, and the 5x5 AAMI EC57 classification confusion
   matrix (N, S, V, F, Q).
2. Common Standards for Quantitative Electrocardiography (CSE) / PhysioNet QT Database
   (QTDB) Fiducial Delineation Verification for P_onset, P_peak, P_end, Q_onset, R_peak,
   J_point, T_peak, and T_end against statutory referee standard deviation tolerances.
3. Episode Overlap Evaluation (`epi`) for Atrial Fibrillation and ST-segment ischemic
   episodes per ANSI/AAMI EC57.

References:
    - ANSI/AAMI EC57:2012 (R2020), "Testing and Reporting Performance Results of Cardiac
      Rhythm and ST Segment Measurement Algorithms."
    - The CSE Working Party (1985), "Recommendations for measurement standards in
      quantitative electrocardiography." European Heart Journal, 6(10), 815-825.
    - Laguna P., Mark R.G., Goldberg A., Moody G.B. (1997), "A database for evaluation
      of algorithms for measurement of QT and other waveform intervals in the ECG."
      Computers in Cardiology, 24, 673-676.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from repolaris.detection.pulse_metrics import compute_stv_qt
from repolaris.detection.q_onset import detect_j_point, detect_q_onset
from repolaris.detection.qrs import detect_r_peaks
from repolaris.detection.t_end import detect_t_end

AAMI_CLASSES: tuple[str, ...] = ("N", "S", "V", "F", "Q")

# Statutory CSE Working Party / QTDB referee standard deviation tolerances (in ms)
CSE_SD_TOLERANCES_MS: dict[str, float] = {
    "p_onset": 10.2,
    "p_peak": 11.0,
    "p_end": 12.7,
    "q_onset": 6.5,
    "r_peak": 6.0,
    "j_point": 11.6,
    "t_peak": 15.0,
    "t_end": 30.6,
}


def evaluate_qrs_and_classification_ec57(
    ref_samples: np.ndarray | list[int],
    test_samples: np.ndarray | list[int],
    fs: float,
    ref_classes: list[str] | None = None,
    test_classes: list[str] | None = None,
    match_window_ms: float = 150.0,
    learning_period_sec: float = 0.0,
) -> dict[str, Any]:
    """Evaluates QRS detection and 5-class AAMI EC57 beat classification via 1-to-1 `bxb` matching."""
    if fs <= 0:
        raise ValueError("Sampling frequency fs must be positive.")

    ref_arr = np.asarray(ref_samples, dtype=np.int64)
    test_arr = np.asarray(test_samples, dtype=np.int64)

    min_sample = int(round(max(0.0, learning_period_sec) * fs))
    ref_mask = ref_arr >= min_sample
    test_mask = test_arr >= min_sample

    ref_valid = ref_arr[ref_mask]
    test_valid = test_arr[test_mask]

    if ref_classes is not None and len(ref_classes) == len(ref_arr):
        ref_cls_valid = [str(c).upper() for c, keep in zip(ref_classes, ref_mask, strict=False) if keep]
    else:
        ref_cls_valid = ["N"] * len(ref_valid)

    if test_classes is not None and len(test_classes) == len(test_arr):
        test_cls_valid = [str(c).upper() for c, keep in zip(test_classes, test_mask, strict=False) if keep]
    else:
        test_cls_valid = ["N"] * len(test_valid)

    tol_samples = int(round((match_window_ms / 1000.0) * fs))

    # Build candidate pairs (|test - ref| <= tol_samples) sorted by absolute time difference
    candidate_pairs: list[tuple[int, int, int]] = []
    for r_idx, r_samp in enumerate(ref_valid):
        if len(test_valid) == 0:
            break
        diffs = np.abs(test_valid - r_samp)
        within = np.where(diffs <= tol_samples)[0]
        for t_idx in within:
            candidate_pairs.append((int(diffs[t_idx]), int(r_idx), int(t_idx)))

    candidate_pairs.sort(key=lambda item: (item[0], item[1], item[2]))

    matched_ref: set[int] = set()
    matched_test: set[int] = set()
    matched_pairs: list[tuple[int, int]] = []
    timing_errors_ms: list[float] = []

    for _, r_idx, t_idx in candidate_pairs:
        if r_idx not in matched_ref and t_idx not in matched_test:
            matched_ref.add(r_idx)
            matched_test.add(t_idx)
            matched_pairs.append((r_idx, t_idx))
            err_ms = float(test_valid[t_idx] - ref_valid[r_idx]) / fs * 1000.0
            timing_errors_ms.append(err_ms)

    matched_pairs.sort(key=lambda p: p[0])

    tp = len(matched_pairs)
    fn = max(0, len(ref_valid) - tp)
    fp = max(0, len(test_valid) - tp)

    se = (tp / (tp + fn) * 100.0) if (tp + fn) > 0 else 100.0
    pp = (tp / (tp + fp) * 100.0) if (tp + fp) > 0 else 100.0
    der = ((fp + fn) / (tp + fn) * 100.0) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * se * pp / (se + pp)) if (se + pp) > 0 else 0.0

    # 5x5 AAMI EC57 Confusion Matrix
    confusion: dict[str, dict[str, int]] = {
        rc: dict.fromkeys(AAMI_CLASSES, 0) for rc in AAMI_CLASSES
    }
    for r_idx, t_idx in matched_pairs:
        r_label = ref_cls_valid[r_idx] if ref_cls_valid[r_idx] in AAMI_CLASSES else "Q"
        t_label = test_cls_valid[t_idx] if test_cls_valid[t_idx] in AAMI_CLASSES else "Q"
        confusion[r_label][t_label] += 1

    per_class_metrics: dict[str, dict[str, float]] = {}
    for cls in AAMI_CLASSES:
        c_tp = confusion[cls][cls]
        c_fn = sum(confusion[cls][other] for other in AAMI_CLASSES if other != cls)
        c_fp = sum(confusion[other][cls] for other in AAMI_CLASSES if other != cls)
        c_se = (c_tp / (c_tp + c_fn) * 100.0) if (c_tp + c_fn) > 0 else 100.0
        c_pp = (c_tp / (c_tp + c_fp) * 100.0) if (c_tp + c_fp) > 0 else 100.0
        per_class_metrics[cls] = {
            "tp": float(c_tp),
            "fn": float(c_fn),
            "fp": float(c_fp),
            "sensitivity_pct": round(c_se, 2),
            "positive_predictivity_pct": round(c_pp, 2),
        }

    err_arr = np.asarray(timing_errors_ms, dtype=np.float64) if timing_errors_ms else np.zeros(1)
    return {
        "protocol": "ANSI/AAMI EC57 (bxb)",
        "match_window_ms": float(match_window_ms),
        "learning_period_sec": float(learning_period_sec),
        "total_reference_beats": len(ref_valid),
        "total_test_beats": len(test_valid),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "sensitivity_pct": round(se, 2),
        "positive_predictivity_pct": round(pp, 2),
        "der_pct": round(der, 3),
        "f1_score_pct": round(f1, 2),
        "mean_timing_error_ms": round(float(np.mean(err_arr)), 3) if timing_errors_ms else 0.0,
        "sd_timing_error_ms": round(float(np.std(err_arr, ddof=1 if len(err_arr) > 1 else 0)), 3) if timing_errors_ms else 0.0,
        "matched_pairs": matched_pairs,
        "confusion_matrix": confusion,
        "per_class_metrics": per_class_metrics,
    }


def evaluate_fiducial_delineation_cse(
    ref_fiducials: dict[str, np.ndarray | list[int]],
    test_fiducials: dict[str, np.ndarray | list[int]],
    fs: float,
    max_error_ms: float = 150.0,
) -> dict[str, Any]:
    """Evaluates wave boundary delineation errors (mean m and SD sigma in ms) against CSE referee tolerances."""
    if fs <= 0:
        raise ValueError("Sampling frequency fs must be positive.")

    fiducial_reports: dict[str, dict[str, Any]] = {}
    all_passed = True

    for fid_name, cse_tol_ms in CSE_SD_TOLERANCES_MS.items():
        if fid_name not in ref_fiducials or fid_name not in test_fiducials:
            continue
        r_pts = np.asarray(ref_fiducials[fid_name], dtype=np.float64)
        t_pts = np.asarray(test_fiducials[fid_name], dtype=np.float64)
        n_common = min(len(r_pts), len(t_pts))
        if n_common == 0:
            continue

        diffs_ms = (t_pts[:n_common] - r_pts[:n_common]) / fs * 1000.0
        valid_mask = np.isfinite(diffs_ms) & (np.abs(diffs_ms) <= max_error_ms)
        valid_diffs = diffs_ms[valid_mask]

        if len(valid_diffs) == 0:
            continue

        mean_err = float(np.mean(valid_diffs))
        sd_err = float(np.std(valid_diffs, ddof=1 if len(valid_diffs) > 1 else 0))
        mae_err = float(np.mean(np.abs(valid_diffs)))
        passed = bool(sd_err <= cse_tol_ms)
        if not passed:
            all_passed = False

        fiducial_reports[fid_name] = {
            "evaluated_beats": int(len(valid_diffs)),
            "mean_error_ms": round(mean_err, 3),
            "sd_error_ms": round(sd_err, 3),
            "mae_ms": round(mae_err, 3),
            "cse_tolerance_sd_ms": float(cse_tol_ms),
            "within_cse_tolerance": passed,
        }

    return {
        "protocol": "CSE Working Party / PhysioNet QTDB",
        "fiducials": fiducial_reports,
        "all_within_cse_limits": bool(all_passed and len(fiducial_reports) > 0),
    }


def evaluate_episode_overlap_ec57(
    ref_episodes: list[tuple[float, float]],
    test_episodes: list[tuple[float, float]],
    total_duration_sec: float,
) -> dict[str, Any]:
    """Evaluates episode-level and duration-weighted overlap sensitivity and +P per ANSI/AAMI EC57 (`epi`)."""
    dur = max(1.0, float(total_duration_sec))
    grid_hz = 10.0  # 100 ms resolution grid for exact interval intersection
    n_bins = max(1, int(round(dur * grid_hz)))

    ref_mask = np.zeros(n_bins, dtype=bool)
    test_mask = np.zeros(n_bins, dtype=bool)

    for start_s, end_s in ref_episodes:
        i0 = max(0, min(n_bins, int(round(start_s * grid_hz))))
        i1 = max(i0, min(n_bins, int(round(end_s * grid_hz))))
        ref_mask[i0:i1] = True

    for start_s, end_s in test_episodes:
        i0 = max(0, min(n_bins, int(round(start_s * grid_hz))))
        i1 = max(i0, min(n_bins, int(round(end_s * grid_hz))))
        test_mask[i0:i1] = True

    tp_bins = int(np.sum(ref_mask & test_mask))
    fn_bins = int(np.sum(ref_mask & (~test_mask)))
    fp_bins = int(np.sum((~ref_mask) & test_mask))
    union_bins = int(np.sum(ref_mask | test_mask))

    dur_se = (tp_bins / (tp_bins + fn_bins) * 100.0) if (tp_bins + fn_bins) > 0 else 100.0
    dur_pp = (tp_bins / (tp_bins + fp_bins) * 100.0) if (tp_bins + fp_bins) > 0 else 100.0
    jaccard = (tp_bins / union_bins * 100.0) if union_bins > 0 else 100.0

    # Episode-by-episode hit rate
    ref_hits = 0
    for r0, r1 in ref_episodes:
        if any(max(r0, t0) < min(r1, t1) for t0, t1 in test_episodes):
            ref_hits += 1

    test_hits = 0
    for t0, t1 in test_episodes:
        if any(max(r0, t0) < min(r1, t1) for r0, r1 in ref_episodes):
            test_hits += 1

    ep_se = (ref_hits / len(ref_episodes) * 100.0) if ref_episodes else 100.0
    ep_pp = (test_hits / len(test_episodes) * 100.0) if test_episodes else 100.0

    return {
        "protocol": "ANSI/AAMI EC57 (epi)",
        "reference_episode_count": len(ref_episodes),
        "test_episode_count": len(test_episodes),
        "episode_sensitivity_pct": round(ep_se, 2),
        "episode_positive_predictivity_pct": round(ep_pp, 2),
        "duration_sensitivity_pct": round(dur_se, 2),
        "duration_positive_predictivity_pct": round(dur_pp, 2),
        "jaccard_overlap_pct": round(jaccard, 2),
    }


def run_synthetic_self_certification(
    fs: float = 500.0,
    duration_sec: float = 25.0,
    heart_rate_bpm: float = 72.0,
) -> dict[str, Any]:
    """Executes an automated self-certification benchmark against a synthetic annotated reference ECG."""
    n_samples = int(round(duration_sec * fs))
    t = np.arange(n_samples, dtype=np.float64) / fs
    sig = np.zeros(n_samples, dtype=np.float64)

    rr_sec = 60.0 / heart_rate_bpm
    ref_r: list[int] = []
    ref_q: list[int] = []
    ref_j: list[int] = []
    ref_tpeak: list[int] = []
    ref_tend: list[int] = []

    curr_t = 0.80
    while curr_t + 0.45 < duration_sec:
        r_idx = int(round(curr_t * fs))
        q_idx = r_idx - int(round(0.036 * fs))
        j_idx = r_idx + int(round(0.038 * fs))
        tp_idx = r_idx + int(round(0.210 * fs))
        te_idx = r_idx + int(round(0.305 * fs))

        # Synthesize physiological P-QRS-T complex
        sig += 0.12 * np.exp(-0.5 * ((t - (curr_t - 0.150)) / 0.016) ** 2)
        sig -= 0.14 * np.exp(-0.5 * ((t - (curr_t - 0.020)) / 0.006) ** 2)
        sig += 1.25 * np.exp(-0.5 * ((t - curr_t) / 0.008) ** 2)
        sig -= 0.24 * np.exp(-0.5 * ((t - (curr_t + 0.022)) / 0.007) ** 2)
        sig += 0.34 * np.exp(-0.5 * ((t - (curr_t + 0.210)) / 0.040) ** 2)

        ref_r.append(r_idx)
        ref_q.append(q_idx)
        ref_j.append(j_idx)
        ref_tpeak.append(tp_idx)
        ref_tend.append(te_idx)
        curr_t += rr_sec

    det_r = detect_r_peaks(sig, fs)
    ec57_qrs = evaluate_qrs_and_classification_ec57(ref_r, det_r, fs=fs)

    det_q: list[int] = []
    det_j: list[int] = []
    det_tp: list[int] = []
    det_te: list[int] = []

    for _, t_idx in ec57_qrs["matched_pairs"]:
        r_samp = int(det_r[t_idx])
        det_q.append(detect_q_onset(sig, r_samp, fs))
        det_j.append(detect_j_point(sig, r_samp, fs))
        tp_s, te_s = detect_t_end(sig, r_samp, fs)
        det_tp.append(int(tp_s))
        det_te.append(int(te_s))

    matched_ref_indices = [r_i for r_i, _ in ec57_qrs["matched_pairs"]]
    cse_report = evaluate_fiducial_delineation_cse(
        ref_fiducials={
            "q_onset": [ref_q[i] for i in matched_ref_indices],
            "r_peak": [ref_r[i] for i in matched_ref_indices],
            "j_point": [ref_j[i] for i in matched_ref_indices],
            "t_peak": [ref_tpeak[i] for i in matched_ref_indices],
            "t_end": [ref_tend[i] for i in matched_ref_indices],
        },
        test_fiducials={
            "q_onset": det_q,
            "r_peak": [int(det_r[t_i]) for _, t_i in ec57_qrs["matched_pairs"]],
            "j_point": det_j,
            "t_peak": det_tp,
            "t_end": det_te,
        },
        fs=fs,
    )

    qt_list = [(te - q) / fs * 1000.0 for q, te in zip(det_q, det_te, strict=False)]
    stv_info = compute_stv_qt(qt_list)

    return {
        "status": "CERTIFIED" if (ec57_qrs["f1_score_pct"] >= 99.0 and cse_report["all_within_cse_limits"]) else "REVIEW_REQUIRED",
        "ec57_qrs": ec57_qrs,
        "cse_fiducials": cse_report,
        "synthetic_stv_qt_ms": stv_info["stv_qt_ms"],
    }
