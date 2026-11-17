"""Repolaris: Biomedical signal processing for electrocardiogram, ventricular repolarization, and arrhythmia analysis."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

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
    "hamilton_classifier",
    "af_detector",
    "trends",
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

from repolaris.config import DetectionConfig, ECGConfig, FilterConfig  # noqa: E402
from repolaris.detection.af_detector import (  # noqa: E402
    AFBurdenReport,
    AFEpisode,
    detect_atrial_fibrillation,
)
from repolaris.detection.annotations import AnnotationManager, ECGAnnotation  # noqa: E402
from repolaris.detection.classifier import (  # noqa: E402
    BeatClass,
    BeatFeatures,
    ClassifiedBeat,
    RhythmPattern,
    classify_all_beats,
    classify_heartbeat,
)
from repolaris.detection.dispersion import (  # noqa: E402
    calculate_qt_dispersion,
    resolve_lead_quorum,
)
from repolaris.detection.hamilton_classifier import HamiltonBeatClassifier  # noqa: E402
from repolaris.detection.hrt import compute_heart_rate_turbulence  # noqa: E402
from repolaris.detection.hrv import (  # noqa: E402
    compute_comprehensive_hrv,
    compute_frequency_domain_hrv,
    compute_nonlinear_hrv,
    compute_time_domain_hrv,
)
from repolaris.detection.hysteresis import (  # noqa: E402
    compute_effective_rr_exponential,
    compute_effective_rr_linear,
    optimize_hysteresis_parameter,
)
from repolaris.detection.pipeline import analyze_ecg, analyze_ecg_stream  # noqa: E402
from repolaris.detection.pulse_metrics import compute_qtc, summarize_beats  # noqa: E402
from repolaris.detection.qtrr import (  # noqa: E402
    QTRR_MODEL_METADATA,
    SUPPORTED_QTRR_MODELS,
    fit_all_qtrr_models,
    fit_qtrr_model,
)
from repolaris.detection.qtvi import (  # noqa: E402
    compute_qtvi,
    optimize_alpha,
    resample_berger,
)
from repolaris.detection.sqi import (  # noqa: E402
    compute_bassqi,
    compute_ksqi,
    compute_psqi,
    compute_ssqi,
    evaluate_lead_quality,
    rank_leads_two_stage,
)
from repolaris.detection.trends import (  # noqa: E402
    HolterTrendReport,
    HourlyTrendBin,
    generate_hourly_trends,
)
from repolaris.detection.twa import compute_mma_twa, compute_spectral_twa  # noqa: E402
from repolaris.io.dicom_reader import is_dicom_file, read_dicom_waveform  # noqa: E402
from repolaris.io.e3c_reader import read_e3c  # noqa: E402
from repolaris.io.ecg_loader import (  # noqa: E402
    SignalBuffer,
    load_ecg_dataset,
    load_ecg_file,
    open_ecg_buffer,
    sniff_ecg_format,
    stream_ecg_chunks,
)
from repolaris.io.hl7_reader import is_hl7_xml, read_hl7_aecg  # noqa: E402
from repolaris.io.pdf_report import generate_clinical_pdf_report  # noqa: E402
from repolaris.io.pecg_format import load_pecg, save_pecg  # noqa: E402
from repolaris.io.scp_reader import is_scp_file, read_scp_ecg  # noqa: E402

__version__ = "0.8.1"
__all__ = [
    "AFBurdenReport",
    "AFEpisode",
    "AnnotationManager",
    "BeatClass",
    "BeatFeatures",
    "ClassifiedBeat",
    "DetectionConfig",
    "ECGAnnotation",
    "ECGConfig",
    "FilterConfig",
    "HamiltonBeatClassifier",
    "HolterTrendReport",
    "HourlyTrendBin",
    "QTRR_MODEL_METADATA",
    "RhythmPattern",
    "SUPPORTED_QTRR_MODELS",
    "SignalBuffer",
    "analyze_ecg",
    "analyze_ecg_stream",
    "calculate_qt_dispersion",
    "classify_all_beats",
    "classify_heartbeat",
    "compute_bassqi",
    "compute_comprehensive_hrv",
    "compute_effective_rr_exponential",
    "compute_effective_rr_linear",
    "compute_frequency_domain_hrv",
    "compute_heart_rate_turbulence",
    "compute_ksqi",
    "compute_mma_twa",
    "compute_nonlinear_hrv",
    "compute_psqi",
    "compute_qtc",
    "compute_qtvi",
    "compute_spectral_twa",
    "compute_ssqi",
    "compute_time_domain_hrv",
    "detect_atrial_fibrillation",
    "evaluate_lead_quality",
    "fit_all_qtrr_models",
    "fit_qtrr_model",
    "generate_clinical_pdf_report",
    "generate_hourly_trends",
    "is_dicom_file",
    "is_hl7_xml",
    "is_scp_file",
    "load_ecg_dataset",
    "load_ecg_file",
    "load_pecg",
    "open_ecg_buffer",
    "optimize_alpha",
    "optimize_hysteresis_parameter",
    "rank_leads_two_stage",
    "read_dicom_waveform",
    "read_e3c",
    "read_hl7_aecg",
    "read_scp_ecg",
    "resample_berger",
    "resolve_lead_quorum",
    "save_pecg",
    "sniff_ecg_format",
    "stream_ecg_chunks",
    "summarize_beats",
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
