"""ECG Pulse Metrics, FDA CiPA Sub-Intervals, and Short-Term QT Variability module.

Formulas:
- Bazett: QTc = QT / sqrt(RR)
- Fridericia: QTc = QT / cbrt(RR)
- Framingham: QTc = QT + 0.154 * (1 - RR)
- Hodges: QTc = QT + 1.75 * (HR - 60)
- FDA CiPA J-Tpeakc (Johannesen et al., 2014/2016): J-Tpeakc = J-Tpeak / (RR ** 0.58)
- Transmural Dispersion Tpe & Tpe/QT Ratio (Gupta et al., 2008): Tpe = T_end - T_peak
- Poincaré Short-Term & Long-Term QT Variability (Thomsen et al., Circulation 2004):
  STV_QT = sum(|QT_{n+1} - QT_n|) / (N * sqrt(2))
  LTV_QT = sum(|QT_{n+1} + QT_n - 2 * mean(QT)|) / (N * sqrt(2))
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def compute_qtc(qt_sec: float, rr_sec: float) -> dict[str, float]:
    """Computes rate-corrected QT intervals across all standard clinical formulas.

    Args:
        qt_sec: QT interval duration in seconds.
        rr_sec: RR interval duration in seconds.

    Returns:
        Dictionary mapping formula names to rate-corrected QTc in milliseconds (ms).
    """
    if rr_sec <= 0 or qt_sec <= 0:
        return {}

    qt_ms = qt_sec * 1000.0
    hr_bpm = 60.0 / rr_sec

    # 1. Bazett (1920): QTc = QT / sqrt(RR)
    qtc_bazett = qt_ms / math.sqrt(rr_sec)

    # 2. Fridericia (1920): QTc = QT / (RR^(1/3))
    qtc_fridericia = qt_ms / (rr_sec ** (1.0 / 3.0))

    # 3. Framingham (Sagie et al., 1992): QTc = QT + 154 * (1 - RR) [in ms]
    qtc_framingham = qt_ms + 154.0 * (1.0 - rr_sec)

    # 4. Hodges (1983): QTc = QT + 1.75 * (HR - 60) [in ms]
    qtc_hodges = qt_ms + 1.75 * (hr_bpm - 60.0)

    return {
        "bazett_ms": round(qtc_bazett, 2),
        "fridericia_ms": round(qtc_fridericia, 2),
        "framingham_ms": round(qtc_framingham, 2),
        "hodges_ms": round(qtc_hodges, 2),
    }


def compute_cipa_metrics(
    q_onset_sample: int,
    j_point_sample: int,
    t_peak_sample: int,
    t_end_sample: int,
    fs: float,
    rr_sec: float,
) -> dict[str, float]:
    """Computes FDA CiPA early and late repolarization sub-intervals for a cardiac cycle.

    References:
        - Johannesen L., Vicente J., Mason J.W., et al. (2014). "Differentiating Drug-Induced
          Multichannel Block on the Electrocardiogram: Randomized Study of Dofetilide,
          Quinidine, Ranolazine, and Verapamil." Clinical Pharmacology & Therapeutics, 96(5), 549-558.
        - Gupta P., Patel C., Patel H., et al. (2008). "Tp-e/QT ratio as an index of
          arrhythmogenesis." Journal of Electrocardiology, 41(6), 567-574.

    Args:
        q_onset_sample: Sample index of Q-wave onset.
        j_point_sample: Sample index of QRS offset (J-point).
        t_peak_sample: Sample index of T-wave apex.
        t_end_sample: Sample index of T-wave offset.
        fs: Sampling frequency in Hz.
        rr_sec: Instantaneous or preceding RR interval in seconds.

    Returns:
        Dictionary with `jt_peak_ms`, `jt_peak_c_ms`, `tpe_ms`, and `tpe_qt_ratio`.
    """
    if fs <= 0:
        return {
            "jt_peak_ms": 0.0,
            "jt_peak_c_ms": 0.0,
            "tpe_ms": 0.0,
            "tpe_qt_ratio": 0.0,
        }

    qt_ms = max(0.0, float(t_end_sample - q_onset_sample) / fs * 1000.0)
    eff_j = min(max(q_onset_sample, j_point_sample), t_peak_sample)
    jt_peak_ms = max(0.0, float(t_peak_sample - eff_j) / fs * 1000.0)
    tpe_ms = max(0.0, float(t_end_sample - t_peak_sample) / fs * 1000.0)

    # Johannesen et al. (2014) FDA CiPA rate-correction exponent 0.58
    jt_peak_c_ms = jt_peak_ms / (rr_sec ** 0.58) if rr_sec > 0.15 else jt_peak_ms
    tpe_qt_ratio = tpe_ms / qt_ms if qt_ms > 1e-6 else 0.0

    return {
        "jt_peak_ms": round(jt_peak_ms, 2),
        "jt_peak_c_ms": round(jt_peak_c_ms, 2),
        "tpe_ms": round(tpe_ms, 2),
        "tpe_qt_ratio": round(tpe_qt_ratio, 4),
    }


def compute_stv_qt(
    qt_intervals_ms: np.ndarray | list[float],
    beat_classes: list[str] | None = None,
) -> dict[str, Any]:
    """Computes Poincaré Short-Term (STV_QT) and Long-Term (LTV_QT) Variability of the QT interval.

    Reference:
        Thomsen M.B., Verduyn S.C., Stengl M., et al. (2004).
        "Increased short-term variability of repolarization predicts d-sotalol-induced
        torsades de pointes in dogs." Circulation, 110(16), 2453-2459.

    Formulas:
        STV_QT = sum(|QT_{n+1} - QT_n|) / (N * sqrt(2))
        LTV_QT = sum(|QT_{n+1} + QT_n - 2 * mean(QT)|) / (N * sqrt(2))

    Args:
        qt_intervals_ms: 1D sequence of QT intervals in milliseconds (if passed in seconds
            with values < 2.0, automatically scaled to milliseconds).
        beat_classes: Optional list of AAMI beat class codes ('N', 'V', 'S', 'F', 'Q') to
            filter for normal sinus beats before computing beat-to-beat repolarization stability.

    Returns:
        Dictionary containing `stv_qt_ms`, `ltv_qt_ms`, `sd1_qt_ms`, `sd2_qt_ms`,
        `instability_index`, `beats_used`, and `risk_category`.
    """
    raw_qt = np.asarray(qt_intervals_ms, dtype=np.float64)
    if len(raw_qt) == 0:
        return {
            "stv_qt_ms": 0.0,
            "ltv_qt_ms": 0.0,
            "sd1_qt_ms": 0.0,
            "sd2_qt_ms": 0.0,
            "instability_index": 0.0,
            "beats_used": 0,
            "risk_category": "INSUFFICIENT_DATA",
        }

    # Auto-detect if caller passed seconds instead of milliseconds
    finite_mask = np.isfinite(raw_qt) & (raw_qt > 0)
    if not np.any(finite_mask):
        return {
            "stv_qt_ms": 0.0,
            "ltv_qt_ms": 0.0,
            "sd1_qt_ms": 0.0,
            "sd2_qt_ms": 0.0,
            "instability_index": 0.0,
            "beats_used": 0,
            "risk_category": "INSUFFICIENT_DATA",
        }

    if float(np.median(raw_qt[finite_mask])) < 2.5:
        raw_qt = raw_qt * 1000.0

    phys_mask = np.isfinite(raw_qt) & (raw_qt >= 120.0) & (raw_qt <= 900.0)
    if beat_classes is not None and len(beat_classes) == len(raw_qt):
        sinus_mask = phys_mask & np.array([str(c).upper() == "N" for c in beat_classes], dtype=bool)
        qt_clean = raw_qt[sinus_mask] if int(np.sum(sinus_mask)) >= 2 else raw_qt[phys_mask]
    else:
        qt_clean = raw_qt[phys_mask]

    n_beats = len(qt_clean)
    if n_beats < 2:
        return {
            "stv_qt_ms": 0.0,
            "ltv_qt_ms": 0.0,
            "sd1_qt_ms": 0.0,
            "sd2_qt_ms": 0.0,
            "instability_index": 0.0,
            "beats_used": int(n_beats),
            "risk_category": "INSUFFICIENT_DATA",
        }

    qt_n = qt_clean[:-1]
    qt_next = qt_clean[1:]
    n_pairs = len(qt_n)
    sqrt2 = math.sqrt(2.0)
    mean_qt = float(np.mean(qt_clean))

    diffs = qt_next - qt_n
    sums_centered = qt_next + qt_n - (2.0 * mean_qt)

    stv_qt = float(np.sum(np.abs(diffs)) / (n_pairs * sqrt2))
    ltv_qt = float(np.sum(np.abs(sums_centered)) / (n_pairs * sqrt2))

    sd1_qt = float(np.std(diffs, ddof=1) / sqrt2) if n_pairs >= 2 else stv_qt
    sd2_qt = float(np.std(qt_next + qt_n, ddof=1) / sqrt2) if n_pairs >= 2 else ltv_qt
    instability_idx = stv_qt / ltv_qt if ltv_qt > 1e-6 else 0.0

    if stv_qt >= 5.5:
        risk_cat = "HIGH_TDP_RISK"
    elif stv_qt >= 4.0:
        risk_cat = "BORDERLINE"
    else:
        risk_cat = "NORMAL"

    return {
        "stv_qt_ms": round(stv_qt, 3),
        "ltv_qt_ms": round(ltv_qt, 3),
        "sd1_qt_ms": round(sd1_qt, 3),
        "sd2_qt_ms": round(sd2_qt, 3),
        "instability_index": round(instability_idx, 3),
        "beats_used": int(n_beats),
        "risk_category": risk_cat,
    }


def summarize_beats(beats: list[dict[str, Any]]) -> dict[str, Any]:
    """Computes summary statistics across detected beats, safely handling None and NaN values."""
    if not beats:
        return {
            "mean_hr_bpm": 0.0,
            "mean_qt_ms": 0.0,
            "mean_qtc_bazett_ms": 0.0,
            "mean_qtc_fridericia_ms": 0.0,
            "mean_qtc_framingham_ms": 0.0,
            "mean_qtc_hodges_ms": 0.0,
            "mean_jt_peak_ms": 0.0,
            "mean_jt_peak_c_ms": 0.0,
            "mean_tpe_ms": 0.0,
            "mean_tpe_qt_ratio": 0.0,
            "stv_qt_ms": 0.0,
            "ltv_qt_ms": 0.0,
            "qt_instability_index": 0.0,
            "stv_risk_category": "INSUFFICIENT_DATA",
            "total_beats": 0,
        }

    hrs = [b["hr_bpm"] for b in beats if b.get("hr_bpm") is not None and not np.isnan(b["hr_bpm"])]
    qts = [b["qt_ms"] for b in beats if b.get("qt_ms") is not None and not np.isnan(b["qt_ms"])]
    qtc_b = [
        b["qtc"]["bazett_ms"]
        for b in beats
        if b.get("qtc") and b["qtc"].get("bazett_ms") is not None and not np.isnan(b["qtc"]["bazett_ms"])
    ]
    qtc_f = [
        b["qtc"]["fridericia_ms"]
        for b in beats
        if b.get("qtc") and b["qtc"].get("fridericia_ms") is not None and not np.isnan(b["qtc"]["fridericia_ms"])
    ]
    qtc_fram = [
        b["qtc"]["framingham_ms"]
        for b in beats
        if b.get("qtc") and b["qtc"].get("framingham_ms") is not None and not np.isnan(b["qtc"]["framingham_ms"])
    ]
    qtc_hodg = [
        b["qtc"]["hodges_ms"]
        for b in beats
        if b.get("qtc") and b["qtc"].get("hodges_ms") is not None and not np.isnan(b["qtc"]["hodges_ms"])
    ]

    jtp = [
        float(b["jt_peak_ms"])
        for b in beats
        if b.get("jt_peak_ms") is not None and not np.isnan(b["jt_peak_ms"]) and float(b["jt_peak_ms"]) > 0
    ]
    jtpc = [
        float(b["jt_peak_c_ms"])
        for b in beats
        if b.get("jt_peak_c_ms") is not None and not np.isnan(b["jt_peak_c_ms"]) and float(b["jt_peak_c_ms"]) > 0
    ]
    tpes = [
        float(b["tpe_ms"])
        for b in beats
        if b.get("tpe_ms") is not None and not np.isnan(b["tpe_ms"]) and float(b["tpe_ms"]) > 0
    ]
    tpe_ratios = [
        float(b["tpe_qt_ratio"])
        for b in beats
        if b.get("tpe_qt_ratio") is not None and not np.isnan(b["tpe_qt_ratio"]) and float(b["tpe_qt_ratio"]) > 0
    ]

    qt_for_stv = [float(b.get("qt_ms", 0.0)) for b in beats]
    classes_for_stv = [str(b.get("beat_class", "N")) for b in beats]
    stv_info = compute_stv_qt(qt_for_stv, beat_classes=classes_for_stv)

    return {
        "mean_hr_bpm": float(np.mean(hrs)) if hrs else 0.0,
        "mean_qt_ms": float(np.mean(qts)) if qts else 0.0,
        "mean_qtc_bazett_ms": float(np.mean(qtc_b)) if qtc_b else 0.0,
        "mean_qtc_fridericia_ms": float(np.mean(qtc_f)) if qtc_f else 0.0,
        "mean_qtc_framingham_ms": float(np.mean(qtc_fram)) if qtc_fram else 0.0,
        "mean_qtc_hodges_ms": float(np.mean(qtc_hodg)) if qtc_hodg else 0.0,
        "mean_jt_peak_ms": float(np.mean(jtp)) if jtp else 0.0,
        "mean_jt_peak_c_ms": float(np.mean(jtpc)) if jtpc else 0.0,
        "mean_tpe_ms": float(np.mean(tpes)) if tpes else 0.0,
        "mean_tpe_qt_ratio": float(np.mean(tpe_ratios)) if tpe_ratios else 0.0,
        "stv_qt_ms": float(stv_info["stv_qt_ms"]),
        "ltv_qt_ms": float(stv_info["ltv_qt_ms"]),
        "qt_instability_index": float(stv_info["instability_index"]),
        "stv_risk_category": str(stv_info["risk_category"]),
        "total_beats": len(beats),
    }
