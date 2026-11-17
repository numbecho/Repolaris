"""Repolaris In-Process Export Service API.

Handles case container serialization, de-identification, .pecg packaging, and clinical PDF reporting.
"""

from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
from typing import Any
import numpy as np

from repolaris.io.pecg_format import save_pecg
from repolaris.io.pdf_report import generate_clinical_pdf_report


class ExportAPI:
    """In-process controller for study container export, archival, and printable PDF reports."""

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

    @staticmethod
    def export_clinical_pdf(
        filepath: str | Path,
        analysis_results: dict[str, Any],
        patient_metadata: dict[str, Any] | None = None,
        fs: float = 500.0,
        lead_name: str = "Lead II",
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> str:
        """Generates a printable multi-page clinical PDF report."""
        return generate_clinical_pdf_report(
            filepath=filepath,
            analysis_results=analysis_results,
            patient_metadata=patient_metadata,
            fs=fs,
            lead_name=lead_name,
            progress_callback=progress_callback,
        )
