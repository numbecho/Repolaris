"""Repolaris In-Process Export Service API.

Handles case container serialization, de-identification, and .pecg packaging.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
import numpy as np

from repolaris.io.pecg_format import save_pecg


class ExportAPI:
    """In-process controller for study container export and archival."""

    @staticmethod
    def export_study_pecg(
        filepath: Union[str, Path],
        signals: np.ndarray,
        sampling_rate: float,
        lead_names: List[str],
        patient_info: Optional[Dict[str, Any]] = None,
        annotations: Optional[Dict[str, Any]] = None,
        events: Optional[List[Any]] = None,
        compression: str = "zstd",
        progress_callback: Optional[Callable[[float, str], None]] = None
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
            progress_callback=progress_callback
        )
