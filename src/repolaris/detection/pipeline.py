"""Comprehensive ECG Analysis and Diagnostic Pipeline module.

Coordinates end-to-end processing of electrocardiogram recordings:
1. Signal conditioning (IIR Q=30 notch filter, 0.05-45 Hz Butterworth bandpass & two-stage median baseline removal).
2. Two-Stage Signal Quality Index (SQI) evaluation (Stage 1 Li et al. 2014 absolute gates + Stage 2 6-index pairwise voting).
3. QRS complex identification and R-peak localization.
4. Ventricular repolarization segmentation (Q-onset and hybrid/tangent/Zhang-2006-area/threshold T-end fiducials).
5. Rate-corrected QT computation (Bazett, Fridericia, Framingham, Hodges formulas).
6. AAMI EC57 & Patrick Hamilton (2002) OSEA abnormal beat classification (Normal, PVC, PAC, Fusion, Unknown).
7. Repetitive ectopic rhythm sequence detection (Bigeminy, Trigeminy, Couplets, VT runs).
8. Clinical events diary auto-detection (Critical QTc, Pauses, Tachycardia, Bradycardia, PVCs).
9. Berger QT Variability Index (QTVI) repolarization lability assessment.
10. Domain-guarded 10-model QT-RR restitution curve modeling (Pueyo et al., 2004) with EW/LW hysteresis compensation.
11. Unified annotation manager integration.
12. Autonomic & Spatial Repolarization Suite (HRV, HRT, TWA, Hysteresis, Multi-Lead QTd).
13. Atrial Fibrillation / Flutter burden & episode detection (repolaris.detection.af_detector).
14. Hourly Arrhythmia Trend Histograms & Holter Summary (repolaris.detection.trends).
15. Out-of-Core Streaming Holter Engine (analyze_ecg_stream).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from typing import Any

import numpy as np

from repolaris.config import ECGConfig
from repolaris.detection.af_detector import detect_atrial_fibrillation
from repolaris.detection.annotations import AnnotationManager
from repolaris.detection.classifier import ClassifiedBeat, classify_all_beats, detect_rhythm_patterns
from repolaris.detection.dispersion import calculate_qt_dispersion
from repolaris.detection.events import detect_clinical_events
from repolaris.detection.hamilton_classifier import HamiltonBeatClassifier
from repolaris.detection.hrt import compute_heart_rate_turbulence
from repolaris.detection.hrv import compute_comprehensive_hrv
from repolaris.detection.hysteresis import (
    compute_effective_rr_linear,
    optimize_hysteresis_parameter,
)
from repolaris.detection.pulse_metrics import compute_qtc, summarize_beats
from repolaris.detection.q_onset import detect_q_onset
from repolaris.detection.qrs import detect_r_peaks
from repolaris.detection.qtrr import fit_all_qtrr_models
from repolaris.detection.qtvi import compute_qtvi
from repolaris.detection.sqi import evaluate_lead_quality, rank_leads_two_stage
from repolaris.detection.t_end import detect_t_end
from repolaris.detection.trends import generate_hourly_trends
from repolaris.detection.twa import compute_mma_twa, compute_spectral_twa
from repolaris.preprocessing.baseline import remove_baseline_wander
from repolaris.preprocessing.filter import bandpass_filter, notch_filter



def _compute_repolarization_dynamics(
    rr_arr: np.ndarray,
    qt_arr: np.ndarray,
    config: ECGConfig,
) -> tuple[float | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Computes Berger QTVI, multi-beat QT-RR hysteresis, and 10-model QT-RR restitution."""
    qtvi_score: float | None = None
    qtrr_metrics: dict[str, Any] | None = None
    hysteresis_metrics: dict[str, Any] | None = None

    preferred_qtrr_model = getattr(config.detection_cfg, "qtrr_model", "linear")
    enable_hysteresis = getattr(config.detection_cfg, "enable_hysteresis", True)
    hysteresis_kernel = getattr(config.detection_cfg, "hysteresis_kernel", "exponential")

    valid_mask = (rr_arr > 0.20) & (qt_arr > 0.05) & np.isfinite(rr_arr) & np.isfinite(qt_arr)
    rr_valid = rr_arr[valid_mask]
    qt_valid = qt_arr[valid_mask]

    if len(rr_valid) >= 5 and len(qt_valid) >= 5:
        with contextlib.suppress(ValueError, ZeroDivisionError):
            qtvi_score = compute_qtvi(rr_valid, qt_valid)

        with contextlib.suppress(ValueError, ZeroDivisionError):
            hysteresis_metrics = optimize_hysteresis_parameter(qt_valid, rr_valid, model_type="linear")

        with contextlib.suppress(ValueError, ZeroDivisionError):
            if enable_hysteresis and hysteresis_metrics is not None:
                if hysteresis_kernel == "linear":
                    rr_used = np.asarray(
                        hysteresis_metrics.get(
                            "rr_eff_lw_sec",
                            compute_effective_rr_linear(rr_valid, memory_beats=25),
                        ),
                        dtype=np.float64,
                    )
                else:
                    rr_used = np.asarray(
                        hysteresis_metrics.get("rr_eff_ew_sec", rr_valid),
                        dtype=np.float64,
                    )
            else:
                rr_used = rr_valid

            multi_fit = fit_all_qtrr_models(rr_used, qt_valid, preferred_model=preferred_qtrr_model)
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
                "rr_raw_sec": rr_valid.tolist(),
                "rr_effective_sec": rr_used.tolist(),
                "qt_sec": qt_valid.tolist(),
                "qt_ms": (qt_valid * 1000.0).tolist(),
            }

    return qtvi_score, qtrr_metrics, hysteresis_metrics


def _build_annotation_manager(
    classified_beats: list[ClassifiedBeat],
    author: str = "AI_DETECTOR",
) -> AnnotationManager:
    """Populates an AnnotationManager from classified beats."""
    mgr = AnnotationManager()
    for cb in classified_beats:
        mgr.add_annotation(
            sample=cb.r_peak_sample,
            timestamp_sec=cb.time_sec,
            label=cb.beat_class.value,
            sublabel=cb.rhythm_pattern.value if cb.rhythm_pattern.value != "NSR" else "",
            author=author,
            notes=cb.diagnostic_rationale,
        )
    return mgr


def _compute_hrv_from_beats(beats: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Extracts normal NN intervals (or falls back to physiological RR intervals) and computes HRV."""
    nn_ms = [b["rr_sec"] * 1000.0 for b in beats if b.get("beat_class") == "N" and b.get("rr_sec", 0.0) > 0.2]
    hrv_input = nn_ms if len(nn_ms) >= 4 else [b["rr_sec"] * 1000.0 for b in beats if b.get("rr_sec", 0.0) > 0.2]
    return compute_comprehensive_hrv(hrv_input) if len(hrv_input) >= 2 else None


def analyze_ecg(
    raw_signal: np.ndarray,
    fs: float = 500.0,
    config: ECGConfig | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
    multi_lead_signals: np.ndarray | dict[str, np.ndarray] | None = None,
    lead_names: list[str] | None = None,
) -> dict[str, Any]:
    """Executes the master diagnostic analysis pipeline on a raw ECG signal."""
    if config is None:
        config = ECGConfig(sampling_rate=fs)

    if progress_callback:
        progress_callback(0.10, "Preprocessing and baseline wander removal...")
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
    sqi_metrics = evaluate_lead_quality(raw_signal, fs, conditioned_signal=clean_signal)
    lead_voting = (
        rank_leads_two_stage(multi_lead_signals, fs=fs, lead_names=lead_names)
        if multi_lead_signals is not None
        else None
    )

    if progress_callback:
        progress_callback(0.40, "Detecting QRS complexes and R-peaks...")
    r_peaks = detect_r_peaks(clean_signal, fs, config.detection_cfg.refractory_period_ms)

    beats: list[dict[str, Any]] = []
    n_peaks = len(r_peaks)

    if progress_callback:
        progress_callback(0.60, f"Segmenting fiducials ({n_peaks} cardiac cycles)...")
    rr_list: list[float] = []
    qt_list: list[float] = []
    q_onsets_list: list[int] = []
    t_ends_list: list[int] = []
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

        rr = (r_idx - r_peaks[i - 1]) / fs if i > 0 else ((r_peaks[1] - r_peaks[0]) / fs if n_peaks > 1 else 0.0)
        qt = (t_end_idx - q_idx) / fs
        hr = 60.0 / rr if rr > 0 else np.nan

        rr_list.append(rr)
        qt_list.append(qt)

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
            "qtc": compute_qtc(qt, rr) if rr > 0 else {},
        })

    if progress_callback:
        progress_callback(0.75, "Classifying beats and ectopic rhythm patterns...")
    q_onsets_arr = np.array(q_onsets_list, dtype=np.int64)
    t_ends_arr = np.array(t_ends_list, dtype=np.int64)
    classified_beats, ectopic_summary = classify_all_beats(
        signal=clean_signal,
        r_peaks=r_peaks,
        q_onsets=q_onsets_arr,
        t_ends=t_ends_arr,
        fs=fs,
    )
    hamilton_clf = HamiltonBeatClassifier(fs=fs)
    hamilton_beats, hamilton_summary = hamilton_clf.classify_recording(
        signal=clean_signal,
        r_peaks=r_peaks,
        q_onsets=q_onsets_arr,
        t_ends=t_ends_arr,
    )
    ectopic_summary["template_cluster_count"] = hamilton_summary.get("template_cluster_count", 1)
    ectopic_summary["af_stabilized"] = hamilton_summary.get("af_stabilized", False)
    ectopic_summary["algorithm"] = "ANSI/AAMI EC57 + Hamilton (2002) OSEA"
    if hamilton_summary.get("af_stabilized", False):
        classified_beats = hamilton_beats
        ectopic_summary.update(hamilton_summary)

    beat_class_codes: list[str] = []
    for i, cb in enumerate(classified_beats):
        code = cb.beat_class.value
        beat_class_codes.append(code)
        if i < len(beats):
            beats[i].update({
                "beat_class": code,
                "rhythm_pattern": cb.rhythm_pattern.value,
                "classification_confidence": cb.confidence,
                "diagnostic_rationale": cb.diagnostic_rationale,
                "qrs_duration_ms": cb.features.qrs_duration_ms,
                "template_correlation": cb.features.template_correlation,
            })

    annotation_mgr = _build_annotation_manager(classified_beats, author="AI_DETECTOR")
    summary = summarize_beats(beats)
    summary["ectopic_summary"] = ectopic_summary
    events = detect_clinical_events(beats, fs=fs)

    if progress_callback:
        progress_callback(0.85, "Evaluating AF/AFL episode burden and hourly trends...")
    af_report = detect_atrial_fibrillation(r_peaks, fs=fs)
    rec_dur = float(len(clean_signal) / fs)
    trends_report = generate_hourly_trends(
        classified_beats,
        events=[ev.to_dict() for ev in events],
        total_duration_sec=rec_dur,
        af_episodes=af_report.episodes,
    )

    if progress_callback:
        progress_callback(0.92, "Assessing repolarization lability & autonomic metrics...")
    rr_arr = np.array(rr_list, dtype=np.float64)
    qt_arr = np.array(qt_list, dtype=np.float64)
    qtvi_score, qtrr_metrics, hysteresis_metrics = _compute_repolarization_dynamics(rr_arr, qt_arr, config)

    hrv_metrics = _compute_hrv_from_beats(beats)
    hrt_metrics = compute_heart_rate_turbulence(classified_beats, r_peaks, fs=fs)
    twa_metrics = {
        "spectral": compute_spectral_twa(clean_signal, fs, r_peaks, beat_classes=beat_class_codes),
        "mma": compute_mma_twa(clean_signal, fs, r_peaks),
    }
    dispersion_metrics = (
        calculate_qt_dispersion(
            multi_lead_signals,
            fs=fs,
            lead_names=lead_names,
            config=config.detection_cfg,
        )
        if multi_lead_signals is not None
        else None
    )

    if progress_callback:
        progress_callback(1.00, f"Diagnostic analysis complete ({n_peaks} beats processed).")
    return {
        "fs": float(fs),
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


def _iter_array_chunks(
    signal_arr: np.ndarray,
    fs: float,
    chunk_duration_sec: float,
    overlap_sec: float,
) -> Iterator[dict[str, Any]]:
    """Yields overlapping chunks from an in-memory or memory-mapped 1D array."""
    raw_arr = np.asarray(signal_arr, dtype=np.float32)
    total_samples = len(raw_arr)
    chunk_samples = max(1, int(round(chunk_duration_sec * fs)))
    overlap_samples = max(0, int(round(overlap_sec * fs)))

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
            "metadata": {"mmap_backed": isinstance(signal_arr, np.memmap)},
        }
        c_start = c_end
        c_idx += 1


def analyze_ecg_stream(
    signal_or_path: np.ndarray | str,
    fs: float = 500.0,
    lead: str | int = 0,
    chunk_duration_sec: float = 300.0,
    overlap_sec: float = 5.0,
    config: ECGConfig | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Executes chunked out-of-core ECG analysis across continuous multi-hour Holter recordings."""
    from repolaris.io.ecg_loader import stream_ecg_chunks

    if config is None:
        config = ECGConfig(sampling_rate=fs)

    chunk_iter = (
        _iter_array_chunks(signal_or_path, fs, chunk_duration_sec, overlap_sec)
        if isinstance(signal_or_path, np.ndarray)
        else stream_ecg_chunks(
            signal_or_path,
            lead_name_or_index=lead,
            chunk_duration_sec=chunk_duration_sec,
            overlap_sec=overlap_sec,
        )
    )

    all_r_peaks: list[int] = []
    all_beats: list[dict[str, Any]] = []
    all_classified: list[ClassifiedBeat] = []
    sqi_list: list[dict[str, Any]] = []
    twa_list: list[dict[str, Any]] = []
    stream_meta: dict[str, Any] = {}
    preview_signal: np.ndarray | None = None
    actual_fs = fs
    total_len = 0

    for ch in chunk_iter:
        actual_fs = float(ch["fs"])
        total_len = int(ch["total_samples"])
        w_start = int(ch["start_sample"])
        core_start = int(ch["core_start_sample"])
        core_end = int(ch["core_end_sample"])
        sig_win = ch["signal"]
        if not stream_meta and isinstance(ch.get("metadata"), dict):
            stream_meta = dict(ch["metadata"])

        if progress_callback and total_len > 0:
            frac = min(0.85, (core_end / total_len) * 0.85)
            progress_callback(
                frac,
                f"Streaming chunk {ch['chunk_index'] + 1} ({core_end / actual_fs:.0f}s / {total_len / actual_fs:.0f}s)...",
            )

        res_win = analyze_ecg(sig_win, fs=actual_fs, config=config)
        if preview_signal is None:
            preview_signal = res_win["clean_signal"][: min(len(res_win["clean_signal"]), int(actual_fs * 30))]
        sqi_list.append(res_win["sqi"])
        if res_win.get("twa"):
            twa_list.append(res_win["twa"])

        for b, cb in zip(res_win["beats"], res_win["classified_beats"], strict=False):
            global_r = int(b["r_peak_sample"]) + w_start
            if core_start <= global_r < core_end:
                if all_r_peaks and (global_r - all_r_peaks[-1]) < int(0.20 * actual_fs):
                    continue
                beat_idx = len(all_beats)
                rr_sec = (global_r - all_r_peaks[-1]) / actual_fs if all_r_peaks else float(b.get("rr_sec", 0.0))
                hr_bpm = 60.0 / rr_sec if rr_sec > 0 else np.nan
                qt_sec = float(b["qt_sec"])

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
                    "qtc": compute_qtc(qt_sec, rr_sec) if rr_sec > 0 else {},
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

    if all_classified:
        detect_rhythm_patterns(all_classified)
        for b_dict, cb_item in zip(all_beats, all_classified, strict=False):
            b_dict["rhythm_pattern"] = cb_item.rhythm_pattern.value
            b_dict["diagnostic_rationale"] = cb_item.diagnostic_rationale

    r_peaks_arr = np.array(all_r_peaks, dtype=np.int64)
    summary = summarize_beats(all_beats)

    counts: dict[str, int] = {}
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
        "pvc_percentage": round(pvc_cnt / tot_b * 100.0, 2) if tot_b > 0 else 0.0,
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

    stream_rr_arr = np.array([float(b.get("rr_sec", 0.0)) for b in all_beats], dtype=np.float64)
    stream_qt_arr = np.array([float(b.get("qt_sec", 0.0)) for b in all_beats], dtype=np.float64)
    qtvi_score, qtrr_metrics, hysteresis_metrics = _compute_repolarization_dynamics(
        stream_rr_arr, stream_qt_arr, config
    )

    hrv_metrics = _compute_hrv_from_beats(all_beats)
    hrt_metrics = compute_heart_rate_turbulence(all_classified, r_peaks_arr, fs=actual_fs)
    annotation_mgr = _build_annotation_manager(all_classified, author="AI_STREAM_DETECTOR")

    if progress_callback:
        progress_callback(1.00, f"Streamed analysis complete ({tot_b} beats across {rec_dur:.1f}s).")

    agg_sqi: dict[str, Any] = {}
    if sqi_list:
        agg_sqi = dict(sqi_list[0])
        for k in ("psqi", "bassqi", "ksqi", "ssqi", "snr_db"):
            vals = [float(s[k]) for s in sqi_list if k in s and isinstance(s[k], int | float)]
            if vals:
                agg_sqi[k] = round(float(np.mean(vals)), 4)

    peak_twa = None
    if twa_list:
        peak_twa = max(
            twa_list,
            key=lambda d: float(d.get("mma", {}).get("max_v_mma_uv", 0.0)),
        )

    return {
        "fs": actual_fs,
        "metadata": stream_meta,
        "clean_signal": preview_signal if preview_signal is not None else np.zeros(0, dtype=np.float32),
        "r_peaks": r_peaks_arr,
        "beats": all_beats,
        "classified_beats": all_classified,
        "ectopic_summary": ectopic_summary,
        "annotations": annotation_mgr,
        "events": [ev.to_dict() for ev in events],
        "summary": summary,
        "qtvi": qtvi_score,
        "qtrr": qtrr_metrics,
        "sqi": agg_sqi,
        "lead_voting": None,
        "hrv": hrv_metrics,
        "hrt": hrt_metrics,
        "twa": peak_twa,
        "hysteresis": hysteresis_metrics,
        "dispersion": None,
        "af_report": af_report.to_dict(),
        "trends": trends_report.to_dict(),
        "streamed": True,
        "total_duration_sec": rec_dur,
    }
