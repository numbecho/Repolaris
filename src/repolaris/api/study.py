"""Repolaris In-Process Study Service API.

Handles study loading, format negotiation, ingestion boundary validation, and lifecycle.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import numpy as np

from repolaris.io.ecg_loader import load_ecg_dataset
from repolaris.utils.signal import generate_synthetic_ecg


class StudyAPI:
    """In-process controller for clinical ECG study ingestion and metadata management."""

    @staticmethod
    def load_study_file(
        file_path: str,
        lead: int | str = 0,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> tuple[np.ndarray, float]:
        """Loads a single lead trace and sampling rate from any supported ECG file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"ECG study file not found: {file_path}")
        signals, fs, _ = load_ecg_dataset(file_path, progress_callback=progress_callback)
        if isinstance(lead, int):
            lead_names = list(signals.keys())
            idx = min(lead, len(lead_names) - 1)
            return signals[lead_names[idx]], fs
        if lead in signals:
            return signals[lead], fs
        return next(iter(signals.values())), fs

    @staticmethod
    def load_study_dataset(
        file_path: str, progress_callback: Callable[[float, str], None] | None = None
    ) -> tuple[dict[str, np.ndarray], float, dict[str, Any]]:
        """Loads multi-lead signals and extracted metadata from any supported ECG container."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"ECG study file not found: {file_path}")
        return load_ecg_dataset(file_path, progress_callback=progress_callback)

    @staticmethod
    def generate_demo_study(
        duration_sec: float = 10.0,
        fs: float = 500.0,
        heart_rate_bpm: float = 72.0,
        noise_std: float = 0.02,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generates a standardized synthetic benchmark ECG study."""
        if progress_callback:
            progress_callback(
                0.20,
                f"Synthesizing {duration_sec:.1f}s benchmark rhythm ({heart_rate_bpm:.0f} BPM)...",
            )
        time_vec, lead2, true_r = generate_synthetic_ecg(
            duration_sec=duration_sec, fs=fs, heart_rate_bpm=heart_rate_bpm, noise_std=noise_std
        )
        if progress_callback:
            progress_callback(1.00, f"Benchmark rhythm generated ({len(true_r)} QRS complexes).")
        return time_vec, lead2, true_r
