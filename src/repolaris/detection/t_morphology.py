"""T-Wave Morphology, 3D SVD/PCA Loop Descriptors & Superimposed Butterfly Median Beat module.

Implements:
1. Single-lead FDA CiPA T-wave morphology biomarkers (Vicente et al., JAHA 2015):
   - T-wave limb area asymmetry/symmetry ratio (ascending vs. descending area).
   - T-wave flatness score (area-to-bounding-box fullness & plateau width).
   - Notched and biphasic T-wave detection with secondary lobe depth scoring.
2. Multi-lead 3D Singular Value Decomposition (SVD/PCA) repolarization loop descriptors
   (Acar et al., 1999; Zabel et al., Circulation 2000; BRAVEHEART VCG/ECG, 2023):
   - T2/T1 dipolarity / loop roundness complexity ratio (sigma_2 / sigma_1).
   - T3/T1 3D planarity departure ratio (sigma_3 / sigma_1).
   - Non-Dipolar Residue percentage (T_NDR %, energy outside 3D principal subspace).
   - Total Cosine R-to-T (TCRT in [-1.0, +1.0], 3D spatial angle cosine between QRS and T loops).
3. Superimposed Multi-Lead "Butterfly" Median Beat synthesis (Pilia et al., ECGdeli 2021):
   - R-peak synchronized ensemble median waveforms across all leads, local PR isoelectric
     zeroing, spatial Root-Mean-Square (RMS) magnitude curve, and synchronized global
     earliest-Q-onset, global J-point, global T-peak, and global latest-T-end calipers.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from repolaris.config import DetectionConfig
from repolaris.detection.q_onset import detect_j_point, detect_q_onset
from repolaris.detection.qrs import detect_r_peaks
from repolaris.detection.t_end import detect_t_end
from repolaris.preprocessing.baseline import remove_baseline_wander
from repolaris.preprocessing.filter import bandpass_filter

_trapz_fn = getattr(np, "trapezoid", None) or getattr(np, "trapz", None)


def evaluate_beat_t_morphology(
    signal: np.ndarray,
    j_point_sample: int,
    t_peak_sample: int,
    t_end_sample: int,
    fs: float,
) -> dict[str, Any]:
    """Quantifies T-wave symmetry/asymmetry, flatness, notching, and biphasic morphology for one beat.

    Args:
        signal: 1D conditioned ECG signal array (mV).
        j_point_sample: Sample index of QRS offset (J-point).
        t_peak_sample: Sample index of dominant T-wave apex.
        t_end_sample: Sample index of T-wave offset.
        fs: Sampling frequency in Hz.

    Returns:
        Dictionary with `asymmetry_ratio`, `asymmetry_index`, `symmetry_score`,
        `flatness_score`, `is_notched`, `is_biphasic`, `notch_score`, and `t_amplitude_mv`.
    """
    n_sig = len(signal)
    j_idx = int(np.clip(j_point_sample, 0, max(0, n_sig - 1)))
    te_idx = int(np.clip(t_end_sample, j_idx + 1, max(1, n_sig - 1)))
    tp_idx = int(np.clip(t_peak_sample, j_idx + 1, max(j_idx + 1, te_idx - 1)))

    if n_sig < 6 or (te_idx - j_idx) < 4 or fs <= 0:
        return {
            "asymmetry_ratio": 1.0,
            "asymmetry_index": 0.0,
            "symmetry_score": 1.0,
            "flatness_score": 0.0,
            "is_notched": False,
            "is_biphasic": False,
            "notch_score": 0.0,
            "t_amplitude_mv": 0.0,
        }

    # Reference baseline from post-T segment (or terminal T-end samples)
    post_end = min(n_sig, te_idx + max(3, int(round(0.040 * fs))))
    iso_level = float(np.median(signal[te_idx:post_end])) if post_end > te_idx else float(signal[te_idx])

    t_seg = np.asarray(signal[j_idx : te_idx + 1], dtype=np.float64) - iso_level
    tp_rel = int(np.clip(tp_idx - j_idx, 1, max(1, len(t_seg) - 2)))

    asc_seg = np.abs(t_seg[: tp_rel + 1])
    desc_seg = np.abs(t_seg[tp_rel:])

    dt = 1.0 / fs
    area_asc = float(_trapz_fn(asc_seg, dx=dt)) if len(asc_seg) >= 2 else 0.0
    area_desc = float(_trapz_fn(desc_seg, dx=dt)) if len(desc_seg) >= 2 else 0.0
    total_area = area_asc + area_desc

    asymmetry_ratio = area_asc / area_desc if area_desc > 1e-7 else 1.0
    asymmetry_index = abs(area_asc - area_desc) / total_area if total_area > 1e-7 else 0.0
    symmetry_score = max(0.0, min(1.0, 1.0 - asymmetry_index))

    # Isolate T-wave body excluding immediate post-J QRS/S-wave recovery tail (first 35 ms post-J)
    t_body_start = min(max(0, tp_rel - max(3, int(round(0.095 * fs)))), max(0, int(round(0.035 * fs))))
    t_body = t_seg[t_body_start:] if len(t_seg) - t_body_start >= 5 else t_seg

    max_pos = float(np.max(t_body))
    min_neg = float(np.min(t_body))
    dom_amp = max(max_pos, abs(min_neg))
    polarity = 1.0 if max_pos >= abs(min_neg) else -1.0
    oriented = polarity * t_body

    # Calibrated FDA CiPA Flatness score: combines 80%-peak plateau width and low-amplitude damping
    if dom_amp > 1e-5 and len(oriented) >= 5:
        norm_wave = np.clip(oriented / dom_amp, 0.0, 1.0)
        plateau_frac = float(np.mean(norm_wave >= 0.80))
        amp_damping = max(0.0, min(1.0, (0.15 - min(dom_amp, 0.15)) / 0.15))
        flatness_score = float(np.clip(0.75 * plateau_frac + 0.25 * amp_damping, 0.0, 1.0))
    else:
        flatness_score = 1.0

    # Smooth T-wave body with a 20 ms zero-phase moving average to reject high-frequency EMG/thermal ripple
    kernel_w = max(3, int(round(0.020 * fs)) | 1)
    if kernel_w > 1 and len(t_body) > kernel_w:
        kernel = np.ones(kernel_w, dtype=np.float64) / float(kernel_w)
        smooth_body = np.convolve(t_body, kernel, mode="same")
    else:
        smooth_body = t_body

    # Biphasic check: opposite-polarity interior local extremum >= 25% of dominant amplitude and >= 0.04 mV
    is_biphasic = False
    if len(smooth_body) >= 7 and dom_amp >= 0.05:
        opp_oriented = -polarity * smooth_body
        for idx in range(2, len(opp_oriented) - 2):
            if (
                opp_oriented[idx] > opp_oriented[idx - 1]
                and opp_oriented[idx] >= opp_oriented[idx + 1]
                and opp_oriented[idx] >= max(0.040, 0.25 * dom_amp)
            ):
                is_biphasic = True
                break

    # Notched check: detect two distinct local peaks separated by >= 22 ms with intervening valley >= 20 uV & 8% amp
    is_notched = False
    notch_score = 0.0
    smooth_oriented = polarity * smooth_body
    if len(smooth_oriented) >= 7 and dom_amp >= 0.04:
        local_max_indices: list[int] = []
        for idx in range(1, len(smooth_oriented) - 1):
            if smooth_oriented[idx] > smooth_oriented[idx - 1] and smooth_oriented[idx] >= smooth_oriented[idx + 1]:
                if smooth_oriented[idx] >= 0.35 * dom_amp:
                    local_max_indices.append(idx)

        min_sep_samples = max(3, int(round(0.022 * fs)))
        for p_idx in range(len(local_max_indices) - 1):
            p1 = local_max_indices[p_idx]
            for p2 in local_max_indices[p_idx + 1 :]:
                if (p2 - p1) >= min_sep_samples:
                    valley = float(np.min(smooth_oriented[p1 : p2 + 1]))
                    lower_peak = min(float(smooth_oriented[p1]), float(smooth_oriented[p2]))
                    depth = lower_peak - valley
                    if depth >= max(0.020, 0.08 * dom_amp):
                        is_notched = True
                        notch_score = max(notch_score, min(1.0, depth / (dom_amp + 1e-9)))

    return {
        "asymmetry_ratio": round(float(asymmetry_ratio), 4),
        "asymmetry_index": round(float(asymmetry_index), 4),
        "symmetry_score": round(float(symmetry_score), 4),
        "flatness_score": round(float(flatness_score), 4),
        "is_notched": bool(is_notched),
        "is_biphasic": bool(is_biphasic),
        "notch_score": round(float(notch_score), 4),
        "t_amplitude_mv": round(float(dom_amp), 4),
    }


def compute_superimposed_median_beat(
    lead_signals: np.ndarray | dict[str, np.ndarray],
    fs: float = 500.0,
    r_peaks: np.ndarray | None = None,
    lead_names: list[str] | None = None,
    pre_r_ms: float = 200.0,
    post_r_ms: float = 550.0,
    config: DetectionConfig | None = None,
    preprocess: bool = True,
) -> dict[str, Any]:
    """Constructs an R-peak aligned multi-lead Superimposed "Butterfly" Median Beat & global calipers.

    Aligns cardiac cycles across all available leads onto a shared relative time axis
    [-pre_r_ms, +post_r_ms] centered on the R-peak (0.0 ms), zeroes each lead's local PR
    isoelectric baseline, computes the spatial Root-Mean-Square (RMS) vector magnitude trace,
    and identifies the synchronized global earliest Q-onset, global J-point, global T-peak,
    and global latest T-end calipers.
    """
    if config is None:
        config = DetectionConfig()

    if isinstance(lead_signals, dict):
        names = list(lead_signals.keys())
        matrix = np.asarray([np.asarray(lead_signals[k], dtype=np.float64) for k in names], dtype=np.float64)
    else:
        arr = np.asarray(lead_signals, dtype=np.float64)
        if arr.ndim == 1:
            matrix = arr[np.newaxis, :]
            names = lead_names if (lead_names and len(lead_names) == 1) else ["Lead I"]
        else:
            matrix = arr
            names = (
                list(lead_names)
                if (lead_names and len(lead_names) == matrix.shape[0])
                else [f"Lead {i + 1}" for i in range(matrix.shape[0])]
            )

    n_leads, n_samples = matrix.shape
    pre_samples = max(10, int(round((pre_r_ms / 1000.0) * fs)))
    post_samples = max(25, int(round((post_r_ms / 1000.0) * fs)))
    win_len = pre_samples + post_samples

    time_rel_sec = (np.arange(win_len, dtype=np.float64) - pre_samples) / fs
    time_rel_ms = time_rel_sec * 1000.0

    if n_leads == 0 or n_samples < win_len:
        zero_trace = np.zeros(win_len, dtype=np.float64)
        return {
            "fs": float(fs),
            "r_anchor_sample": pre_samples,
            "time_rel_sec": time_rel_sec,
            "time_rel_ms": time_rel_ms,
            "lead_names": names,
            "lead_medians": {name: zero_trace.copy() for name in names},
            "rms_signal": zero_trace,
            "beats_averaged": 0,
            "global_q_onset_sample": max(0, pre_samples - int(round(0.040 * fs))),
            "global_j_point_sample": min(win_len - 1, pre_samples + int(round(0.040 * fs))),
            "global_t_peak_sample": min(win_len - 1, pre_samples + int(round(0.240 * fs))),
            "global_t_end_sample": min(win_len - 1, pre_samples + int(round(0.360 * fs))),
            "global_q_onset_sec": -0.040,
            "global_j_point_sec": 0.040,
            "global_t_peak_sec": 0.240,
            "global_t_end_sec": 0.360,
            "global_q_onset_ms": -40.0,
            "global_j_point_ms": 40.0,
            "global_t_peak_ms": 240.0,
            "global_t_end_ms": 360.0,
            "global_qt_ms": 400.0,
            "global_jt_peak_ms": 200.0,
            "global_tpe_ms": 120.0,
            "global_tpe_qt_ratio": 0.30,
        }

    conditioned_matrix = np.zeros_like(matrix, dtype=np.float64)
    for idx in range(n_leads):
        trace = matrix[idx]
        if preprocess and np.std(trace) > 1e-6:
            conditioned_matrix[idx] = remove_baseline_wander(bandpass_filter(trace, fs), fs)
        else:
            conditioned_matrix[idx] = trace

    if r_peaks is None or len(r_peaks) == 0:
        stds = [float(np.std(conditioned_matrix[i])) for i in range(n_leads)]
        ref_lead_idx = int(np.argmax(stds))
        r_peaks = detect_r_peaks(conditioned_matrix[ref_lead_idx], fs, config.refractory_period_ms)

    valid_r = [int(r) for r in r_peaks if pre_samples <= int(r) < (n_samples - post_samples)]
    if not valid_r and len(r_peaks) > 0:
        r0 = int(r_peaks[len(r_peaks) // 2])
        pad_left = max(0, pre_samples - r0)
        pad_right = max(0, (r0 + post_samples) - n_samples)
        padded = np.pad(conditioned_matrix, ((0, 0), (pad_left, pad_right)), mode="edge")
        r_shifted = r0 + pad_left
        median_matrix = padded[:, r_shifted - pre_samples : r_shifted + post_samples]
        beats_averaged = 1
    elif valid_r:
        stack = np.stack(
            [conditioned_matrix[:, r - pre_samples : r + post_samples] for r in valid_r],
            axis=0,
        )
        median_matrix = np.median(stack, axis=0)
        beats_averaged = len(valid_r)
    else:
        median_matrix = np.zeros((n_leads, win_len), dtype=np.float64)
        beats_averaged = 0

    iso_start = max(0, pre_samples - int(round(0.110 * fs)))
    iso_end = max(iso_start + 2, pre_samples - int(round(0.050 * fs)))

    lead_medians: dict[str, np.ndarray] = {}
    q_candidates: list[int] = []
    j_candidates: list[int] = []
    tp_candidates: list[int] = []
    te_candidates: list[int] = []

    for idx, lname in enumerate(names):
        m_trace = median_matrix[idx].copy()
        if iso_end <= len(m_trace):
            m_trace -= float(np.median(m_trace[iso_start:iso_end]))
        lead_medians[lname] = m_trace

        if float(np.std(m_trace)) > 1e-5:
            q_i = detect_q_onset(m_trace, pre_samples, fs, config.q_search_window_ms)
            j_i = detect_j_point(m_trace, pre_samples, fs, config.q_search_window_ms)
            tp_i, te_i = detect_t_end(
                m_trace,
                pre_samples,
                fs,
                config.t_search_window_ms,
                config.t_end_threshold_ratio,
                method=getattr(config, "t_end_method", "hybrid"),
            )
            q_candidates.append(int(q_i))
            j_candidates.append(int(j_i))
            tp_candidates.append(int(tp_i))
            te_candidates.append(int(te_i))

    aligned_stack = np.asarray([lead_medians[k] for k in names], dtype=np.float64)
    rms_signal = np.sqrt(np.mean(aligned_stack**2, axis=0))

    if q_candidates:
        global_q_samp = int(np.percentile(q_candidates, 15)) if len(q_candidates) >= 4 else int(min(q_candidates))
    else:
        global_q_samp = max(0, pre_samples - int(round(0.040 * fs)))

    if j_candidates:
        global_j_samp = int(round(float(np.median(j_candidates))))
    else:
        global_j_samp = min(win_len - 1, pre_samples + int(round(0.040 * fs)))

    if te_candidates:
        global_te_samp = int(np.percentile(te_candidates, 85)) if len(te_candidates) >= 4 else int(max(te_candidates))
    else:
        global_te_samp = min(win_len - 1, pre_samples + int(round(0.360 * fs)))

    tp_search_start = min(win_len - 2, max(global_j_samp + int(round(0.030 * fs)), pre_samples + int(round(0.090 * fs))))
    tp_search_end = max(tp_search_start + 1, min(win_len, global_te_samp))
    if tp_search_end > tp_search_start and float(np.max(rms_signal[tp_search_start:tp_search_end])) > 1e-6:
        global_tp_samp = tp_search_start + int(np.argmax(rms_signal[tp_search_start:tp_search_end]))
    elif tp_candidates:
        global_tp_samp = int(round(float(np.median(tp_candidates))))
    else:
        global_tp_samp = min(win_len - 2, pre_samples + int(round(0.240 * fs)))

    global_te_samp = max(global_tp_samp + 1, global_te_samp)

    q_rel_sec = float((global_q_samp - pre_samples) / fs)
    j_rel_sec = float((global_j_samp - pre_samples) / fs)
    tp_rel_sec = float((global_tp_samp - pre_samples) / fs)
    te_rel_sec = float((global_te_samp - pre_samples) / fs)

    global_qt_ms = max(0.0, (te_rel_sec - q_rel_sec) * 1000.0)
    global_jtp_ms = max(0.0, (tp_rel_sec - j_rel_sec) * 1000.0)
    global_tpe_ms = max(0.0, (te_rel_sec - tp_rel_sec) * 1000.0)
    global_tpe_qt = global_tpe_ms / global_qt_ms if global_qt_ms > 1e-6 else 0.0

    return {
        "fs": float(fs),
        "r_anchor_sample": int(pre_samples),
        "time_rel_sec": time_rel_sec,
        "time_rel_ms": time_rel_ms,
        "lead_names": names,
        "lead_medians": lead_medians,
        "rms_signal": rms_signal,
        "beats_averaged": int(beats_averaged),
        "global_q_onset_sample": int(global_q_samp),
        "global_j_point_sample": int(global_j_samp),
        "global_t_peak_sample": int(global_tp_samp),
        "global_t_end_sample": int(global_te_samp),
        "global_q_onset_sec": round(q_rel_sec, 4),
        "global_j_point_sec": round(j_rel_sec, 4),
        "global_t_peak_sec": round(tp_rel_sec, 4),
        "global_t_end_sec": round(te_rel_sec, 4),
        "global_q_onset_ms": round(q_rel_sec * 1000.0, 2),
        "global_j_point_ms": round(j_rel_sec * 1000.0, 2),
        "global_t_peak_ms": round(tp_rel_sec * 1000.0, 2),
        "global_t_end_ms": round(te_rel_sec * 1000.0, 2),
        "global_qt_ms": round(global_qt_ms, 2),
        "global_jt_peak_ms": round(global_jtp_ms, 2),
        "global_tpe_ms": round(global_tpe_ms, 2),
        "global_tpe_qt_ratio": round(global_tpe_qt, 4),
    }


def compute_twave_svd_descriptors(
    butterfly_data: dict[str, Any],
) -> dict[str, Any]:
    """Computes 3D SVD/PCA T-wave loop complexity (T2/T1), non-dipolar residue, and Total Cosine R-to-T (TCRT)."""
    lead_medians: dict[str, np.ndarray] = butterfly_data.get("lead_medians", {})
    _non_ecg_tokens = ("RESP", "SPO2", "PLETH", "ABP", "ACC", "TEMP", "EEG", "EOG", "EMG", "AIRFLOW")
    names = [
        k for k in lead_medians
        if not any(tok in str(k).upper() for tok in _non_ecg_tokens)
    ]
    n_leads = len(names)
    if n_leads < 2:
        return {
            "available": False,
            "lead_count": n_leads,
            "t2_t1_ratio": None,
            "t3_t1_ratio": None,
            "non_dipolar_residue_pct": None,
            "tcrt": None,
            "singular_values": [],
        }

    matrix = np.asarray([lead_medians[k] for k in names], dtype=np.float64)
    n_samples = matrix.shape[1]

    q_samp = int(np.clip(butterfly_data.get("global_q_onset_sample", 0), 0, n_samples - 2))
    j_samp = int(np.clip(butterfly_data.get("global_j_point_sample", q_samp + 4), q_samp + 2, n_samples - 2))
    te_samp = int(np.clip(butterfly_data.get("global_t_end_sample", j_samp + 10), j_samp + 3, n_samples))

    qrs_mat = matrix[:, q_samp:j_samp]
    t_mat = matrix[:, j_samp:te_samp]

    def _unavailable() -> dict[str, Any]:
        return {
            "available": False,
            "lead_count": n_leads,
            "t2_t1_ratio": None,
            "t3_t1_ratio": None,
            "non_dipolar_residue_pct": None,
            "tcrt": None,
            "singular_values": [],
        }

    def _safe_svd(mat: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
        if not np.all(np.isfinite(mat)):
            return None
        try:
            u_m, s_m, _ = np.linalg.svd(mat, full_matrices=False)
            return u_m, s_m
        except np.linalg.LinAlgError:
            scale = float(np.max(np.abs(mat)))
            if scale <= 1e-12 or not np.isfinite(scale):
                return None
            try:
                u_m, s_m, _ = np.linalg.svd(mat / scale, full_matrices=False)
                return u_m, s_m * scale
            except np.linalg.LinAlgError:
                return None

    if t_mat.shape[1] < 3 or not np.all(np.isfinite(t_mat)) or float(np.std(t_mat)) < 1e-7:
        return _unavailable()

    t_svd = _safe_svd(t_mat)
    if t_svd is None:
        return _unavailable()
    _, s_vals = t_svd
    s1 = float(s_vals[0]) if len(s_vals) >= 1 else 0.0
    s2 = float(s_vals[1]) if len(s_vals) >= 2 else 0.0
    s3 = float(s_vals[2]) if len(s_vals) >= 3 else 0.0

    if s1 <= 1e-9:
        return _unavailable()

    t2_t1 = s2 / s1
    t3_t1 = s3 / s1 if len(s_vals) >= 3 else 0.0

    total_energy = float(np.sum(s_vals**2))
    non_dipolar_energy = float(np.sum(s_vals[3:] ** 2)) if len(s_vals) > 3 else 0.0
    ndr_pct = (non_dipolar_energy / total_energy * 100.0) if total_energy > 1e-12 else 0.0

    qrst_mat = matrix[:, q_samp:te_samp]
    qrst_svd = _safe_svd(qrst_mat)
    if qrst_svd is None:
        return _unavailable()
    u_full, _ = qrst_svd
    n_dim = min(3, u_full.shape[1])
    u_3d = u_full[:, :n_dim]

    qrs_3d = u_3d.T @ qrs_mat
    t_3d = u_3d.T @ t_mat

    t_norms = np.linalg.norm(t_3d, axis=0)
    qrs_norms = np.linalg.norm(qrs_3d, axis=0)
    max_t_idx = int(np.argmax(t_norms))
    max_t_norm = float(t_norms[max_t_idx])
    max_qrs_norm = float(np.max(qrs_norms)) if len(qrs_norms) > 0 else 0.0

    if max_t_norm > 1e-7 and max_qrs_norm > 1e-7:
        e_t_max = t_3d[:, max_t_idx] / max_t_norm
        active_qrs_mask = qrs_norms >= (0.50 * max_qrs_norm)
        if not np.any(active_qrs_mask):
            active_qrs_mask = qrs_norms > 1e-7
        qrs_active = qrs_3d[:, active_qrs_mask]
        qrs_active_norms = qrs_norms[active_qrs_mask]
        cosines = (e_t_max @ qrs_active) / qrs_active_norms
        tcrt_val: float | None = round(float(np.clip(np.mean(cosines), -1.0, 1.0)), 4)
    else:
        tcrt_val = None

    return {
        "available": True,
        "lead_count": int(n_leads),
        "t2_t1_ratio": round(float(t2_t1), 4),
        "t3_t1_ratio": round(float(t3_t1), 4),
        "non_dipolar_residue_pct": round(float(ndr_pct), 3),
        "tcrt": tcrt_val,
        "singular_values": [round(float(v), 4) for v in s_vals],
    }


def compute_t_wave_morphology(
    signal: np.ndarray,
    fs: float = 500.0,
    r_peaks: np.ndarray | None = None,
    beats: list[dict[str, Any]] | None = None,
    multi_lead_signals: np.ndarray | dict[str, np.ndarray] | None = None,
    lead_names: list[str] | None = None,
    config: DetectionConfig | None = None,
) -> dict[str, Any]:
    """Master T-Wave Morphology, 3D SVD Loop Complexity & Butterfly Median Beat analyzer."""
    if config is None:
        config = DetectionConfig()

    if r_peaks is None:
        r_peaks = detect_r_peaks(signal, fs, config.refractory_period_ms)

    n_sig = len(signal)
    edge_guard = max(4, int(round(0.050 * fs)))
    beat_morphs: list[dict[str, Any]] = []
    if beats:
        for b in beats:
            j_idx = int(b.get("j_point_sample") or detect_j_point(signal, int(b["r_peak_sample"]), fs))
            tp_idx = int(b["t_peak_sample"])
            te_idx = int(b["t_end_sample"])
            if te_idx < (n_sig - edge_guard):
                beat_morphs.append(evaluate_beat_t_morphology(signal, j_idx, tp_idx, te_idx, fs))
    else:
        for r_idx in r_peaks:
            j_idx = detect_j_point(signal, int(r_idx), fs, config.q_search_window_ms)
            tp_idx, te_idx = detect_t_end(
                signal,
                int(r_idx),
                fs,
                config.t_search_window_ms,
                config.t_end_threshold_ratio,
                method=getattr(config, "t_end_method", "hybrid"),
            )
            if te_idx < (n_sig - edge_guard):
                beat_morphs.append(evaluate_beat_t_morphology(signal, j_idx, tp_idx, te_idx, fs))

    leads_input: np.ndarray | dict[str, np.ndarray]
    is_multi = multi_lead_signals is not None
    if multi_lead_signals is not None:
        leads_input = multi_lead_signals
    else:
        leads_input = {"Active Lead": np.asarray(signal, dtype=np.float64)}

    butterfly = compute_superimposed_median_beat(
        leads_input,
        fs=fs,
        r_peaks=r_peaks,
        lead_names=lead_names,
        config=config,
        preprocess=is_multi,
    )
    svd_metrics = compute_twave_svd_descriptors(butterfly)

    if beat_morphs:
        asym_ratios = [m["asymmetry_ratio"] for m in beat_morphs]
        asym_indices = [m["asymmetry_index"] for m in beat_morphs]
        sym_scores = [m["symmetry_score"] for m in beat_morphs]
        flat_scores = [m["flatness_score"] for m in beat_morphs]
        notch_scores = [m["notch_score"] for m in beat_morphs]
        notched_cnt = sum(1 for m in beat_morphs if m["is_notched"])
        biphasic_cnt = sum(1 for m in beat_morphs if m["is_biphasic"])
        n_m = len(beat_morphs)

        mean_asym_ratio = round(float(np.mean(asym_ratios)), 4)
        mean_asym_idx = round(float(np.mean(asym_indices)), 4)
        mean_sym_score = round(float(np.mean(sym_scores)), 4)
        mean_flatness = round(float(np.mean(flat_scores)), 4)
        mean_notch = round(float(np.mean(notch_scores)), 4)
        notched_pct = round(notched_cnt / n_m * 100.0, 2)
    else:
        mean_asym_ratio = 1.0
        mean_asym_idx = 0.0
        mean_sym_score = 1.0
        mean_flatness = 0.0
        mean_notch = 0.0
        notched_cnt = 0
        biphasic_cnt = 0
        notched_pct = 0.0

    t2_t1 = svd_metrics.get("t2_t1_ratio")
    tcrt = svd_metrics.get("tcrt")
    if notched_pct >= 25.0 or (t2_t1 is not None and t2_t1 >= 0.35) or (tcrt is not None and tcrt < -0.25):
        verdict = "HIGH_HETEROGENEITY"
    elif notched_cnt > 0 or biphasic_cnt > 0 or mean_flatness >= 0.65:
        verdict = "ABNORMAL_MORPHOLOGY"
    else:
        verdict = "NORMAL"

    return {
        "mean_asymmetry_ratio": mean_asym_ratio,
        "mean_asymmetry_index": mean_asym_idx,
        "mean_symmetry_score": mean_sym_score,
        "mean_flatness_score": mean_flatness,
        "mean_notch_score": mean_notch,
        "notched_beat_count": int(notched_cnt),
        "notched_beat_pct": float(notched_pct),
        "biphasic_beat_count": int(biphasic_cnt),
        "beats_evaluated": len(beat_morphs),
        "svd_3d": svd_metrics,
        "butterfly": butterfly,
        "verdict": verdict,
    }
