"""Repolaris In-Process Analysis Service API.

Orchestrates beat classification, repolarization interval calculations, spatial QT dispersion,
microvolt T-wave alternans, heart rate turbulence, HRV, hysteresis, and autonomic risk triage.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Union
import numpy as np

from repolaris.config import ECGConfig, DetectionConfig
from repolaris.detection.pipeline import analyze_ecg
from repolaris.detection.pulse_metrics import compute_qtc
from repolaris.detection.dispersion import calculate_qt_dispersion
from repolaris.detection.twa import compute_spectral_twa, compute_mma_twa
from repolaris.detection.hrt import compute_heart_rate_turbulence
from repolaris.detection.hrv import compute_comprehensive_hrv
from repolaris.detection.hysteresis import (
    compute_effective_rr_exponential,
    compute_effective_rr_linear,
    optimize_hysteresis_parameter,
)
from repolaris.detection.qtrr import fit_all_qtrr_models, fit_qtrr_model
from repolaris.detection.sqi import rank_leads_two_stage


class AnalysisAPI:
    """In-process controller for ECG signal processing and repolarization analytics."""

    @staticmethod
    def analyze_signal(
        signal: np.ndarray,
        fs: float = 500.0,
        config: Optional[ECGConfig] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        multi_lead_signals: Optional[Union[np.ndarray, Dict[str, np.ndarray]]] = None,
        lead_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Executes full electrophysiology analysis pipeline on an ECG signal."""
        return analyze_ecg(
            signal,
            fs=fs,
            config=config,
            progress_callback=progress_callback,
            multi_lead_signals=multi_lead_signals,
            lead_names=lead_names,
        )

    @staticmethod
    def calculate_qtc(raw_qt_sec: float, rr_sec: float) -> Dict[str, float]:
        """Calculates Bazett, Fridericia, Framingham, and Hodges rate-corrected QTc intervals in ms."""
        return compute_qtc(raw_qt_sec, rr_sec)

    @staticmethod
    def evaluate_qtrr_models(
        rr_intervals_sec: Union[np.ndarray, List[float]],
        qt_intervals_sec: Union[np.ndarray, List[float]],
        preferred_model: str = "linear",
        hysteresis_mode: str = "exponential",
        optimal_lambda: float = 0.08,
    ) -> Dict[str, Any]:
        """Evaluates all 10 Pueyo (2004) QT-RR restitution models under the selected hysteresis mode."""
        rr_raw = np.asarray(rr_intervals_sec, dtype=np.float64)
        qt_arr = np.asarray(qt_intervals_sec, dtype=np.float64)

        if hysteresis_mode == "exponential":
            rr_used = compute_effective_rr_exponential(rr_raw, lambda_param=optimal_lambda)
        elif hysteresis_mode == "linear":
            rr_used = compute_effective_rr_linear(rr_raw, memory_beats=25)
        else:
            rr_used = rr_raw

        res = fit_all_qtrr_models(rr_used, qt_arr, preferred_model=preferred_model)
        res["rr_raw_sec"] = rr_raw
        res["rr_used_sec"] = rr_used
        res["qt_sec"] = qt_arr
        res["qt_ms"] = qt_arr * 1000.0
        res["hysteresis_mode"] = hysteresis_mode
        return res

    @staticmethod
    def rank_leads(
        lead_signals: Union[np.ndarray, Dict[str, np.ndarray]],
        fs: float = 500.0,
        lead_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Executes Two-Stage SQA Lead Ranking (Stage 1 absolute gate + Stage 2 6-index pairwise voting)."""
        return rank_leads_two_stage(lead_signals, fs=fs, lead_names=lead_names)

    @staticmethod
    def analyze_dispersion(
        lead_signals: Union[np.ndarray, Dict[str, np.ndarray]],
        fs: float = 500.0,
        lead_names: Optional[List[str]] = None,
        config: Optional[DetectionConfig] = None,
    ) -> Optional[Dict[str, Any]]:
        """Computes multi-lead spatial QT dispersion (QTd) and transmural dispersion (Tpe,d)."""
        return calculate_qt_dispersion(lead_signals, fs=fs, lead_names=lead_names, config=config)

    @staticmethod
    def analyze_twa(
        lead_signal: np.ndarray,
        fs: float,
        r_peaks: np.ndarray,
        beat_classes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Computes dual Spectral FFT and Modified Moving Average (MMA) T-wave alternans."""
        return {
            "spectral": compute_spectral_twa(lead_signal, fs, r_peaks, beat_classes=beat_classes),
            "mma": compute_mma_twa(lead_signal, fs, r_peaks),
        }

    @staticmethod
    def analyze_hrt(
        classified_beats: List[Any],
        r_peaks: np.ndarray,
        fs: float = 500.0,
    ) -> Dict[str, Any]:
        """Computes Heart Rate Turbulence (TO, TS, and ISHNE risk category)."""
        return compute_heart_rate_turbulence(classified_beats, r_peaks, fs=fs)

    @staticmethod
    def analyze_hrv(
        nn_intervals_ms: Union[np.ndarray, List[float]],
        fs_resample: float = 4.0,
    ) -> Dict[str, Any]:
        """Computes comprehensive Time-Domain, Welch Frequency-Domain, and Non-Linear HRV."""
        return compute_comprehensive_hrv(nn_intervals_ms, fs_resample=fs_resample)

    @staticmethod
    def analyze_hysteresis(
        qt_intervals_sec: Union[np.ndarray, List[float]],
        rr_intervals_sec: Union[np.ndarray, List[float]],
        model_type: str = "linear",
    ) -> Dict[str, Any]:
        """Optimizes multi-beat QT-RR memory hysteresis (EW/LW profiles, lambda*, t90)."""
        return optimize_hysteresis_parameter(qt_intervals_sec, rr_intervals_sec, model_type=model_type)
