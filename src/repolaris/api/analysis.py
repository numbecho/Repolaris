"""Repolaris In-Process Analysis Service API.

Orchestrates beat classification, repolarization interval calculations, and autonomic risk triage.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
        config: ECGConfig | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> dict[str, Any]:
        """Executes full electrophysiology analysis pipeline on an ECG signal."""
        return analyze_ecg(signal, fs=fs, config=config, progress_callback=progress_callback)

    @staticmethod
    def calculate_qtc(raw_qt_sec: float, rr_sec: float) -> dict[str, float]:
        """Calculates Bazett, Fridericia, and Framingham rate-corrected QTc intervals in milliseconds."""
        return compute_qtc(raw_qt_sec, rr_sec)
