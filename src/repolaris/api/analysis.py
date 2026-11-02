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
from repolaris.detection.hysteresis import optimize_hysteresis_parameter


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
