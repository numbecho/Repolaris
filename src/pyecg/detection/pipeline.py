"""Comprehensive ECG Analysis and Diagnostic Pipeline module.

Coordinates end-to-end processing of electrocardiogram recordings:
1. Signal conditioning (Butterworth bandpass filtering & two-stage median baseline removal).
2. QRS complex identification and R-peak localization.
3. Ventricular repolarization segmentation (Q-onset and T-end fiducials).
4. Rate-corrected QT computation (Bazett, Fridericia, Framingham formulas).
5. AAMI EC57 abnormal beat classification (Normal, PVC, PAC, Fusion, Unknown).
6. Repetitive ectopic rhythm sequence detection (Bigeminy, Trigeminy, Couplets, VT runs).
7. Clinical events diary auto-detection (Critical QTc, Pauses, Tachycardia, Bradycardia).
8. Berger QT Variability Index (QTVI) repolarization lability assessment.
9. QT-RR restitution curve modeling (linear and hyperbolic).
10. Signal Quality Index (SQI) evaluation.
11. Unified annotation manager integration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
import numpy as np

from pyecg.config import ECGConfig
from pyecg.preprocessing.filter import bandpass_filter, notch_filter
from pyecg.preprocessing.baseline import remove_baseline_wander
from pyecg.detection.qrs import detect_r_peaks
from pyecg.detection.q_onset import detect_q_onset
from pyecg.detection.t_end import detect_t_end
from pyecg.detection.pulse_metrics import compute_qtc, summarize_beats
from pyecg.detection.events import detect_clinical_events, ECGEvent
from pyecg.detection.qtvi import compute_qtvi
from pyecg.detection.qtrr import fit_qtrr_model
from pyecg.detection.sqi import evaluate_lead_quality
from pyecg.detection.classifier import classify_all_beats, ClassifiedBeat
from pyecg.detection.annotations import AnnotationManager


def analyze_ecg(
    raw_signal: np.ndarray,
    fs: float = 500.0,
    config: Optional[ECGConfig] = None,
) -> Dict[str, Any]:
    """Executes the master diagnostic analysis pipeline on a raw ECG signal.

    Args:
        raw_signal: 1D numpy array of raw ECG voltage measurements.
        fs: Sampling frequency in Hertz (default: 500.0).
        config: Optional ECGConfig instance specifying filter and detection parameters.

    Returns:
        A dictionary containing:
            - 'clean_signal': Baseline-corrected, filtered 1D signal array.
            - 'r_peaks': 1D array of detected R-peak sample indices.
            - 'beats': List of dictionaries detailing beat fiducials, intervals, and classifications.
            - 'classified_beats': List of ClassifiedBeat instances (AAMI EC57 classes).
            - 'ectopic_summary': Summary of PVC/PAC counts, burden percentage, and rhythm patterns.
            - 'annotations': AnnotationManager instance containing all beat annotations.
            - 'events': List of clinical event dictionaries (Critical QTc, Pauses, etc.).
            - 'summary': Aggregate statistics (mean HR, mean QTc, min/max intervals).
            - 'qtvi': Berger QT Variability Index (float or None if insufficient beats).
            - 'qtrr': Dictionary of QT-RR restitution fit metrics (or None).
            - 'sqi': Lead signal quality indicators (pSQI, basSQI, SNR, verdict).
    """
    if config is None:
        config = ECGConfig(sampling_rate=fs)

    # 1. Preprocessing and noise reduction
    filtered = bandpass_filter(raw_signal, fs, config.filter_cfg)
    clean_signal = remove_baseline_wander(filtered, fs)

    # 2. Lead Signal Quality Evaluation
    sqi_metrics = evaluate_lead_quality(clean_signal, fs)

    # 3. QRS Detection
    r_peaks = detect_r_peaks(clean_signal, fs, config.detection_cfg.refractory_period_ms)

    beats: List[Dict[str, Any]] = []
    n_peaks = len(r_peaks)

    # 4. Waveform Fiducial Segmentation
    rr_list: List[float] = []
    qt_list: List[float] = []
    q_onsets_list: List[int] = []
    t_ends_list: List[int] = []

    for i, r_idx in enumerate(r_peaks):
        q_idx = detect_q_onset(clean_signal, r_idx, fs, config.detection_cfg.q_search_window_ms)
        t_peak_idx, t_end_idx = detect_t_end(clean_signal, r_idx, fs, config.detection_cfg.t_search_window_ms)

        qt_sec = (t_end_idx - q_idx) / fs

        # Calculate RR interval
        if i < n_peaks - 1:
            rr_sec = (r_peaks[i + 1] - r_idx) / fs
        elif i > 0:
            rr_sec = (r_idx - r_peaks[i - 1]) / fs
        else:
            rr_sec = 1.0

        hr_bpm = 60.0 / rr_sec if rr_sec > 0 else np.nan
        qtc_dict = compute_qtc(qt_sec, rr_sec)

        rr_list.append(rr_sec)
        qt_list.append(qt_sec)
        q_onsets_list.append(int(q_idx))
        t_ends_list.append(int(t_end_idx))

        beats.append({
            "beat_index": i,
            "q_onset_sample": int(q_idx),
            "r_peak_sample": int(r_idx),
            "t_peak_sample": int(t_peak_idx),
            "t_end_sample": int(t_end_idx),
            "time_sec": float(r_idx / fs),
            "rr_sec": float(rr_sec),
            "hr_bpm": float(hr_bpm),
            "qt_ms": float(qt_sec * 1000.0),
            "qtc": qtc_dict,
        })

    # 5. Beat Classification & Rhythm Sequence Analysis (AAMI EC57)
    q_arr = np.array(q_onsets_list, dtype=int)
    t_arr = np.array(t_ends_list, dtype=int)
    classified_beats, ectopic_summary = classify_all_beats(
        signal=clean_signal,
        r_peaks=r_peaks,
        q_onsets=q_arr,
        t_ends=t_arr,
        fs=fs,
    )

    # Attach classification results and build AnnotationManager
    annotation_mgr = AnnotationManager()
    for i, cb in enumerate(classified_beats):
        beats[i]["beat_class"] = cb.beat_class.value
        beats[i]["rhythm_pattern"] = cb.rhythm_pattern.value
        beats[i]["classification_confidence"] = cb.confidence
        beats[i]["diagnostic_rationale"] = cb.diagnostic_rationale

        annotation_mgr.add_annotation(
            sample=cb.r_peak_sample,
            timestamp_sec=cb.time_sec,
            label=cb.beat_class.value,
            sublabel=cb.rhythm_pattern.value if cb.rhythm_pattern.value != "NSR" else "",
            author="AI_DETECTOR",
            notes=cb.diagnostic_rationale,
        )

    summary = summarize_beats(beats)
    summary["ectopic_summary"] = ectopic_summary

    events = detect_clinical_events(beats, fs=fs)

    # 6. Advanced Repolarization Lability: QTVI & QT-RR Restitution
    qtvi_score: Optional[float] = None
    qtrr_metrics: Optional[Dict[str, Any]] = None

    if len(beats) >= 5:
        try:
            qtvi_score = compute_qtvi(np.array(rr_list), np.array(qt_list))
        except (ValueError, ZeroDivisionError):
            qtvi_score = None

        try:
            fit_res = fit_qtrr_model(np.array(rr_list), np.array(qt_list), model="linear")
            qtrr_metrics = {
                "model": "linear",
                "slope": fit_res["slope"],
                "intercept": fit_res["intercept"],
                "pearson_r": fit_res["pearson_r"],
                "p_value": fit_res["p_value"],
            }
        except (ValueError, ZeroDivisionError):
            qtrr_metrics = None

    return {
        "clean_signal": clean_signal,
        "r_peaks": r_peaks,
        "beats": beats,
        "classified_beats": classified_beats,
        "ectopic_summary": ectopic_summary,
        "annotations": annotation_mgr,
        "events": [ev.to_dict() for ev in events],
        "summary": summary,
        "qtvi": qtvi_score,
        "qtrr": qtrr_metrics,
        "sqi": sqi_metrics,
    }
