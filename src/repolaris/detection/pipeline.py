"""Comprehensive ECG Analysis and Diagnostic Pipeline module.

Coordinates end-to-end processing of electrocardiogram recordings:
1. Signal conditioning (IIR Q=30 notch filter, 0.05-45 Hz Butterworth bandpass & two-stage median baseline removal).
2. Two-Stage Signal Quality Index (SQI) evaluation (Stage 1 Li et al. 2014 absolute gates + Stage 2 6-index pairwise voting).
3. QRS complex identification, R-peak localization, and high-rate Pacemaker Spike Guard (fs >= 1000 Hz).
4. Ventricular repolarization segmentation (Q-onset, J-point, and hybrid/tangent/Zhang-2006-area/threshold T-end fiducials).
5. Rate-corrected QT computation (Bazett, Fridericia, Framingham, Hodges formulas) & FDA CiPA sub-intervals (J-Tpeakc, Tpe, Tpe/QT).
6. AAMI EC57 & Patrick Hamilton (2002) OSEA abnormal beat classification (Normal, PVC, PAC, Fusion, Unknown).
7. Repetitive ectopic rhythm sequence detection (Bigeminy, Trigeminy, Couplets, VT runs).
8. Clinical events diary auto-detection (Critical QTc, Pauses, Tachycardia, Bradycardia, PVCs).
9. Berger QT Variability Index (QTVI) & Poincaré Short-Term/Long-Term QT Variability (STV_QT / LTV_QT).
10. Domain-guarded 10-model QT-RR restitution curve modeling (Pueyo et al., 2004) with EW/LW hysteresis compensation.
11. Unified annotation manager integration.
12. Autonomic & Spatial Repolarization Suite (HRV, HRT, PRSA DC/AC, TWA, Hysteresis, Multi-Lead QTd, 3D SVD T-Wave Morphology & Butterfly Median Beat).
13. Atrial Fibrillation / Flutter burden & episode detection (repolaris.detection.af_detector).
14. Ambulatory ST-Segment Level & Transient Ischemia Engine (repolaris.detection.st_segment).
15. AF-Gated P-Wave Delineation & AV Block Screening (repolaris.detection.p_wave).
16. ECG-Derived Respiration (EDR) & CVHR Sleep-Disordered Breathing Screening (repolaris.detection.edr).
17. Hourly Arrhythmia Trend Histograms & Holter Summary (repolaris.detection.trends).
18. Out-of-Core Streaming Holter Engine (analyze_ecg_stream).
"""

from __future__ import annotations

import ctypes
import gc

import contextlib
from collections.abc import Callable, Iterator, Sequence
from typing import Any

import numpy as np

from repolaris.config import ECGConfig, FilterConfig
from repolaris.detection.af_detector import detect_atrial_fibrillation
from repolaris.detection.annotations import AnnotationManager
from repolaris.detection.classifier import (
    BeatClass,
    BeatFeatures,
    ClassifiedBeat,
    RhythmPattern,
    classify_all_beats,
)
from repolaris.detection.dispersion import calculate_qt_dispersion
from repolaris.detection.circadian import analyze_circadian_repolarization
from repolaris.detection.edr import compute_ecg_derived_respiration
from repolaris.plugins import GLOBAL_PLUGIN_REGISTRY
from repolaris.detection.events import detect_clinical_events
from repolaris.detection.hamilton_classifier import HamiltonBeatClassifier
from repolaris.detection.hrt import compute_heart_rate_turbulence
from repolaris.detection.hrv import compute_comprehensive_hrv
from repolaris.detection.hysteresis import (
    compute_effective_rr_linear,
    optimize_hysteresis_parameter,
)
from repolaris.detection.p_wave import (
    analyze_p_waves_and_av_block,
    detect_pacemaker_spikes,
)
from repolaris.detection.prsa import compute_prsa_capacity
from repolaris.detection.pulse_metrics import (
    compute_cipa_metrics,
    compute_qtc,
    compute_stv_qt,
    summarize_beats,
)
from repolaris.detection.q_onset import detect_j_point, detect_q_onset
from repolaris.detection.qrs import _refine_r_peaks_polarity_locked, detect_r_peaks
from repolaris.detection.qtrr import fit_all_qtrr_models
from repolaris.detection.qtvi import compute_qtvi
from repolaris.detection.sqi import evaluate_lead_quality, rank_leads_two_stage
from repolaris.detection.st_segment import analyze_st_segment
from repolaris.detection.t_end import detect_t_end
from repolaris.detection.t_morphology import (
    compute_t_wave_morphology,
    evaluate_beat_t_morphology,
)
from repolaris.detection.trends import generate_hourly_trends
from repolaris.detection.twa import compute_mma_twa, compute_spectral_twa
from repolaris.preprocessing.baseline import remove_baseline_wander
from repolaris.preprocessing.filter import bandpass_filter, notch_filter



BEAT_FLAG_PACED = 1 << 0
BEAT_FLAG_T_NOTCHED = 1 << 1
BEAT_FLAG_T_BIPHASIC = 1 << 2
BEAT_FLAG_LOW_QUALITY_EPOCH = 1 << 3

_BEAT_CLASSES = (
    BeatClass.NORMAL,
    BeatClass.PVC,
    BeatClass.PAC,
    BeatClass.FUSION,
    BeatClass.UNKNOWN,
)
_BEAT_CLASS_TO_CODE = {bc.value: idx for idx, bc in enumerate(_BEAT_CLASSES)}

_RHYTHM_PATTERNS = (
    RhythmPattern.NORMAL_SINUS,
    RhythmPattern.BIGEMINY,
    RhythmPattern.TRIGEMINY,
    RhythmPattern.COUPLET,
    RhythmPattern.VT_RUN,
    RhythmPattern.TACHYCARDIA,
    RhythmPattern.BRADYCARDIA,
    RhythmPattern.PAUSE,
    RhythmPattern.ISOLATED_ECTOPIC,
)
_RHYTHM_TO_CODE = {rp.value: idx for idx, rp in enumerate(_RHYTHM_PATTERNS)}

BEAT_DTYPE = np.dtype([
    ("r_peak_sample", np.int64),
    ("q_onset_sample", np.int64),
    ("j_point_sample", np.int64),
    ("t_peak_sample", np.int64),
    ("t_end_sample", np.int64),
    ("rr_sec", np.float32),
    ("qt_sec", np.float32),
    ("st_level_uv", np.float32),
    ("st_j60_uv", np.float32),
    ("st_j80_uv", np.float32),
    ("st_slope_mv_per_sec", np.float32),
    ("t_asymmetry_ratio", np.float32),
    ("t_flatness_score", np.float32),
    ("classification_confidence", np.float32),
    ("qrs_duration_ms", np.float32),
    ("template_correlation", np.float32),
    ("beat_class_code", np.uint8),
    ("rhythm_code", np.uint8),
    ("active_lead_id", np.uint8),
    ("flags", np.uint8),
])


class BeatArrayProxy(Sequence):
    """Read-only lazy sequence over a compact 88-byte/beat NumPy structured array."""

    def __init__(
        self,
        arr: np.ndarray,
        fs: float,
        lead_names: list[str] | None = None,
        as_classified: bool = False,
    ) -> None:
        self._arr = arr
        self._fs = float(fs) if fs > 0 else 500.0
        self._lead_names = list(lead_names) if lead_names else []
        self._as_classified = as_classified

    @property
    def array(self) -> np.ndarray:
        return self._arr

    def __len__(self) -> int:
        return int(len(self._arr))

    def _materialize_dict(self, idx: int) -> dict[str, Any]:
        row = self._arr[idx]
        r_idx = int(row["r_peak_sample"])
        q_idx = int(row["q_onset_sample"])
        j_idx = int(row["j_point_sample"])
        tp_idx = int(row["t_peak_sample"])
        te_idx = int(row["t_end_sample"])
        rr = float(row["rr_sec"])
        qt = float(row["qt_sec"])
        flags = int(row["flags"])
        cipa = compute_cipa_metrics(q_idx, j_idx, tp_idx, te_idx, self._fs, rr)
        bc = _BEAT_CLASSES[min(int(row["beat_class_code"]), len(_BEAT_CLASSES) - 1)].value
        rp = _RHYTHM_PATTERNS[min(int(row["rhythm_code"]), len(_RHYTHM_PATTERNS) - 1)].value
        lid = int(row["active_lead_id"])
        lead_label = self._lead_names[lid] if 0 <= lid < len(self._lead_names) else f"Lead_{lid + 1}"
        return {
            "beat_index": idx,
            "r_peak_sample": r_idx,
            "time_sec": float(r_idx / self._fs),
            "q_onset_sample": q_idx,
            "j_point_sample": j_idx,
            "t_peak_sample": tp_idx,
            "t_end_sample": te_idx,
            "rr_sec": rr,
            "hr_bpm": float(60.0 / rr) if rr > 0 else np.nan,
            "qt_sec": qt,
            "qt_ms": float(qt * 1000.0),
            "jt_peak_ms": float(cipa["jt_peak_ms"]),
            "jt_peak_c_ms": float(cipa["jt_peak_c_ms"]),
            "tpe_ms": float(cipa["tpe_ms"]),
            "tpe_qt_ratio": float(cipa["tpe_qt_ratio"]),
            "t_asymmetry_ratio": float(row["t_asymmetry_ratio"]),
            "t_flatness_score": float(row["t_flatness_score"]),
            "t_is_notched": bool(flags & BEAT_FLAG_T_NOTCHED),
            "t_is_biphasic": bool(flags & BEAT_FLAG_T_BIPHASIC),
            "is_paced": bool(flags & BEAT_FLAG_PACED),
            "low_quality_epoch": bool(flags & BEAT_FLAG_LOW_QUALITY_EPOCH),
            "active_lead": lead_label,
            "active_lead_id": lid,
            "st_level_uv": float(row["st_level_uv"]),
            "st_j60_uv": float(row["st_j60_uv"]),
            "st_j80_uv": float(row["st_j80_uv"]),
            "st_slope_mv_per_sec": float(row["st_slope_mv_per_sec"]),
            "beat_class": bc,
            "rhythm_pattern": rp,
            "classification_confidence": float(row["classification_confidence"]),
            "diagnostic_rationale": f"{bc} ({rp})",
            "qrs_duration_ms": float(row["qrs_duration_ms"]),
            "template_correlation": float(row["template_correlation"]),
            "qtc": compute_qtc(qt, rr) if rr > 0 else {},
        }

    def _materialize_classified(self, idx: int) -> ClassifiedBeat:
        row = self._arr[idx]
        r_idx = int(row["r_peak_sample"])
        rr = float(row["rr_sec"])
        bc = _BEAT_CLASSES[min(int(row["beat_class_code"]), len(_BEAT_CLASSES) - 1)]
        rp = _RHYTHM_PATTERNS[min(int(row["rhythm_code"]), len(_RHYTHM_PATTERNS) - 1)]
        feats = BeatFeatures(
            pre_rr_sec=rr,
            post_rr_sec=rr,
            pre_rr_ratio=1.0,
            post_rr_ratio=1.0,
            compensatory_ratio=1.0,
            qrs_duration_ms=float(row["qrs_duration_ms"]),
            qrs_peak_to_peak_mv=1.0,
            qrs_energy=1.0,
            template_correlation=float(row["template_correlation"]),
            polarity=1,
        )
        return ClassifiedBeat(
            beat_index=idx,
            r_peak_sample=r_idx,
            time_sec=float(r_idx / self._fs),
            beat_class=bc,
            rhythm_pattern=rp,
            confidence=float(row["classification_confidence"]),
            features=feats,
            diagnostic_rationale=f"{bc.value} ({rp.value})",
        )

    def __getitem__(self, index: int | slice) -> Any:
        if isinstance(index, slice):
            indices = range(*index.indices(len(self._arr)))
            return [
                self._materialize_classified(i) if self._as_classified else self._materialize_dict(i)
                for i in indices
            ]
        idx = int(index)
        if idx < 0:
            idx += len(self._arr)
        if idx < 0 or idx >= len(self._arr):
            raise IndexError("BeatArrayProxy index out of range")
        return self._materialize_classified(idx) if self._as_classified else self._materialize_dict(idx)

    def __setitem__(self, index: Any, value: Any) -> None:
        raise TypeError("BeatArrayProxy is read-only; copy the materialized beat dict before mutating.")


def _condition_signal(raw_arr: np.ndarray, fs: float, fcfg: FilterConfig) -> np.ndarray:
    """Applies the shared clinical conditioning chain (Q=30 notch -> 0.05-45 Hz bandpass -> median baseline)."""
    notched = notch_filter(raw_arr, fs, freq=fcfg.notch_freq, q=fcfg.notch_quality)
    filtered = bandpass_filter(notched, fs, fcfg)
    return remove_baseline_wander(filtered, fs)


def _apply_stream_rhythm_patterns(beat_arr: np.ndarray) -> None:
    """Assigns rhythm pattern codes directly on the structured beat array without Python object allocation."""
    n = len(beat_arr)
    if n == 0:
        return
    pvc_code = _BEAT_CLASS_TO_CODE[BeatClass.PVC.value]
    pac_code = _BEAT_CLASS_TO_CODE[BeatClass.PAC.value]
    vt_code = _RHYTHM_TO_CODE[RhythmPattern.VT_RUN.value]
    couplet_code = _RHYTHM_TO_CODE[RhythmPattern.COUPLET.value]
    bigeminy_code = _RHYTHM_TO_CODE[RhythmPattern.BIGEMINY.value]
    trigeminy_code = _RHYTHM_TO_CODE[RhythmPattern.TRIGEMINY.value]
    pause_code = _RHYTHM_TO_CODE[RhythmPattern.PAUSE.value]
    isolated_code = _RHYTHM_TO_CODE[RhythmPattern.ISOLATED_ECTOPIC.value]

    bc = beat_arr["beat_class_code"]
    rr = beat_arr["rr_sec"]
    rc = beat_arr["rhythm_code"]
    rc[:] = _RHYTHM_TO_CODE[RhythmPattern.NORMAL_SINUS.value]

    i = 0
    while i < n:
        if bc[i] == pvc_code:
            run_end = i + 1
            while run_end < n and bc[run_end] == pvc_code:
                run_end += 1
            run_len = run_end - i
            if run_len >= 3:
                rc[i:run_end] = vt_code
                i = run_end
                continue
            if run_len == 2:
                rc[i:run_end] = couplet_code
                i = run_end
                continue
        i += 1

    for idx in range(n):
        if rc[idx] != 0:
            continue
        if rr[idx] >= 2.0:
            rc[idx] = pause_code
        elif bc[idx] in (pvc_code, pac_code):
            if idx >= 2 and bc[idx - 2] == bc[idx] and bc[idx - 1] == 0:
                rc[idx] = bigeminy_code
            elif idx >= 3 and bc[idx - 3] == bc[idx] and bc[idx - 1] == 0 and bc[idx - 2] == 0:
                rc[idx] = trigeminy_code
            else:
                rc[idx] = isolated_code


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
                "rr_raw_sec": rr_valid[:: max(1, len(rr_valid) // 5000)][:5000].tolist(),
                "rr_effective_sec": rr_used[:: max(1, len(rr_used) // 5000)][:5000].tolist(),
                "qt_sec": qt_valid[:: max(1, len(qt_valid) // 5000)][:5000].tolist(),
                "qt_ms": (qt_valid[:: max(1, len(qt_valid) // 5000)][:5000] * 1000.0).tolist(),
            }

    return qtvi_score, qtrr_metrics, hysteresis_metrics


def _build_annotation_manager(
    classified_beats: Sequence[ClassifiedBeat],
    author: str = "AI_DETECTOR",
    max_normal_annotations: int = 5000,
) -> AnnotationManager:
    """Populates a sparse AnnotationManager from classified beats."""
    mgr = AnnotationManager()
    normal_count = 0
    for cb in classified_beats:
        is_normal = cb.beat_class == BeatClass.NORMAL and cb.rhythm_pattern == RhythmPattern.NORMAL_SINUS
        if is_normal:
            if normal_count >= max_normal_annotations:
                continue
            normal_count += 1
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
    """Extracts non-paced normal NN intervals (or falls back to physiological RR intervals) and computes HRV."""
    nn_ms = [
        b["rr_sec"] * 1000.0
        for b in beats
        if b.get("beat_class") == "N" and not b.get("is_paced", False) and b.get("rr_sec", 0.0) > 0.2
    ]
    hrv_input = (
        nn_ms
        if len(nn_ms) >= 4
        else [b["rr_sec"] * 1000.0 for b in beats if not b.get("is_paced", False) and b.get("rr_sec", 0.0) > 0.2]
    )
    return compute_comprehensive_hrv(hrv_input) if len(hrv_input) >= 2 else None


def _sanitize_raw_signal(raw_signal: np.ndarray) -> tuple[np.ndarray, bool]:
    """Interpolates non-finite ADC glitches (NaN/Inf) and detects constant flatline/lead-off inputs."""
    arr = np.asarray(raw_signal, dtype=np.float64).ravel()
    if arr.size == 0:
        return arr, True
    finite_mask = np.isfinite(arr)
    if not np.all(finite_mask):
        arr = arr.copy()
        if not np.any(finite_mask):
            return np.zeros_like(arr), True
        idx = np.arange(arr.size)
        arr[~finite_mask] = np.interp(idx[~finite_mask], idx[finite_mask], arr[finite_mask])
    is_flatline = float(np.ptp(arr)) < 1e-9
    if is_flatline:
        arr = np.zeros_like(arr)
    else:
        arr = arr - float(np.median(arr))
    return arr, is_flatline


def analyze_ecg(
    raw_signal: np.ndarray,
    fs: float = 500.0,
    config: ECGConfig | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
    multi_lead_signals: np.ndarray | dict[str, np.ndarray] | None = None,
    lead_names: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    auto_select_lead: bool = False,
    hamilton_clf: HamiltonBeatClassifier | None = None,
) -> dict[str, Any]:
    """Executes the master diagnostic analysis pipeline on a raw ECG signal."""
    if config is None:
        config = ECGConfig(sampling_rate=fs)

    raw_signal, is_flatline = _sanitize_raw_signal(raw_signal)

    if progress_callback:
        progress_callback(0.10, "Preprocessing and baseline wander removal...")

    raw_lead_dict: dict[str, np.ndarray] | None = None
    conditioned_cache: dict[str, np.ndarray] | None = None
    if multi_lead_signals is not None:
        if isinstance(multi_lead_signals, dict):
            raw_lead_dict = {
                k: _sanitize_raw_signal(np.asarray(v, dtype=np.float64))[0]
                for k, v in multi_lead_signals.items()
            }
        else:
            ml_arr = np.asarray(multi_lead_signals, dtype=np.float64)
            if ml_arr.ndim == 1:
                ml_arr = ml_arr[None, :]
            ml_names = (
                lead_names
                if (lead_names and len(lead_names) == ml_arr.shape[0])
                else [f"Lead_{i + 1}" for i in range(ml_arr.shape[0])]
            )
            raw_lead_dict = {
                ml_names[i]: _sanitize_raw_signal(ml_arr[i])[0] for i in range(ml_arr.shape[0])
            }
        conditioned_cache = {
            k: _condition_signal(v, fs, config.filter_cfg) for k, v in raw_lead_dict.items()
        }

    clean_signal = _condition_signal(raw_signal, fs, config.filter_cfg)

    if progress_callback:
        progress_callback(0.25, "Evaluating lead signal quality (SQI)...")
    sqi_metrics = evaluate_lead_quality(raw_signal, fs, conditioned_signal=clean_signal)
    lead_voting = (
        rank_leads_two_stage(raw_lead_dict, fs=fs, conditioned_leads=conditioned_cache)
        if raw_lead_dict is not None and conditioned_cache is not None
        else None
    )

    qrs_lead: str | None = None
    delineation_lead: str | None = None
    low_t_amplitude_warning = False
    qrs_diag: dict[str, int] = {}

    if auto_select_lead and lead_voting is not None and conditioned_cache is not None and raw_lead_dict is not None:
        qrs_lead = (
            lead_voting["recommended_lead"]
            if lead_voting.get("quorum_passed")
            else lead_voting.get("fallback_lead")
        )
        if qrs_lead is not None and qrs_lead in conditioned_cache:
            raw_signal = raw_lead_dict[qrs_lead]
            clean_signal = conditioned_cache[qrs_lead]
            _, is_flatline = _sanitize_raw_signal(raw_signal)
            sqi_metrics = lead_voting["per_lead"].get(qrs_lead, sqi_metrics)

    if progress_callback:
        progress_callback(0.40, "Detecting QRS complexes, R-peaks, and high-rate pacing spikes...")
    r_peaks = (
        np.array([], dtype=int)
        if is_flatline
        else detect_r_peaks(
            clean_signal,
            fs,
            config.detection_cfg.refractory_period_ms,
            backend=getattr(config.detection_cfg, "qrs_backend", "adaptive_derivative"),
            t_wave_slope_ratio=getattr(config.detection_cfg, "t_wave_slope_ratio", 0.50),
            diagnostics_out=qrs_diag if getattr(config.detection_cfg, "collect_diagnostics", False) else None,
        )
    )

    if (
        auto_select_lead
        and qrs_lead is not None
        and lead_voting is not None
        and conditioned_cache is not None
        and raw_lead_dict is not None
        and len(r_peaks) > 0
    ):
        delineation_lead = qrs_lead

        def _median_post_r_t_ptp(sig_trace: np.ndarray, peaks: np.ndarray) -> float | None:
            ptps: list[float] = []
            n_sig = len(sig_trace)
            off_start = int(round(0.120 * fs))
            max_end = int(round(0.480 * fs))
            for idx_p, r_p in enumerate(peaks):
                if idx_p + 1 < len(peaks):
                    rr_s = int(peaks[idx_p + 1] - r_p)
                elif idx_p > 0:
                    rr_s = int(r_p - peaks[idx_p - 1])
                else:
                    rr_s = int(round(0.8 * fs))
                w_end_off = min(max_end, int(round(0.65 * rr_s)))
                if w_end_off <= off_start:
                    continue
                s0 = min(n_sig - 1, int(r_p) + off_start)
                s1 = min(n_sig, int(r_p) + w_end_off)
                if s1 > s0:
                    ptps.append(float(np.ptp(sig_trace[s0:s1])))
            return float(np.median(ptps)) if ptps else None

        qrs_t_ptp = _median_post_r_t_ptp(clean_signal, r_peaks)
        if qrs_t_ptp is None or qrs_t_ptp < 0.05:
            passing_sorted = sorted(
                lead_voting.get("passing_leads", []),
                key=lambda k: (
                    float(lead_voting["per_lead"][k].get("voting_index", -6.0)),
                    float(lead_voting["per_lead"][k].get("snr_db", -30.0)),
                ),
                reverse=True,
            )
            switched = False
            for cand_lead in passing_sorted:
                if cand_lead == qrs_lead:
                    continue
                cand_sig = conditioned_cache[cand_lead]
                snapped = _refine_r_peaks_polarity_locked(cand_sig, r_peaks.tolist(), fs)
                cand_t_ptp = _median_post_r_t_ptp(cand_sig, snapped)
                if cand_t_ptp is not None and cand_t_ptp >= 0.05:
                    delineation_lead = cand_lead
                    raw_signal = raw_lead_dict[cand_lead]
                    clean_signal = cand_sig
                    r_peaks = snapped
                    sqi_metrics = lead_voting["per_lead"].get(cand_lead, sqi_metrics)
                    switched = True
                    break
            if not switched:
                low_t_amplitude_warning = True
    pacemaker_report = detect_pacemaker_spikes(raw_signal, fs=fs, r_peaks=r_peaks, metadata=metadata)
    paced_set = set(pacemaker_report.get("paced_beat_indices", []))

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
        j_idx = detect_j_point(clean_signal, r_idx, fs, config.detection_cfg.q_search_window_ms)
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

        cipa = compute_cipa_metrics(q_idx, j_idx, t_peak_idx, t_end_idx, fs, rr)
        t_morph = evaluate_beat_t_morphology(clean_signal, j_idx, t_peak_idx, t_end_idx, fs)

        rr_list.append(rr)
        qt_list.append(qt)

        beats.append({
            "beat_index": i,
            "r_peak_sample": int(r_idx),
            "time_sec": float(r_idx / fs),
            "q_onset_sample": int(q_idx),
            "j_point_sample": int(j_idx),
            "t_peak_sample": int(t_peak_idx),
            "t_end_sample": int(t_end_idx),
            "rr_sec": float(rr),
            "hr_bpm": float(hr),
            "qt_sec": float(qt),
            "qt_ms": float(qt * 1000.0),
            "jt_peak_ms": float(cipa["jt_peak_ms"]),
            "jt_peak_c_ms": float(cipa["jt_peak_c_ms"]),
            "tpe_ms": float(cipa["tpe_ms"]),
            "tpe_qt_ratio": float(cipa["tpe_qt_ratio"]),
            "t_asymmetry_ratio": float(t_morph["asymmetry_ratio"]),
            "t_flatness_score": float(t_morph["flatness_score"]),
            "t_is_notched": bool(t_morph["is_notched"]),
            "t_is_biphasic": bool(t_morph["is_biphasic"]),
            "is_paced": bool(i in paced_set),
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
    reuse_hamilton = hamilton_clf is not None
    active_hamilton = hamilton_clf if reuse_hamilton else HamiltonBeatClassifier(fs=fs)
    hamilton_beats, hamilton_summary = active_hamilton.classify_recording(
        signal=clean_signal,
        r_peaks=r_peaks,
        q_onsets=q_onsets_arr,
        t_ends=t_ends_arr,
        reset_state=not reuse_hamilton,
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

    if progress_callback:
        progress_callback(0.85, "Evaluating AF burden, P-waves, ST ischemia, and hourly trends...")
    af_report = detect_atrial_fibrillation(r_peaks, fs=fs)
    af_dict = af_report.to_dict()

    st_metrics = analyze_st_segment(
        clean_signal,
        fs=fs,
        beats=beats,
        r_peaks=r_peaks,
        sqi_passed=bool(sqi_metrics.get("passed_absolute_gate", True)),
    )
    p_wave_metrics = analyze_p_waves_and_av_block(
        clean_signal,
        fs=fs,
        beats=beats,
        r_peaks=r_peaks,
        af_report=af_dict,
    )
    edr_metrics = compute_ecg_derived_respiration(
        clean_signal,
        fs=fs,
        r_peaks=r_peaks,
        beats=beats,
    )

    annotation_mgr = _build_annotation_manager(classified_beats, author="AI_DETECTOR")
    summary = summarize_beats(beats)
    if "pvc_percentage" not in ectopic_summary:
        _tot = int(ectopic_summary.get("total_beats", 0))
        _pvc = int(ectopic_summary.get("pvc_count", 0))
        ectopic_summary["pvc_percentage"] = round(_pvc / _tot * 100.0, 2) if _tot > 0 else 0.0
    summary["ectopic_summary"] = ectopic_summary
    events = detect_clinical_events(beats, fs=fs)

    rec_dur = float(len(clean_signal) / fs)
    circadian_metrics = analyze_circadian_repolarization(
        beats,
        metadata=metadata,
        total_duration_sec=rec_dur,
    )
    custom_biomarkers = GLOBAL_PLUGIN_REGISTRY.execute_biomarkers(clean_signal, fs, beats, summary)
    trends_report = generate_hourly_trends(
        classified_beats,
        events=[ev.to_dict() for ev in events],
        total_duration_sec=rec_dur,
        af_episodes=af_report.episodes,
    )

    if progress_callback:
        progress_callback(0.92, "Assessing repolarization lability, T-wave PCA, PRSA & autonomic metrics...")
    non_paced_beats = [b for b in beats if not b.get("is_paced", False)] or beats
    rr_arr = np.array([float(b["rr_sec"]) for b in non_paced_beats], dtype=np.float64)
    qt_arr = np.array([float(b["qt_sec"]) for b in non_paced_beats], dtype=np.float64)
    non_paced_classes = [str(b.get("beat_class", "N")) for b in non_paced_beats]

    qtvi_score, qtrr_metrics, hysteresis_metrics = _compute_repolarization_dynamics(rr_arr, qt_arr, config)
    stv_qt_metrics = compute_stv_qt([float(b["qt_ms"]) for b in non_paced_beats], beat_classes=non_paced_classes)
    prsa_metrics = compute_prsa_capacity(
        [float(b["rr_sec"]) * 1000.0 for b in non_paced_beats],
        beat_classes=non_paced_classes,
    )
    t_morphology_metrics = compute_t_wave_morphology(
        clean_signal,
        fs=fs,
        r_peaks=r_peaks,
        beats=beats,
        multi_lead_signals=multi_lead_signals,
        lead_names=lead_names,
        config=config.detection_cfg,
    )

    hrv_metrics = _compute_hrv_from_beats(beats)
    hrt_metrics = compute_heart_rate_turbulence(classified_beats, r_peaks, fs=fs)
    twa_metrics = {
        "spectral": compute_spectral_twa(clean_signal, fs, r_peaks, beat_classes=beat_class_codes),
        "mma": compute_mma_twa(clean_signal, fs, r_peaks),
    }
    dispersion_metrics = (
        calculate_qt_dispersion(
            raw_lead_dict if raw_lead_dict is not None else multi_lead_signals,
            fs=fs,
            lead_names=lead_names,
            config=config.detection_cfg,
            conditioned_leads=conditioned_cache,
            lead_voting=lead_voting,
            filter_cfg=config.filter_cfg,
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
        "stv_qt": stv_qt_metrics,
        "t_morphology": t_morphology_metrics,
        "butterfly": t_morphology_metrics["butterfly"],
        "prsa": prsa_metrics,
        "st_segment": st_metrics,
        "p_wave": p_wave_metrics,
        "edr": edr_metrics,
        "pacemaker": pacemaker_report,
        "circadian": circadian_metrics,
        "custom_biomarkers": custom_biomarkers,
        "qtrr": qtrr_metrics,
        "sqi": sqi_metrics,
        "lead_voting": lead_voting,
        "hrv": hrv_metrics,
        "hrt": hrt_metrics,
        "twa": twa_metrics,
        "hysteresis": hysteresis_metrics,
        "dispersion": dispersion_metrics,
        "af_report": af_dict,
        "trends": trends_report.to_dict(),
        **(
            {
                "diagnostics": {
                    "qrs_backend": getattr(config.detection_cfg, "qrs_backend", "adaptive_derivative"),
                    "refractory_period_ms": float(config.detection_cfg.refractory_period_ms),
                    "t_wave_slope_ratio": float(getattr(config.detection_cfg, "t_wave_slope_ratio", 0.50)),
                    "qrs_lead": qrs_lead,
                    "delineation_lead": delineation_lead,
                    "low_t_amplitude_warning": low_t_amplitude_warning,
                    "refractory_rejected": qrs_diag.get("refractory_rejected", 0),
                    "t_wave_rejected": qrs_diag.get("t_wave_rejected", 0),
                    "selection_basis": lead_voting.get("selection_basis") if lead_voting else None,
                    "failed_criteria": sqi_metrics.get("failed_criteria", []),
                }
            }
            if getattr(config.detection_cfg, "collect_diagnostics", False)
            else {}
        ),
    }


def _iter_array_chunks(
    signal_arr: np.ndarray,
    fs: float,
    chunk_duration_sec: float,
    overlap_sec: float,
) -> Iterator[dict[str, Any]]:
    """Yields overlapping chunks from an in-memory or memory-mapped 1D or 2D (n_leads, n_samples) array."""
    raw_arr = np.asarray(signal_arr, dtype=np.float32)
    total_samples = raw_arr.shape[1] if raw_arr.ndim == 2 else len(raw_arr)
    chunk_samples = max(1, int(round(chunk_duration_sec * fs)))
    overlap_samples = max(0, int(round(overlap_sec * fs)))

    c_start = 0
    c_idx = 0
    while c_start < total_samples:
        c_end = min(total_samples, c_start + chunk_samples)
        w_start = max(0, c_start - overlap_samples)
        w_end = min(total_samples, c_end + overlap_samples)
        sig_slice = raw_arr[:, w_start:w_end] if raw_arr.ndim == 2 else raw_arr[w_start:w_end]
        yield {
            "chunk_index": c_idx,
            "start_sample": w_start,
            "end_sample": w_end,
            "core_start_sample": c_start,
            "core_end_sample": c_end,
            "signal": sig_slice,
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
    chunk_duration_sec: float | None = None,
    overlap_sec: float = 5.0,
    config: ECGConfig | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Executes chunked out-of-core ECG analysis across continuous multi-hour Holter recordings."""
    from repolaris.io.ecg_loader import stream_ecg_chunks

    if config is None:
        config = ECGConfig(sampling_rate=fs)

    auto_lead_mode = isinstance(lead, str) and lead.strip().lower() == "auto"
    eff_chunk_sec = (
        float(chunk_duration_sec)
        if chunk_duration_sec is not None
        else (60.0 if auto_lead_mode else 300.0)
    )
    loader_lead: str | int = "all" if auto_lead_mode else lead

    chunk_iter = (
        _iter_array_chunks(signal_or_path, fs, eff_chunk_sec, overlap_sec)
        if isinstance(signal_or_path, np.ndarray)
        else stream_ecg_chunks(
            signal_or_path,
            lead_name_or_index=loader_lead,
            chunk_duration_sec=eff_chunk_sec,
            overlap_sec=overlap_sec,
        )
    )

    capacity = 4096
    beat_buf = np.empty(capacity, dtype=BEAT_DTYPE)
    n_beats_total = 0

    sqi_list: list[dict[str, Any]] = []
    twa_list: list[dict[str, Any]] = []
    edr_list: list[dict[str, Any]] = []
    p_wave_list: list[dict[str, Any]] = []
    pacemaker_spikes_global: list[int] = []
    first_t_morph: dict[str, Any] | None = None
    stream_meta: dict[str, Any] = {}
    preview_signal: np.ndarray | None = None
    actual_fs = fs
    total_len = 0
    last_r_peak = -1

    active_lead_idx = 0
    consec_bad_chunks = 0
    stream_hamilton_clf: HamiltonBeatClassifier | None = None
    stream_hamilton_lead: int | None = None
    stream_hamilton_fs: float | None = None
    lead_names_list: list[str] = []

    for ch in chunk_iter:
        actual_fs = float(ch["fs"])
        total_len = int(ch["total_samples"])
        w_start = int(ch["start_sample"])
        core_start = int(ch["core_start_sample"])
        core_end = int(ch["core_end_sample"])
        sig_win = ch["signal"]
        if not stream_meta and isinstance(ch.get("metadata"), dict):
            stream_meta = dict(ch["metadata"])
            if isinstance(stream_meta.get("lead_names"), list):
                lead_names_list = [str(n) for n in stream_meta["lead_names"]]

        if progress_callback and total_len > 0:
            frac = min(0.85, (core_end / total_len) * 0.85)
            progress_callback(
                frac,
                f"Streaming chunk {ch['chunk_index'] + 1} ({core_end / actual_fs:.0f}s / {total_len / actual_fs:.0f}s)...",
            )

        low_quality_epoch = False
        if auto_lead_mode and isinstance(sig_win, np.ndarray) and sig_win.ndim == 2:
            n_ch_leads = sig_win.shape[0]
            if not lead_names_list or len(lead_names_list) != n_ch_leads:
                lead_names_list = [f"Lead_{i + 1}" for i in range(n_ch_leads)]
            if active_lead_idx >= n_ch_leads:
                active_lead_idx = 0

            cond_chunk = {
                lead_names_list[i]: _condition_signal(sig_win[i].astype(np.float64), actual_fs, config.filter_cfg)
                for i in range(n_ch_leads)
            }
            raw_chunk = {lead_names_list[i]: sig_win[i] for i in range(n_ch_leads)}
            chunk_vote = rank_leads_two_stage(raw_chunk, fs=actual_fs, conditioned_leads=cond_chunk)
            act_name = lead_names_list[active_lead_idx]
            act_sqi = chunk_vote["per_lead"].get(act_name, {})
            is_flat_sat = (
                float(act_sqi.get("non_flat_ratio", 0.0)) < 0.80
                or float(np.std(sig_win[active_lead_idx])) <= 1e-6
            )
            passed_act = bool(act_sqi.get("passed_absolute_gate", False))

            if chunk_vote["quorum_passed"]:
                if is_flat_sat:
                    best_name = chunk_vote["recommended_lead"]
                    active_lead_idx = lead_names_list.index(best_name)
                    consec_bad_chunks = 0
                elif not passed_act:
                    consec_bad_chunks += 1
                    if consec_bad_chunks >= 2:
                        best_name = chunk_vote["recommended_lead"]
                        active_lead_idx = lead_names_list.index(best_name)
                        consec_bad_chunks = 0
                else:
                    consec_bad_chunks = 0
            else:
                low_quality_epoch = True
                consec_bad_chunks += 1

            sig_1d = sig_win[active_lead_idx]
        else:
            sig_1d = sig_win[0] if (isinstance(sig_win, np.ndarray) and sig_win.ndim == 2) else sig_win

        if (
            stream_hamilton_clf is None
            or stream_hamilton_lead != active_lead_idx
            or stream_hamilton_fs != actual_fs
        ):
            stream_hamilton_clf = HamiltonBeatClassifier(fs=actual_fs)
            stream_hamilton_lead = active_lead_idx
            stream_hamilton_fs = actual_fs
        res_win = analyze_ecg(
            sig_1d,
            fs=actual_fs,
            config=config,
            metadata=stream_meta,
            hamilton_clf=stream_hamilton_clf,
        )
        if preview_signal is None:
            preview_signal = res_win["clean_signal"][: min(len(res_win["clean_signal"]), int(actual_fs * 30))].copy()
        if first_t_morph is None and isinstance(res_win.get("t_morphology"), dict):
            first_t_morph = dict(res_win["t_morphology"])
        sqi_list.append(res_win["sqi"])
        if res_win.get("twa"):
            twa_list.append(res_win["twa"])
        if not edr_list and res_win.get("edr") and res_win["edr"].get("valid"):
            edr_list.append(res_win["edr"])
        if not p_wave_list and res_win.get("p_wave"):
            p_wave_list.append(res_win["p_wave"])
        pm_win = res_win.get("pacemaker") or {}
        for sp in pm_win.get("spike_samples", []):
            g_sp = int(sp) + w_start
            if core_start <= g_sp < core_end:
                pacemaker_spikes_global.append(g_sp)

        for b, cb in zip(res_win["beats"], res_win["classified_beats"], strict=False):
            global_r = int(b["r_peak_sample"]) + w_start
            if core_start <= global_r < core_end:
                if last_r_peak >= 0 and (global_r - last_r_peak) < int(0.20 * actual_fs):
                    continue
                if n_beats_total >= capacity:
                    new_cap = capacity * 2
                    new_buf = np.empty(new_cap, dtype=BEAT_DTYPE)
                    new_buf[:n_beats_total] = beat_buf[:n_beats_total]
                    beat_buf = new_buf
                    capacity = new_cap

                rr_sec = (global_r - last_r_peak) / actual_fs if last_r_peak >= 0 else float(b.get("rr_sec", 0.0))
                row = beat_buf[n_beats_total]
                row["r_peak_sample"] = global_r
                row["q_onset_sample"] = int(b.get("q_onset_sample", -1)) + w_start
                row["j_point_sample"] = int(b.get("j_point_sample", b["r_peak_sample"] + int(0.04 * actual_fs))) + w_start
                row["t_peak_sample"] = int(b.get("t_peak_sample", -1)) + w_start
                row["t_end_sample"] = int(b.get("t_end_sample", -1)) + w_start
                row["rr_sec"] = float(rr_sec)
                row["qt_sec"] = float(b.get("qt_sec", 0.0))
                row["st_level_uv"] = float(b.get("st_level_uv", 0.0))
                row["st_j60_uv"] = float(b.get("st_j60_uv", 0.0))
                row["st_j80_uv"] = float(b.get("st_j80_uv", 0.0))
                row["st_slope_mv_per_sec"] = float(b.get("st_slope_mv_per_sec", 0.0))
                row["t_asymmetry_ratio"] = float(b.get("t_asymmetry_ratio", 0.0))
                row["t_flatness_score"] = float(b.get("t_flatness_score", 0.0))
                row["classification_confidence"] = float(cb.confidence)
                row["qrs_duration_ms"] = float(cb.features.qrs_duration_ms)
                row["template_correlation"] = float(cb.features.template_correlation)
                row["beat_class_code"] = _BEAT_CLASS_TO_CODE.get(cb.beat_class.value, 0)
                row["rhythm_code"] = _RHYTHM_TO_CODE.get(cb.rhythm_pattern.value, 0)
                row["active_lead_id"] = active_lead_idx & 0xFF
                flags = 0
                if b.get("is_paced", False):
                    flags |= BEAT_FLAG_PACED
                if b.get("t_is_notched", False):
                    flags |= BEAT_FLAG_T_NOTCHED
                if b.get("t_is_biphasic", False):
                    flags |= BEAT_FLAG_T_BIPHASIC
                if low_quality_epoch:
                    flags |= BEAT_FLAG_LOW_QUALITY_EPOCH
                row["flags"] = flags

                last_r_peak = global_r
                n_beats_total += 1
        del res_win

    beat_arr = np.ascontiguousarray(beat_buf[:n_beats_total])
    del beat_buf
    gc.collect()
    with contextlib.suppress(Exception):
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    if n_beats_total > 0:
        _apply_stream_rhythm_patterns(beat_arr)

    all_beats = BeatArrayProxy(beat_arr, fs=actual_fs, lead_names=lead_names_list, as_classified=False)
    all_classified = BeatArrayProxy(beat_arr, fs=actual_fs, lead_names=lead_names_list, as_classified=True)
    r_peaks_arr = beat_arr["r_peak_sample"].copy() if n_beats_total > 0 else np.array([], dtype=np.int64)

    summary = summarize_beats(all_beats)

    counts: dict[str, int] = {}
    rhythm_counts: dict[str, int] = {}
    if n_beats_total > 0:
        u_bc, u_bc_cnt = np.unique(beat_arr["beat_class_code"], return_counts=True)
        for code_i, cnt_i in zip(u_bc, u_bc_cnt, strict=False):
            counts[_BEAT_CLASSES[int(code_i)].value] = int(cnt_i)
        u_rc, u_rc_cnt = np.unique(beat_arr["rhythm_code"], return_counts=True)
        for code_i, cnt_i in zip(u_rc, u_rc_cnt, strict=False):
            rhythm_counts[_RHYTHM_PATTERNS[int(code_i)].value] = int(cnt_i)

    pvc_cnt = counts.get("V", 0)
    pac_cnt = counts.get("S", 0)
    tot_b = n_beats_total
    ectopic_summary = {
        "total_beats": tot_b,
        "counts": counts,
        "pvc_count": pvc_cnt,
        "pac_count": pac_cnt,
        "pvc_percentage": round(pvc_cnt / tot_b * 100.0, 2) if tot_b > 0 else 0.0,
        "ectopic_burden_pct": round((pvc_cnt + pac_cnt) / tot_b * 100.0, 2) if tot_b > 0 else 0.0,
        "algorithm": "Hamilton_OSEA_2002_Stream",
        "rhythm_patterns": rhythm_counts,
        "vt_runs": rhythm_counts.get("VT_RUN", 0),
        "couplet_episodes": rhythm_counts.get("COUPLET", 0),
        "af_stabilized": False,
        "template_cluster_count": len(counts),
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

    if n_beats_total > 0:
        non_paced_mask = (beat_arr["flags"] & BEAT_FLAG_PACED) == 0
        if not np.any(non_paced_mask):
            non_paced_mask = np.ones(n_beats_total, dtype=bool)
        stream_rr_arr = beat_arr["rr_sec"][non_paced_mask].astype(np.float64)
        stream_qt_arr = beat_arr["qt_sec"][non_paced_mask].astype(np.float64)
        np_codes = beat_arr["beat_class_code"][non_paced_mask]
        non_paced_classes = [_BEAT_CLASSES[int(c)].value for c in np_codes]
    else:
        stream_rr_arr = np.array([], dtype=np.float64)
        stream_qt_arr = np.array([], dtype=np.float64)
        non_paced_classes = []

    qtvi_score, qtrr_metrics, hysteresis_metrics = _compute_repolarization_dynamics(
        stream_rr_arr, stream_qt_arr, config
    )
    stv_qt_metrics = compute_stv_qt(
        (stream_qt_arr * 1000.0).tolist(),
        beat_classes=non_paced_classes,
    )
    prsa_metrics = compute_prsa_capacity(
        (stream_rr_arr * 1000.0).tolist(),
        beat_classes=non_paced_classes,
    )

    if n_beats_total > 0:
        st_uvs = beat_arr["st_level_uv"]
        st_j60s = beat_arr["st_j60_uv"]
        st_j80s = beat_arr["st_j80_uv"]
        st_slopes = beat_arr["st_slope_mv_per_sec"]
        st_stream_summary = {
            "mean_st_j60_uv": round(float(np.mean(st_j60s)), 2),
            "mean_st_j80_uv": round(float(np.mean(st_j80s)), 2),
            "mean_st_level_uv": round(float(np.mean(st_uvs)), 2),
            "max_st_elevation_uv": round(max(0.0, float(np.max(st_uvs))), 2),
            "max_st_depression_uv": round(min(0.0, float(np.min(st_uvs))), 2),
            "mean_st_slope_mv_per_sec": round(float(np.mean(st_slopes)), 3),
            "num_episodes": 0,
            "episodes": [],
            "ischemic_burden_pct": 0.0,
            "hourly_st_trends": [],
            "verdict": "NORMAL",
        }
    else:
        st_stream_summary = {
            "mean_st_j60_uv": 0.0,
            "mean_st_j80_uv": 0.0,
            "mean_st_level_uv": 0.0,
            "max_st_elevation_uv": 0.0,
            "max_st_depression_uv": 0.0,
            "mean_st_slope_mv_per_sec": 0.0,
            "num_episodes": 0,
            "episodes": [],
            "ischemic_burden_pct": 0.0,
            "hourly_st_trends": [],
            "verdict": "NORMAL",
        }

    p_wave_agg = p_wave_list[0] if p_wave_list else {
        "af_gated": False,
        "p_wave_detection_rate_pct": 0.0,
        "mean_pr_ms": 0.0,
        "max_pr_ms": 0.0,
        "mean_p_duration_ms": 0.0,
        "first_degree_av_block": False,
        "second_degree_av_block": "NONE",
        "dropped_p_wave_count": 0,
        "av_conduction_verdict": "NORMAL_AV_CONDUCTION",
    }
    edr_agg = edr_list[0] if edr_list else {
        "valid": False,
        "respiratory_rate_brpm": 0.0,
        "respiratory_freq_hz": 0.0,
        "edr_time_sec": [],
        "edr_waveform": [],
        "cvhr_power_ratio": 0.0,
        "apnea_screening_verdict": "INSUFFICIENT_DURATION",
    }
    paced_indices = np.flatnonzero((beat_arr["flags"] & BEAT_FLAG_PACED) != 0).tolist() if n_beats_total > 0 else []
    pm_meta = str(stream_meta.get("pacemaker", "NO")).strip().upper()
    meta_paced = pm_meta not in ("", "NO", "NONE", "FALSE", "0", "ABSENT", "UNSPECIFIED")
    pacemaker_agg = {
        "raw_spike_detection_enabled": bool(actual_fs >= 1000.0),
        "gating_reason": (
            f"Active high-rate slew guard (fs={actual_fs:.0f} Hz >= 1000 Hz)"
            if actual_fs >= 1000.0
            else f"Sampling rate {actual_fs:.0f} Hz < 1000 Hz minimum Nyquist pacing spike guard"
        ),
        "metadata_pacemaker_flag": meta_paced,
        "metadata_pacemaker_mode": pm_meta if meta_paced else "NO",
        "spike_samples": pacemaker_spikes_global,
        "spike_count": len(pacemaker_spikes_global),
        "paced_beat_indices": paced_indices,
        "paced_beat_count": len(paced_indices),
        "pacing_detected": bool(meta_paced or len(pacemaker_spikes_global) > 0),
    }

    circadian_stream = analyze_circadian_repolarization(
        all_beats,
        metadata=stream_meta,
        total_duration_sec=rec_dur,
    )
    preview_sig_arr = preview_signal if preview_signal is not None else np.zeros(0, dtype=np.float32)
    custom_biomarkers_stream = GLOBAL_PLUGIN_REGISTRY.execute_biomarkers(
        preview_sig_arr,
        actual_fs,
        all_beats,
        summary,
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
        "stv_qt": stv_qt_metrics,
        "t_morphology": first_t_morph,
        "butterfly": first_t_morph.get("butterfly") if first_t_morph else None,
        "prsa": prsa_metrics,
        "st_segment": st_stream_summary,
        "p_wave": p_wave_agg,
        "edr": edr_agg,
        "pacemaker": pacemaker_agg,
        "circadian": circadian_stream,
        "custom_biomarkers": custom_biomarkers_stream,
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
