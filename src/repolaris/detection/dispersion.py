"""Multi-Lead Spatial QT Dispersion (QTd) and Transmural Dispersion (Tpe,d) module.

Quantifies inter-lead spatial heterogeneity in ventricular recovery time and
transmural dispersion of repolarization across synchronous multi-lead ECG recordings,
enforcing clinical signal quality screening and dynamic channel quorum gating.

References:
    - Day, C. P., McComb, J. M., & Campbell, R. W. (1990). QT dispersion: an indication
      of arrhythmia risk in patients with long QT intervals. British Heart Journal, 63(6), 342-344.
    - Antzelevitch, C., et al. (2001). Transmural dispersion of repolarization and Torsade
      de Pointes. Circulation, 103(22), 2722-2728.
"""

from __future__ import annotations

from typing import Any
import numpy as np

from repolaris.config import DetectionConfig
from repolaris.detection.q_onset import detect_q_onset
from repolaris.detection.qrs import detect_r_peaks
from repolaris.detection.sqi import evaluate_lead_quality
from repolaris.detection.t_end import detect_t_end
from repolaris.preprocessing.baseline import remove_baseline_wander
from repolaris.preprocessing.filter import bandpass_filter

PRECORDIAL_LEADS: frozenset[str] = frozenset(
    {"V1", "V2", "V3", "V4", "V5", "V6", "LEAD V1", "LEAD V2", "LEAD V3", "LEAD V4", "LEAD V5", "LEAD V6"}
)


def resolve_lead_quorum(total_leads: int, min_quorum: int | None = None) -> int:
    """Determines the minimum required valid lead quorum based on recording configuration.

    Standard 12-lead diagnostic recordings (>= 8 channels) require at least 8 valid leads
    (or user-specified quorum), while ambulatory Holter configurations (3 to 7 channels)
    require at least 3 valid diagnostic leads. Single/dual-lead patches (< 3 channels)
    cannot satisfy spatial dispersion quorum.
    """
    if min_quorum is not None:
        return max(2, int(min_quorum))
    if total_leads >= 8:
        return 8
    return 3


def calculate_qt_dispersion(
    lead_signals: np.ndarray | dict[str, np.ndarray],
    fs: float = 500.0,
    lead_names: list[str] | None = None,
    config: DetectionConfig | None = None,
    min_quorum: int | None = None,
    min_psqi: float = 0.50,
    min_bassqi: float = 0.70,
    min_snr_db: float = 8.0,
    min_t_amp_mv: float = 0.05,
    preprocess: bool = True,
) -> dict[str, Any] | None:
    """Quantifies spatial repolarization heterogeneity across synchronous multi-lead recordings.

    Args:
        lead_signals: 2D array of shape (n_leads, n_samples) or Dict[lead_name, 1D_array].
        fs: Sampling frequency in Hz (default: 500.0).
        lead_names: Optional list of clinical lead identifiers.
        config: Optional DetectionConfig thresholds.
        min_quorum: Minimum valid leads required (defaults to 8 for >=8-lead, 3 for Holter).
        min_psqi: Minimum QRS relative power SQI threshold (default: 0.50).
        min_bassqi: Minimum baseline stability SQI threshold (default: 0.70).
        min_snr_db: Minimum Signal-to-Noise Ratio in dB (default: 8.0).
        min_t_amp_mv: Minimum peak-to-peak T-wave amplitude in mV (50 uV = 0.05 mV).
        preprocess: Whether to apply bandpass + baseline wander removal per lead.

    Returns:
        Dictionary containing beat-by-beat arrays and aggregate summary metrics:
            - 'qt_dispersion_ms': 1D array of beat-by-beat QTd = QT_max - QT_min (ms).
            - 'qtc_dispersion_ms': 1D array of Fridericia rate-corrected QTc_d (ms).
            - 'tpe_dispersion_ms': 1D array of transmural Tpeak-Tend dispersion Tpe,d (ms).
            - 'precordial_tpe_dispersion_ms': 1D array of precordial (V1-V6) Tpe,d (ms).
            - 'global_q_onsets': 1D array of earliest Q-onset sample indices across valid leads.
            - 'valid_leads': List of lead names that passed SQI and amplitude screening.
            - 'rejected_leads': List of lead names masked due to low SQI or flat T-waves.
            - 'quorum_met': Boolean indicating whether channel quorum was satisfied.
            - 'summary': Aggregate statistics (mean/median/p95 QTd, QTc_d, Tpe,d, risk verdict).
        Returns None if total channels < 3 or valid leads < required quorum.
    """
    if config is None:
        config = DetectionConfig()

    if isinstance(lead_signals, dict):
        names = list(lead_signals.keys())
        matrix = np.asarray([np.asarray(lead_signals[k], dtype=np.float64) for k in names])
    else:
        matrix = np.asarray(lead_signals, dtype=np.float64)
        if matrix.ndim != 2:
            return None
        names = lead_names if lead_names and len(lead_names) == matrix.shape[0] else [
            f"Lead {i + 1}" for i in range(matrix.shape[0])
        ]

    n_leads, n_samples = matrix.shape
    if n_leads < 3 or n_samples < int(fs * 1.5):
        return None

    required_quorum = resolve_lead_quorum(n_leads, min_quorum=min_quorum)

    clean_leads: dict[str, np.ndarray] = {}
    valid_leads: list[str] = []
    rejected_leads: list[str] = []
    lead_sqi: dict[str, dict[str, Any]] = {}

    for idx, name in enumerate(names):
        raw_trace = matrix[idx]
        if np.std(raw_trace) < 1e-6:
            rejected_leads.append(name)
            continue

        trace = remove_baseline_wander(bandpass_filter(raw_trace, fs), fs) if preprocess else raw_trace
        sqi = evaluate_lead_quality(trace, fs)
        lead_sqi[name] = sqi

        if (
            float(sqi["psqi"]) >= min_psqi
            and float(sqi["bassqi"]) >= min_bassqi
            and float(sqi["snr_db"]) >= min_snr_db
        ):
            clean_leads[name] = trace
            valid_leads.append(name)
        else:
            rejected_leads.append(name)

    if len(valid_leads) < required_quorum:
        return None

    # Detect master R-peaks on the highest-SNR valid lead
    best_lead = max(valid_leads, key=lambda k: float(lead_sqi[k]["snr_db"]))
    r_peaks = detect_r_peaks(clean_leads[best_lead], fs, config.refractory_period_ms)
    n_beats = len(r_peaks)
    if n_beats == 0:
        return None

    qtd_list: list[float] = []
    qtcd_list: list[float] = []
    tped_list: list[float] = []
    precordial_tped_list: list[float] = []
    global_q_list: list[int] = []

    for b_idx, r_idx in enumerate(r_peaks):
        if b_idx < n_beats - 1:
            rr_sec = float((r_peaks[b_idx + 1] - r_idx) / fs)
        elif b_idx > 0:
            rr_sec = float((r_idx - r_peaks[b_idx - 1]) / fs)
        else:
            rr_sec = 1.0
        rr_cbrt = (rr_sec ** (1.0 / 3.0)) if rr_sec > 0 else 1.0

        beat_q_onsets: dict[str, int] = {}
        beat_t_peaks: dict[str, int] = {}
        beat_t_ends: dict[str, int] = {}

        for lname in valid_leads:
            sig = clean_leads[lname]
            # Local R-peak alignment within +/- 40 ms
            rad = max(1, int(0.040 * fs))
            s_start = max(0, int(r_idx) - rad)
            s_end = min(n_samples, int(r_idx) + rad + 1)
            local_r = s_start + int(np.argmax(np.abs(sig[s_start:s_end])))

            q_idx = detect_q_onset(sig, local_r, fs, config.q_search_window_ms)
            tp_idx, te_idx = detect_t_end(
                sig,
                local_r,
                fs,
                config.t_search_window_ms,
                config.t_end_threshold_ratio,
            )

            # Check T-wave peak-to-peak amplitude >= min_t_amp_mv (50 uV)
            t_win_start = min(n_samples - 1, local_r + int(0.080 * fs))
            t_win_end = min(n_samples, te_idx + int(0.040 * fs))
            if t_win_end > t_win_start:
                t_ptp = float(np.ptp(sig[t_win_start:t_win_end]))
            else:
                t_ptp = 0.0

            if t_ptp >= min_t_amp_mv and te_idx > q_idx and te_idx > tp_idx:
                beat_q_onsets[lname] = int(q_idx)
                beat_t_peaks[lname] = int(tp_idx)
                beat_t_ends[lname] = int(te_idx)

        if len(beat_t_ends) < min(3, required_quorum):
            continue

        global_q = min(beat_q_onsets.values())
        global_q_list.append(global_q)

        qt_ms_per_lead: list[float] = []
        qtc_ms_per_lead: list[float] = []
        tpe_ms_per_lead: list[float] = []
        prec_tpe_ms: list[float] = []

        for lname, te_idx in beat_t_ends.items():
            q_idx = beat_q_onsets[lname]
            tp_idx = beat_t_peaks[lname]

            qt_ms = float((te_idx - q_idx) / fs * 1000.0)
            qtc_ms = qt_ms / rr_cbrt
            tpe_ms = float((te_idx - tp_idx) / fs * 1000.0)

            qt_ms_per_lead.append(qt_ms)
            qtc_ms_per_lead.append(qtc_ms)
            tpe_ms_per_lead.append(tpe_ms)

            if lname.strip().upper() in PRECORDIAL_LEADS:
                prec_tpe_ms.append(tpe_ms)

        qtd_list.append(float(np.max(qt_ms_per_lead) - np.min(qt_ms_per_lead)))
        qtcd_list.append(float(np.max(qtc_ms_per_lead) - np.min(qtc_ms_per_lead)))
        tped_list.append(float(np.max(tpe_ms_per_lead) - np.min(tpe_ms_per_lead)))
        if len(prec_tpe_ms) >= 2:
            precordial_tped_list.append(float(np.max(prec_tpe_ms) - np.min(prec_tpe_ms)))
        else:
            precordial_tped_list.append(float(np.max(tpe_ms_per_lead) - np.min(tpe_ms_per_lead)))

    if not qtd_list:
        return None

    qtd_arr = np.asarray(qtd_list, dtype=np.float64)
    qtcd_arr = np.asarray(qtcd_list, dtype=np.float64)
    tped_arr = np.asarray(tped_list, dtype=np.float64)
    prec_tped_arr = np.asarray(precordial_tped_list, dtype=np.float64)

    mean_qtd = float(np.mean(qtd_arr))
    if mean_qtd > 65.0:
        risk_category = "PATHOLOGICAL"
    elif mean_qtd >= 50.0:
        risk_category = "BORDERLINE"
    else:
        risk_category = "NORMAL"

    return {
        "qt_dispersion_ms": qtd_arr,
        "qtc_dispersion_ms": qtcd_arr,
        "tpe_dispersion_ms": tped_arr,
        "precordial_tpe_dispersion_ms": prec_tped_arr,
        "global_q_onsets": np.asarray(global_q_list, dtype=int),
        "valid_leads": valid_leads,
        "rejected_leads": rejected_leads,
        "quorum_met": True,
        "required_quorum": required_quorum,
        "summary": {
            "mean_qtd_ms": mean_qtd,
            "median_qtd_ms": float(np.median(qtd_arr)),
            "p95_qtd_ms": float(np.percentile(qtd_arr, 95)),
            "mean_qtcd_ms": float(np.mean(qtcd_arr)),
            "mean_tped_ms": float(np.mean(tped_arr)),
            "mean_precordial_tped_ms": float(np.mean(prec_tped_arr)),
            "valid_lead_count": len(valid_leads),
            "total_lead_count": n_leads,
            "beats_evaluated": len(qtd_arr),
            "risk_category": risk_category,
        },
    }
