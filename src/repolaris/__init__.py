"""Repolaris: Biomedical signal processing for electrocardiogram, ventricular repolarization, and arrhythmia analysis."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_pkg_dir = Path(__file__).resolve().parent

# Ensure all detection submodules are registered cleanly on both standard and 9p filesystems
_det_dir = _pkg_dir / "detection"
for _sub in (
    "qrs",
    "q_onset",
    "t_end",
    "pulse_metrics",
    "qtvi",
    "qtrr",
    "sqi",
    "classifier",
    "annotations",
    "events",
    "dispersion",
    "twa",
    "hrt",
    "hrv",
    "hysteresis",
    "pipeline",
):
    _mod_name = f"repolaris.detection.{_sub}"
    if _mod_name not in sys.modules:
        _mod_path = _det_dir / f"{_sub}.py"
        if _mod_path.is_file():
            _spec = importlib.util.spec_from_file_location(_mod_name, _mod_path)
            if _spec and _spec.loader:
                _mod = importlib.util.module_from_spec(_spec)
                sys.modules[_mod_name] = _mod
                _spec.loader.exec_module(_mod)

from repolaris.config import ECGConfig, FilterConfig, DetectionConfig
from repolaris.detection.pipeline import analyze_ecg
from repolaris.detection.pulse_metrics import compute_qtc, summarize_beats
from repolaris.detection.qtvi import compute_qtvi, resample_berger, optimize_alpha
from repolaris.detection.qtrr import fit_qtrr_model, fit_all_qtrr_models, SUPPORTED_QTRR_MODELS, QTRR_MODEL_METADATA
from repolaris.detection.sqi import compute_psqi, compute_bassqi, compute_ksqi, compute_ssqi, evaluate_lead_quality, rank_leads_two_stage
from repolaris.detection.dispersion import calculate_qt_dispersion, resolve_lead_quorum
from repolaris.detection.twa import compute_spectral_twa, compute_mma_twa
from repolaris.detection.hrt import compute_heart_rate_turbulence
from repolaris.detection.hrv import (
    compute_time_domain_hrv,
    compute_frequency_domain_hrv,
    compute_nonlinear_hrv,
    compute_comprehensive_hrv,
)
from repolaris.detection.hysteresis import (
    compute_effective_rr_exponential,
    compute_effective_rr_linear,
    optimize_hysteresis_parameter,
)
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

__version__ = "0.6.1"
__all__ = [
    "ECGConfig",
    "FilterConfig",
    "DetectionConfig",
    "analyze_ecg",
    "compute_qtc",
    "summarize_beats",
    "compute_qtvi",
    "resample_berger",
    "optimize_alpha",
    "fit_qtrr_model",
    "fit_all_qtrr_models",
    "SUPPORTED_QTRR_MODELS",
    "QTRR_MODEL_METADATA",
    "compute_psqi",
    "compute_bassqi",
    "compute_ksqi",
    "compute_ssqi",
    "evaluate_lead_quality",
    "rank_leads_two_stage",
    "calculate_qt_dispersion",
    "resolve_lead_quorum",
    "compute_spectral_twa",
    "compute_mma_twa",
    "compute_heart_rate_turbulence",
    "compute_time_domain_hrv",
    "compute_frequency_domain_hrv",
    "compute_nonlinear_hrv",
    "compute_comprehensive_hrv",
    "compute_effective_rr_exponential",
    "compute_effective_rr_linear",
    "optimize_hysteresis_parameter",
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

# Auto-register in-process API and resources layers
_api_dir = _pkg_dir / "api"
_api_init = _api_dir / "__init__.py"
if _api_init.is_file() and "repolaris.api" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "repolaris.api",
        _api_init,
        submodule_search_locations=[str(_api_dir)],
    )
    if _spec and _spec.loader:
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules["repolaris.api"] = _mod
        _spec.loader.exec_module(_mod)

_res_dir = _pkg_dir / "resources"
_res_init = _res_dir / "__init__.py"
if _res_init.is_file() and "repolaris.resources" not in sys.modules:
    _spec_res = importlib.util.spec_from_file_location(
        "repolaris.resources",
        _res_init,
        submodule_search_locations=[str(_res_dir)],
    )
    if _spec_res and _spec_res.loader:
        _mod_res = importlib.util.module_from_spec(_spec_res)
        sys.modules["repolaris.resources"] = _mod_res
        _spec_res.loader.exec_module(_mod_res)
