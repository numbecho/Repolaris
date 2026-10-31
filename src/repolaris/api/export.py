"""Repolaris In-Process Export Service API.

Handles case container serialization, de-identification, and .pecg packaging.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from repolaris.io.pecg_format import save_pecg


class ExportAPI:
    """In-process controller for study container export and archival."""

    @staticmethod
    def export_study_pecg(
        filepath: str | Path,
        signals: np.ndarray,
        sampling_rate: float,
        lead_names: list[str],
        patient_info: dict[str, Any] | None = None,
        annotations: dict[str, Any] | None = None,
        events: list[Any] | None = None,
        compression: str = "zstd",
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> str:
        """Packages multi-lead signals, calibrated fiducials, and metadata into a .pecg archive."""
        return save_pecg(
            filepath=filepath,
            signals=signals,
            sampling_rate=sampling_rate,
            lead_names=lead_names,
            patient_info=patient_info,
            annotations=annotations,
            events=events,
            compression=compression,
            progress_callback=progress_callback,
        )
