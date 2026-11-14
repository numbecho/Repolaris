"""Comprehensive ECG Analysis and Diagnostic Pipeline module.

Coordinates end-to-end processing of electrocardiogram recordings:
1. Signal conditioning (IIR Q=30 notch filter, 0.05-45 Hz Butterworth bandpass & two-stage median baseline removal).
2. Two-Stage Signal Quality Index (SQI) evaluation (Stage 1 Li et al. 2014 absolute gates + Stage 2 6-index pairwise voting).
3. QRS complex identification and R-peak localization.
4. Ventricular repolarization segmentation (Q-onset and hybrid/tangent/Zhang-2006-area/threshold T-end fiducials).
5. Rate-corrected QT computation (Bazett, Fridericia, Framingham, Hodges formulas).
6. AAMI EC57 abnormal beat classification (Normal, PVC, PAC, Fusion, Unknown).
7. Repetitive ectopic rhythm sequence detection (Bigeminy, Trigeminy, Couplets, VT runs).
8. Clinical events diary auto-detection (Critical QTc, Pauses, Tachycardia, Bradycardia).
9. Berger QT Variability Index (QTVI) repolarization lability assessment.
10. Domain-guarded 10-model QT-RR restitution curve modeling (Pueyo et al., 2004) with EW/LW hysteresis compensation.
11. Unified annotation manager integration.
12. Autonomic & Spatial Repolarization Suite (HRV, HRT, TWA, Hysteresis, Multi-Lead QTd).
13. Atrial Fibrillation / Flutter burden & episode detection (repolaris.detection.af_detector).
14. Hourly Arrhythmia Trend Histograms & Holter Summary (repolaris.detection.trends).
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
from repolaris.detection.qtrr import fit_qtrr_model, fit_all_qtrr_models
from repolaris.detection.sqi import evaluate_lead_quality, rank_leads_two_stage
from repolaris.detection.classifier import classify_all_beats, ClassifiedBeat
from repolaris.detection.annotations import AnnotationManager
from repolaris.detection.dispersion import calculate_qt_dispersion
from repolaris.detection.twa import compute_spectral_twa, compute_mma_twa
from repolaris.detection.hrt import compute_heart_rate_turbulence
from repolaris.detection.hrv import compute_comprehensive_hrv
from repolaris.detection.hysteresis import (
    compute_effective_rr_exponential,
    compute_effective_rr_linear,
    optimize_hysteresis_parameter,
)
from repolaris.detection.af_detector import detect_atrial_fibrillation
from repolaris.detection.trends import generate_hourly_trends


def analyze_ecg(
    raw_signal: np.ndarray,
    fs: float = 500.0,
    config: Optional[ECGConfig] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    multi_lead_signals: Optional[Union[np.ndarray, Dict[str, np.ndarray]]] = None,
    lead_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Executes the master diagnostic analysis pipeline on a raw ECG signal."""
    if config is None:
        config = ECGConfig(sampling_rate=fs)

    if progress_callback:
        progress_callback(0.10, "Preprocessing and baseline wander removal...")
    # 1. Preprocessing and noise reduction (IIR Q=30 notch + 0.05-45 Hz Butterworth + two-stage median baseline)
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
    # 2. Lead Signal Quality Evaluation (Stage 1 Absolute + Stage 2 Pairwise Voting if multi-lead)
    sqi_metrics = evaluate_lead_quality(clean_signal, fs)
    lead_voting: Optional[Dict[str, Any]] = None
    if multi_lead_signals is not None:
        lead_voting = rank_leads_two_stage(multi_lead_signals, fs=fs, lead_names=lead_names)

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

    t_end_method = getattr(config.detection_cfg, "t_end_method", "hybrid")

    for i, r_idx in enumerate(r_peaks):
        q_idx = detect_q_onset(clean_signal, r_idx, fs, config.detection_cfg.q_search_window_ms)
        t_peak_idx, t_end_idx = detect_t_end(
            clean_signal,
            r_idx,
            fs,
            config.detection_cfg.t_search_window_ms,
            method=t_end_method,
        )

        q_onsets_list.append(int(q_idx))
        t_ends_list.append(int(t_end_idx))

        rr = (r_idx - r_peaks[i - 1]) / fs if i > 0 else 0.0
        qt = (t_end_idx - q_idx) / fs
        hr = 60.0 / rr if rr > 0 else np.nan

        rr_list.append(rr)
        qt_list.append(qt)

        qtc_values = compute_qtc(qt, rr) if rr > 0 else {}

        beats.append({
            "beat_index": i,
            "r_peak_sample": int(r_idx),
            "time_sec": float(r_idx / fs),
            "q_onset_sample": int(q_idx),
            "t_peak_sample": int(t_peak_idx),
            "t_end_sample": int(t_end_idx),
            "rr_sec": float(rr),
            "hr_bpm": float(hr),
            "qt_sec": float(qt),
            "qt_ms": float(qt * 1000.0),
            "qtc": qtc_values,
        })

    if progress_callback:
        progress_callback(0.75, "Classifying beats and ectopic rhythm patterns...")
    # 5. Beat Classification and Rhythm Identification (ANSI/AAMI EC57)
    q_onsets_arr = np.array(q_onsets_list, dtype=np.int64)
    t_ends_arr = np.array(t_ends_list, dtype=np.int64)
    classified_beats, ectopic_summary = classify_all_beats(
        signal=clean_signal,
        r_peaks=r_peaks,
        q_onsets=q_onsets_arr,
        t_ends=t_ends_arr,
        fs=fs,
    )

    # Attach classifications back to beat dictionaries & collect normal NN intervals for HRV
    nn_intervals_ms: List[float] = []
    beat_class_codes: List[str] = []

    for i, cb in enumerate(classified_beats):
        if i < len(beats):
            beats[i]["beat_class"] = cb.beat_class.value
            beats[i]["rhythm_pattern"] = cb.rhythm_pattern.value
            beats[i]["classification_confidence"] = cb.confidence
            beats[i]["diagnostic_rationale"] = cb.diagnostic_rationale
            beats[i]["qrs_duration_ms"] = cb.features.qrs_duration_ms
            beats[i]["template_correlation"] = cb.features.template_correlation

        code = cb.beat_class.value
        beat_class_codes.append(code)
        if code == "N" and i > 0 and beats[i]["rr_sec"] and beats[i]["rr_sec"] > 0.2:
            nn_intervals_ms.append(beats[i]["rr_sec"] * 1000.0)

    # Populate AnnotationManager
    annotation_mgr = AnnotationManager()
    for cb in classified_beats:
        code = cb.beat_class.value
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
        progress_callback(0.85, "Evaluating AF/AFL episode burden and hourly trends...")
    # Atrial Fibrillation / Flutter burden analysis
    af_report = detect_atrial_fibrillation(r_peaks, fs=fs)

    # Hourly Arrhythmia Trend Histograms
    rec_dur = float(len(clean_signal) / fs)
    trends_report = generate_hourly_trends(
        classified_beats,
        events=[ev.to_dict() for ev in events],
        total_duration_sec=rec_dur,
        af_episodes=af_report.episodes,
    )

    if progress_callback:
        progress_callback(0.92, "Assessing repolarization lability & autonomic metrics...")
    # 6. Advanced Repolarization Lability: QTVI, 10-Model QT-RR Restitution & v0.6.1 Autonomic Suite
    qtvi_score: Optional[float] = None
    qtrr_metrics: Optional[Dict[str, Any]] = None
    hysteresis_metrics: Optional[Dict[str, Any]] = None

    rr_arr = np.array(rr_list, dtype=np.float64)
    qt_arr = np.array(qt_list, dtype=np.float64)

    preferred_qtrr_model = getattr(config.detection_cfg, "qtrr_model", "linear")
    enable_hysteresis = getattr(config.detection_cfg, "enable_hysteresis", True)
    hysteresis_kernel = getattr(config.detection_cfg, "hysteresis_kernel", "exponential")

    if len(beats) >= 5:
        try:
            qtvi_score = compute_qtvi(rr_arr, qt_arr)
        except (ValueError, ZeroDivisionError):
            qtvi_score = None

        try:
            hysteresis_metrics = optimize_hysteresis_parameter(qt_arr, rr_arr, model_type="linear")
        except (ValueError, ZeroDivisionError):
            hysteresis_metrics = None

        try:
            if enable_hysteresis and hysteresis_metrics is not None:
                if hysteresis_kernel == "linear":
                    rr_used = compute_effective_rr_linear(rr_arr, memory_beats=25)
                else:
                    rr_used = np.asarray(hysteresis_metrics.get("effective_rr_sec", rr_arr), dtype=np.float64)
            else:
                rr_used = rr_arr

            multi_fit = fit_all_qtrr_models(rr_used, qt_arr, preferred_model=preferred_qtrr_model)
            active_fit = multi_fit["active_fit"]
            lin_fit = multi_fit["models"].get("linear", active_fit)

            qtrr_metrics = {
                "model": active_fit["model"],
                "label": active_fit["label"],
                "equation": active_fit["equation"],
                "slope": active_fit["slope"],
                "linear_slope": lin_fit["slope"],
                "intercept": active_fit["intercept"],
                "pearson_r": active_fit["pearson_r"],
                "r_squared": active_fit["r_squared"],
                "p_value": active_fit["p_value"],
                "rmse_ms": active_fit["rmse_ms"],
                "aic": active_fit["aic"],
                "qtc_individual_ms": active_fit["qtc_individual_ms"],
                "best_model": multi_fit["best_model"],
                "ranking": multi_fit["ranking"],
                "hysteresis_enabled": bool(enable_hysteresis and hysteresis_metrics is not None),
                "hysteresis_kernel": hysteresis_kernel if enable_hysteresis else "raw",
                "rr_raw_sec": rr_arr.tolist(),
                "rr_effective_sec": rr_used.tolist(),
                "qt_sec": qt_arr.tolist(),
                "qt_ms": (qt_arr * 1000.0).tolist(),
            }
        except (ValueError, ZeroDivisionError):
            qtrr_metrics = None

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
        "lead_voting": lead_voting,
        "hrv": hrv_metrics,
        "hrt": hrt_metrics,
        "twa": twa_metrics,
        "hysteresis": hysteresis_metrics,
        "dispersion": dispersion_metrics,
        "af_report": af_report.to_dict(),
        "trends": trends_report.to_dict(),
    }


def analyze_ecg_stream(
    signal_or_path: Union[np.ndarray, str],
    fs: float = 500.0,
    lead: Union[str, int] = 0,
    chunk_duration_sec: float = 300.0,
    overlap_sec: float = 5.0,
    config: Optional[ECGConfig] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """Executes chunked out-of-core ECG analysis across continuous multi-hour Holter recordings.

    Processes overlapping windows to prevent filter edge transients, deduplicates R-peaks at
    chunk boundaries, and aggregates full-study arrhythmia trends, AF burden, HRV, HRT, and QTc.
    """
    from repolaris.io.ecg_loader import stream_ecg_chunks

    if isinstance(signal_or_path, np.ndarray):
        raw_arr = np.asarray(signal_or_path, dtype=np.float32)
        total_samples = len(raw_arr)
        chunk_samples = max(int(fs * 10), int(round(chunk_duration_sec * fs)))
        overlap_samples = max(0, int(round(overlap_sec * fs)))

        def _array_gen():
            c_start = 0
            c_idx = 0
            while c_start < total_samples:
                c_end = min(total_samples, c_start + chunk_samples)
                w_start = max(0, c_start - overlap_samples)
                w_end = min(total_samples, c_end + overlap_samples)
                yield {
                    "chunk_index": c_idx,
                    "start_sample": w_start,
                    "end_sample": w_end,
                    "core_start_sample": c_start,
                    "core_end_sample": c_end,
                    "signal": raw_arr[w_start:w_end],
                    "fs": fs,
                    "total_samples": total_samples,
                    "metadata": {"mmap_backed": isinstance(signal_or_path, np.memmap)},
                }
                c_start = c_end
                c_idx += 1

        chunk_iter = _array_gen()
    else:
        chunk_iter = stream_ecg_chunks(
            signal_or_path,
            lead_name_or_index=lead,
            chunk_duration_sec=chunk_duration_sec,
            overlap_sec=overlap_sec,
        )

    all_r_peaks: List[int] = []
    all_beats: List[Dict[str, Any]] = []
    all_classified: List[ClassifiedBeat] = []
    sqi_list: List[Dict[str, Any]] = []
    preview_signal: Optional[np.ndarray] = None
    actual_fs = fs
    total_len = 0

    for ch in chunk_iter:
        actual_fs = float(ch["fs"])
        total_len = int(ch["total_samples"])
        w_start = int(ch["start_sample"])
        core_start = int(ch["core_start_sample"])
        core_end = int(ch["core_end_sample"])
        sig_win = ch["signal"]

        if progress_callback and total_len > 0:
            frac = min(0.85, (core_end / total_len) * 0.85)
            progress_callback(frac, f"Streaming chunk {ch['chunk_index'] + 1} ({core_end / actual_fs:.0f}s / {total_len / actual_fs:.0f}s)...")

        res_win = analyze_ecg(sig_win, fs=actual_fs, config=config)
        if preview_signal is None:
            preview_signal = res_win["clean_signal"][: min(len(res_win["clean_signal"]), int(actual_fs * 30))]
        sqi_list.append(res_win["sqi"])

        for b, cb in zip(res_win["beats"], res_win["classified_beats"]):
            global_r = int(b["r_peak_sample"]) + w_start
            if core_start <= global_r < core_end:
                if all_r_peaks and (global_r - all_r_peaks[-1]) < int(0.20 * actual_fs):
                    continue
                beat_idx = len(all_beats)
                rr_sec = (global_r - all_r_peaks[-1]) / actual_fs if all_r_peaks else 0.0
                hr_bpm = 60.0 / rr_sec if rr_sec > 0 else np.nan
                qt_sec = float(b["qt_sec"])
                qtc_vals = compute_qtc(qt_sec, rr_sec) if rr_sec > 0 else {}

                b_copy = dict(b)
                b_copy.update({
                    "beat_index": beat_idx,
                    "r_peak_sample": global_r,
                    "time_sec": float(global_r / actual_fs),
                    "q_onset_sample": int(b["q_onset_sample"]) + w_start,
                    "t_peak_sample": int(b["t_peak_sample"]) + w_start,
                    "t_end_sample": int(b["t_end_sample"]) + w_start,
                    "rr_sec": float(rr_sec),
                    "hr_bpm": float(hr_bpm),
                    "qtc": qtc_vals,
                })
                cb_copy = ClassifiedBeat(
                    beat_index=beat_idx,
                    r_peak_sample=global_r,
                    time_sec=float(global_r / actual_fs),
                    beat_class=cb.beat_class,
                    rhythm_pattern=cb.rhythm_pattern,
                    confidence=cb.confidence,
                    features=cb.features,
                    diagnostic_rationale=cb.diagnostic_rationale,
                )
                all_r_peaks.append(global_r)
                all_beats.append(b_copy)
                all_classified.append(cb_copy)

    r_peaks_arr = np.array(all_r_peaks, dtype=np.int64)
    summary = summarize_beats(all_beats)

    counts: Dict[str, int] = {}
    for cb in all_classified:
        counts[cb.beat_class.value] = counts.get(cb.beat_class.value, 0) + 1
    pvc_cnt = counts.get("V", 0)
    pac_cnt = counts.get("S", 0)
    tot_b = len(all_classified)
    ectopic_summary = {
        "total_beats": tot_b,
        "counts": counts,
        "pvc_count": pvc_cnt,
        "pac_count": pac_cnt,
        "ectopic_burden_pct": round((pvc_cnt + pac_cnt) / tot_b * 100.0, 2) if tot_b > 0 else 0.0,
    }
    summary["ectopic_summary"] = ectopic_summary

    events = detect_clinical_events(all_beats, fs=actual_fs)
    af_report = detect_atrial_fibrillation(r_peaks_arr, fs=actual_fs)
    rec_dur = float(total_len / actual_fs) if actual_fs > 0 else 0.0
    trends_report = generate_hourly_trends(
        all_classified,
        events=[ev.to_dict() for ev in events],
        total_duration_sec=rec_dur,
        af_episodes=af_report.episodes,
    )

    nn_ms = [b["rr_sec"] * 1000.0 for b in all_beats if b.get("beat_class") == "N" and b.get("rr_sec", 0.0) > 0.2]
    hrv_input = nn_ms if len(nn_ms) >= 4 else [b["rr_sec"] * 1000.0 for b in all_beats if b.get("rr_sec", 0.0) > 0.2]
    hrv_metrics = compute_comprehensive_hrv(hrv_input) if len(hrv_input) >= 2 else None
    hrt_metrics = compute_heart_rate_turbulence(all_classified, r_peaks_arr, fs=actual_fs)

    annotation_mgr = AnnotationManager()
    for cb in all_classified:
        annotation_mgr.add_annotation(
            sample=cb.r_peak_sample,
            timestamp_sec=cb.time_sec,
            label=cb.beat_class.value,
            sublabel=cb.rhythm_pattern.value if cb.rhythm_pattern.value != "NSR" else "",
            author="AI_STREAM_DETECTOR",
            notes=cb.diagnostic_rationale,
        )

    if progress_callback:
        progress_callback(1.00, f"Streamed analysis complete ({tot_b} beats across {rec_dur:.1f}s).")

    return {
        "clean_signal": preview_signal if preview_signal is not None else np.zeros(0, dtype=np.float32),
        "r_peaks": r_peaks_arr,
        "beats": all_beats,
        "classified_beats": all_classified,
        "ectopic_summary": ectopic_summary,
        "annotations": annotation_mgr,
        "events": [ev.to_dict() for ev in events],
        "summary": summary,
        "qtvi": None,
        "qtrr": None,
        "sqi": sqi_list[0] if sqi_list else {},
        "lead_voting": None,
        "hrv": hrv_metrics,
        "hrt": hrt_metrics,
        "twa": None,
        "hysteresis": None,
        "dispersion": None,
        "af_report": af_report.to_dict(),
        "trends": trends_report.to_dict(),
        "streamed": True,
        "total_duration_sec": rec_dur,
    }
