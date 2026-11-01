"""Repolaris: Biomedical signal processing for electrocardiogram, ventricular repolarization, and arrhythmia analysis."""

from __future__ import annotations

from repolaris.config import ECGConfig, FilterConfig, DetectionConfig
from repolaris.detection.pipeline import analyze_ecg
from repolaris.detection.qtvi import compute_qtvi, resample_berger
from repolaris.detection.qtrr import fit_qtrr_model
from repolaris.detection.sqi import compute_psqi, compute_bassqi, evaluate_lead_quality
from repolaris.detection.classifier import (
    BeatClass,
    RhythmPattern,
    BeatFeatures,
    ClassifiedBeat,
    classify_all_beats,
    classify_heartbeat,
)
from repolaris.detection.annotations import ECGAnnotation, AnnotationManager
from repolaris.io.ecg_loader import load_ecg_file, load_ecg_dataset
from repolaris.io.pecg_format import save_pecg, load_pecg
from repolaris.io.e3c_reader import read_e3c

__version__ = "0.5.0"
__all__ = [
    "ECGConfig",
    "FilterConfig",
    "DetectionConfig",
    "analyze_ecg",
    "compute_qtvi",
    "resample_berger",
    "fit_qtrr_model",
    "compute_psqi",
    "compute_bassqi",
    "evaluate_lead_quality",
    "BeatClass",
    "RhythmPattern",
    "BeatFeatures",
    "ClassifiedBeat",
    "classify_all_beats",
    "classify_heartbeat",
    "ECGAnnotation",
    "AnnotationManager",
    "load_ecg_file",
    "load_ecg_dataset",
    "save_pecg",
    "load_pecg",
    "read_e3c",
]

# Auto-register in-process API layer
import sys
from pathlib import Path
import importlib.util

_api_dir = Path(__file__).parent / "api"
_api_init = _api_dir / "__init__.py"
if _api_init.is_file() and "repolaris.api" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "repolaris.api",
        _api_init,
        submodule_search_locations=[str(_api_dir)]
    )
    if _spec and _spec.loader:
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules["repolaris.api"] = _mod
        _spec.loader.exec_module(_mod)

_res_dir = Path(__file__).parent / "resources"
_res_init = _res_dir / "__init__.py"
if _res_init.is_file() and "repolaris.resources" not in sys.modules:
    _spec_res = importlib.util.spec_from_file_location(
        "repolaris.resources",
        _res_init,
        submodule_search_locations=[str(_res_dir)]
    )
    if _spec_res and _spec_res.loader:
        _mod_res = importlib.util.module_from_spec(_spec_res)
        sys.modules["repolaris.resources"] = _mod_res
        _spec_res.loader.exec_module(_mod_res)
