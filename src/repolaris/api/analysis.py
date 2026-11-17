"""Repolaris In-Process Analysis Service API.

Orchestrates beat classification, repolarization interval calculations, spatial QT dispersion,
microvolt T-wave alternans, heart rate turbulence, HRV, hysteresis, AF burden, hourly trends,
and autonomic risk triage.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
import numpy as np

from repolaris.config import ECGConfig, DetectionConfig
from repolaris.detection.pipeline import analyze_ecg, analyze_ecg_stream
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
from repolaris.detection.qtrr import fit_all_qtrr_models
from repolaris.detection.sqi import rank_leads_two_stage
from repolaris.detection.af_detector import detect_atrial_fibrillation
from repolaris.detection.trends import generate_hourly_trends


class AnalysisAPI:
    """In-process controller for ECG signal processing and repolarization analytics."""

    @staticmethod
    def analyze_signal(
        signal: np.ndarray,
        fs: float = 500.0,
        config: ECGConfig | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        multi_lead_signals: np.ndarray | dict[str, np.ndarray] | None = None,
        lead_names: list[str] | None = None,
    ) -> dict[str, Any]:
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
    def calculate_qtc(raw_qt_sec: float, rr_sec: float) -> dict[str, float]:
        """Calculates Bazett, Fridericia, Framingham, and Hodges rate-corrected QTc intervals in ms."""
        return compute_qtc(raw_qt_sec, rr_sec)

    @staticmethod
    def evaluate_qtrr_models(
        rr_intervals_sec: np.ndarray | list[float],
        qt_intervals_sec: np.ndarray | list[float],
        preferred_model: str = "linear",
        hysteresis_mode: str = "exponential",
        optimal_lambda: float = 0.08,
    ) -> dict[str, Any]:
        """Evaluates all 10 Pueyo (2004) QT-RR restitution models under the selected hysteresis mode."""
        rr_raw = np.asarray(rr_intervals_sec, dtype=np.float64)
        qt_arr = np.asarray(qt_intervals_sec, dtype=np.float64)

        valid_mask = (rr_raw > 0.20) & (qt_arr > 0.05) & np.isfinite(rr_raw) & np.isfinite(qt_arr)
        if np.sum(valid_mask) >= 3:
            rr_raw = rr_raw[valid_mask]
            qt_arr = qt_arr[valid_mask]

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
        lead_signals: np.ndarray | dict[str, np.ndarray],
        fs: float = 500.0,
        lead_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Executes Two-Stage SQA Lead Ranking (Stage 1 absolute gate + Stage 2 6-index pairwise voting)."""
        return rank_leads_two_stage(lead_signals, fs=fs, lead_names=lead_names)

    @staticmethod
    def analyze_dispersion(
        lead_signals: np.ndarray | dict[str, np.ndarray],
        fs: float = 500.0,
        lead_names: list[str] | None = None,
        config: DetectionConfig | None = None,
    ) -> dict[str, Any] | None:
        """Computes multi-lead spatial QT dispersion (QTd) and transmural dispersion (Tpe,d)."""
        return calculate_qt_dispersion(lead_signals, fs=fs, lead_names=lead_names, config=config)

    @staticmethod
    def analyze_twa(
        lead_signal: np.ndarray,
        fs: float,
        r_peaks: np.ndarray,
        beat_classes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Computes dual Spectral FFT and Modified Moving Average (MMA) T-wave alternans."""
        return {
            "spectral": compute_spectral_twa(lead_signal, fs, r_peaks, beat_classes=beat_classes),
            "mma": compute_mma_twa(lead_signal, fs, r_peaks),
        }

    @staticmethod
    def analyze_hrt(
        classified_beats: list[Any],
        r_peaks: np.ndarray,
        fs: float = 500.0,
    ) -> dict[str, Any]:
        """Computes Heart Rate Turbulence (TO, TS, and ISHNE risk category)."""
        return compute_heart_rate_turbulence(classified_beats, r_peaks, fs=fs)

    @staticmethod
    def analyze_hrv(
        nn_intervals_ms: np.ndarray | list[float],
        fs_resample: float = 4.0,
    ) -> dict[str, Any]:
        """Computes comprehensive Time-Domain, Welch Frequency-Domain, and Non-Linear HRV."""
        return compute_comprehensive_hrv(nn_intervals_ms, fs_resample=fs_resample)

    @staticmethod
    def analyze_hysteresis(
        qt_intervals_sec: np.ndarray | list[float],
        rr_intervals_sec: np.ndarray | list[float],
        model_type: str = "linear",
    ) -> dict[str, Any]:
        """Optimizes multi-beat QT-RR memory hysteresis (EW/LW profiles, lambda*, t90)."""
        return optimize_hysteresis_parameter(qt_intervals_sec, rr_intervals_sec, model_type=model_type)

    @staticmethod
    def detect_af(
        r_peaks: np.ndarray,
        fs: float = 500.0,
        window_beats: int = 32,
        min_episode_duration_sec: float = 30.0,
    ) -> dict[str, Any]:
        """Detects sustained Atrial Fibrillation / Flutter episodes and returns burden dictionary."""
        return detect_atrial_fibrillation(
            r_peaks,
            fs=fs,
            window_beats=window_beats,
            min_episode_duration_sec=min_episode_duration_sec,
        ).to_dict()

    @staticmethod
    def compute_hourly_trends(
        classified_beats: list[Any],
        events: list[dict[str, Any]] | None = None,
        total_duration_sec: float | None = None,
        bin_size_sec: float = 3600.0,
        af_episodes: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Aggregates classified beats, events, and AF episodes into 1-hour Holter trend bins."""
        return generate_hourly_trends(
            classified_beats,
            events=events,
            total_duration_sec=total_duration_sec,
            bin_size_sec=bin_size_sec,
            af_episodes=af_episodes,
        ).to_dict()

    @staticmethod
    def analyze_stream(
        signal_or_path: np.ndarray | str,
        fs: float = 500.0,
        lead: str | int = 0,
        chunk_duration_sec: float = 300.0,
        overlap_sec: float = 5.0,
        config: ECGConfig | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> dict[str, Any]:
        """Executes bounded-memory chunked Holter analysis across a long recording or file."""
        return analyze_ecg_stream(
            signal_or_path,
            fs=fs,
            lead=lead,
            chunk_duration_sec=chunk_duration_sec,
            overlap_sec=overlap_sec,
            config=config,
            progress_callback=progress_callback,
        )
