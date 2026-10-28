"""PyECG: Biomedical signal processing for electrocardiogram, ventricular repolarization, and arrhythmia analysis."""

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
from repolaris.io.mat_reader import load_mat_ecg, save_mat_ecg
from repolaris.io.e3c_reader import read_e3c

__version__ = "0.2.0"
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
    "load_mat_ecg",
    "save_mat_ecg",
    "read_e3c",
]
