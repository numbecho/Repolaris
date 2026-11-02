"""Repolaris Electrophysiological Detection and Autonomic Analysis Subpackage."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_det_dir = Path(__file__).resolve().parent

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
