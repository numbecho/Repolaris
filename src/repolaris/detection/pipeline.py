"""Comprehensive ECG Analysis and Diagnostic Pipeline module.

Coordinates end-to-end processing of electrocardiogram recordings:
1. Signal conditioning (IIR notch filter, Butterworth bandpass filtering & two-stage median baseline removal).
2. QRS complex identification and R-peak localization.
3. Ventricular repolarization segmentation (Q-onset and T-end fiducials).
4. Rate-corrected QT computation (Bazett, Fridericia, Framingham, Hodges formulas).
5. AAMI EC57 abnormal beat classification (Normal, PVC, PAC, Fusion, Unknown).
6. Repetitive ectopic rhythm sequence detection (Bigeminy, Trigeminy, Couplets, VT runs).
7. Clinical events diary auto-detection (Critical QTc, Pauses, Tachycardia, Bradycardia).
8. Berger QT Variability Index (QTVI) repolarization lability assessment.
9. QT-RR restitution curve modeling (6 empirical formulations).
10. Signal Quality Index (SQI) evaluation.
11. Unified annotation manager integration.
12. Version 0.6.0 Autonomic & Spatial Repolarization Suite (HRV, HRT, TWA, Hysteresis, Multi-Lead QTd).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Union
import numpy as np

from repolaris.config import ECGConfig
from repolaris.preprocessing.filter import bandpass_filter, notch_filter
from repolaris.preprocessing.baseline import remove_baseline_wander
from repolaris.detection.qrs import detect_r_peaks
from repolaris.detection.q_onset import detect_q_onset
from repolaris.detection.t_end import detect_t_end
from repolaris.detection.pulse_metrics import compute_qtc, summarize_beats
from repolaris.detection.events import detect_clinical_events, ECGEvent
from repolaris.detection.qtvi import compute_qtvi
from repolaris.detection.qtrr import fit_qtrr_model
from repolaris.detection.sqi import evaluate_lead_quality
from repolaris.detection.classifier import classify_all_beats, ClassifiedBeat
from repolaris.detection.annotations import AnnotationManager
from repolaris.detection.dispersion import calculate_qt_dispersion
from repolaris.detection.twa import compute_spectral_twa, compute_mma_twa
from repolaris.detection.hrt import compute_heart_rate_turbulence
from repolaris.detection.hrv import compute_comprehensive_hrv
from repolaris.detection.hysteresis import optimize_hysteresis_parameter


def analyze_ecg(
    raw_signal: np.ndarray,
    fs: float = 500.0,
    config: Optional[ECGConfig] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    multi_lead_signals: Optional[Union[np.ndarray, Dict[str, np.ndarray]]] = None,
    lead_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Executes the master diagnostic analysis pipeline on a raw ECG signal.

    Args:
        raw_signal: 1D numpy array of raw ECG voltage measurements.
        fs: Sampling frequency in Hertz (default: 500.0).
        config: Optional ECGConfig instance specifying filter and detection parameters.
        progress_callback: Optional callback receiving (fraction, status_message).
        multi_lead_signals: Optional 2D array or dict of multi-lead signals for spatial QTd.
        lead_names: Optional list of lead identifiers when multi_lead_signals is a 2D array.

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
            - 'hrv': Comprehensive HRV dictionary (time_domain, frequency_domain, nonlinear).
            - 'hrt': Heart Rate Turbulence dictionary (turbulence_onset, turbulence_slope, category).
            - 'twa': Microvolt T-Wave Alternans dictionary (spectral and mma).
            - 'hysteresis': Multi-beat QT-RR memory hysteresis dictionary (or None).
            - 'dispersion': Multi-lead spatial QT dispersion dictionary (or None if <3 valid leads).
    """
    if config is None:
        config = ECGConfig(sampling_rate=fs)

    if progress_callback:
        progress_callback(0.10, "Preprocessing and baseline wander removal...")
    # 1. Preprocessing and noise reduction (IIR notch + Butterworth bandpass + two-stage median baseline)
    notched = notch_filter(
        raw_signal,
        fs,
        freq=config.filter_cfg.notch_freq,
        q=config.filter_cfg.notch_quality,
    )
    filtered = bandpass_filter(notched, fs, config.filter_cfg)
    clean_signal = remove_baseline_wander(filtered, fs)

    if progress_callback:
        progress_callback(0.25, "Evaluating lead signal quality (SQI)...")
    # 2. Lead Signal Quality Evaluation
    sqi_metrics = evaluate_lead_quality(clean_signal, fs)

    if progress_callback:
        progress_callback(0.40, "Detecting QRS complexes and R-peaks...")
    # 3. QRS Detection
    r_peaks = detect_r_peaks(clean_signal, fs, config.detection_cfg.refractory_period_ms)

    beats: List[Dict[str, Any]] = []
    n_peaks = len(r_peaks)

    if progress_callback:
        progress_callback(0.60, f"Segmenting fiducials ({n_peaks} cardiac cycles)...")
    # 4. Waveform Fiducial Segmentation
    rr_list: List[float] = []
    qt_list: List[float] = []
    q_onsets_list: List[int] = []
    t_ends_list: List[int] = []

    for i, r_idx in enumerate(r_peaks):
        q_idx = detect_q_onset(clean_signal, r_idx, fs, config.detection_cfg.q_search_window_ms)
        t_peak_idx, t_end_idx = detect_t_end(
            clean_signal,
            r_idx,
            fs,
            config.detection_cfg.t_search_window_ms,
            config.detection_cfg.t_end_threshold_ratio,
        )

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

    if progress_callback:
        progress_callback(0.75, "Classifying beats and ectopic rhythm sequences...")
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
    beat_class_codes: List[str] = []
    nn_intervals_ms: List[float] = []

    for i, cb in enumerate(classified_beats):
        code = cb.beat_class.value
        beat_class_codes.append(code)
        beats[i]["beat_class"] = code
        beats[i]["rhythm_pattern"] = cb.rhythm_pattern.value
        beats[i]["classification_confidence"] = cb.confidence
        beats[i]["diagnostic_rationale"] = cb.diagnostic_rationale

        if code == "N" and beats[i]["rr_sec"] > 0:
            nn_intervals_ms.append(beats[i]["rr_sec"] * 1000.0)

        annotation_mgr.add_annotation(
            sample=cb.r_peak_sample,
            timestamp_sec=cb.time_sec,
            label=code,
            sublabel=cb.rhythm_pattern.value if cb.rhythm_pattern.value != "NSR" else "",
            author="AI_DETECTOR",
            notes=cb.diagnostic_rationale,
        )

    summary = summarize_beats(beats)
    summary["ectopic_summary"] = ectopic_summary

    events = detect_clinical_events(beats, fs=fs)

    if progress_callback:
        progress_callback(0.90, "Assessing repolarization lability & autonomic metrics...")
    # 6. Advanced Repolarization Lability: QTVI, QT-RR Restitution & v0.6.0 Autonomic Suite
    qtvi_score: Optional[float] = None
    qtrr_metrics: Optional[Dict[str, Any]] = None
    hysteresis_metrics: Optional[Dict[str, Any]] = None

    rr_arr = np.array(rr_list, dtype=np.float64)
    qt_arr = np.array(qt_list, dtype=np.float64)

    if len(beats) >= 5:
        try:
            qtvi_score = compute_qtvi(rr_arr, qt_arr)
        except (ValueError, ZeroDivisionError):
            qtvi_score = None

        try:
            fit_res = fit_qtrr_model(rr_arr, qt_arr, model="linear")
            qtrr_metrics = {
                "model": "linear",
                "slope": fit_res["slope"],
                "linear_slope": fit_res["slope"],
                "intercept": fit_res["intercept"],
                "pearson_r": fit_res["pearson_r"],
                "p_value": fit_res["p_value"],
            }
        except (ValueError, ZeroDivisionError):
            qtrr_metrics = None

        try:
            hysteresis_metrics = optimize_hysteresis_parameter(qt_arr, rr_arr, model_type="linear")
        except (ValueError, ZeroDivisionError):
            hysteresis_metrics = None

    # Comprehensive HRV (on NN intervals, or all RR intervals if < 3 classified 'N')
    hrv_input_ms = nn_intervals_ms if len(nn_intervals_ms) >= 4 else [r * 1000.0 for r in rr_list]
    hrv_metrics = compute_comprehensive_hrv(hrv_input_ms) if len(hrv_input_ms) >= 2 else None

    # Heart Rate Turbulence (HRT)
    hrt_metrics = compute_heart_rate_turbulence(classified_beats, r_peaks, fs=fs)

    # Microvolt T-Wave Alternans (TWA: Spectral FFT + MMA)
    twa_metrics = {
        "spectral": compute_spectral_twa(clean_signal, fs, r_peaks, beat_classes=beat_class_codes),
        "mma": compute_mma_twa(clean_signal, fs, r_peaks),
    }

    # Multi-Lead Spatial QT Dispersion (if synchronous multi-lead matrix/dict provided)
    dispersion_metrics: Optional[Dict[str, Any]] = None
    if multi_lead_signals is not None:
        dispersion_metrics = calculate_qt_dispersion(
            multi_lead_signals,
            fs=fs,
            lead_names=lead_names,
            config=config.detection_cfg,
        )

    if progress_callback:
        progress_callback(1.00, f"Diagnostic analysis complete ({n_peaks} beats processed).")
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
        "hrv": hrv_metrics,
        "hrt": hrt_metrics,
        "twa": twa_metrics,
        "hysteresis": hysteresis_metrics,
        "dispersion": dispersion_metrics,
    }
