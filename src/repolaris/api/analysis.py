"""Repolaris In-Process Analysis Service API.

Orchestrates beat classification, repolarization interval calculations, and autonomic risk triage.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import numpy as np

from repolaris.config import ECGConfig
from repolaris.detection.pipeline import analyze_ecg
from repolaris.detection.pulse_metrics import compute_qtc


class AnalysisAPI:
    """In-process controller for ECG signal processing and repolarization analytics."""

    @staticmethod
    def analyze_signal(
        signal: np.ndarray,
        fs: float = 500.0,
        config: Optional[ECGConfig] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """Executes full electrophysiology analysis pipeline on an ECG signal."""
        return analyze_ecg(signal, fs=fs, config=config, progress_callback=progress_callback)

    @staticmethod
    def calculate_qtc(raw_qt_sec: float, rr_sec: float) -> Dict[str, float]:
        """Calculates Bazett, Fridericia, and Framingham rate-corrected QTc intervals in milliseconds."""
        return compute_qtc(raw_qt_sec, rr_sec)
