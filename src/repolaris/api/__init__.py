"""Repolaris In-Process Service API Layer.

Exposes unified controllers for study loading, analysis, and export consumed by CLI and GUI clients.
"""

from __future__ import annotations

import sys
from pathlib import Path
import importlib.util

def _load_submodule(sub_name: str):
    full_name = f"repolaris.api.{sub_name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    path = Path(__file__).parent / f"{sub_name}.py"
    spec = importlib.util.spec_from_file_location(full_name, path)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = mod
        spec.loader.exec_module(mod)
        return mod
    raise ImportError(f"Could not load {full_name} from {path}")

_study_mod = _load_submodule("study")
_analysis_mod = _load_submodule("analysis")
_export_mod = _load_submodule("export")

StudyAPI = _study_mod.StudyAPI
AnalysisAPI = _analysis_mod.AnalysisAPI
ExportAPI = _export_mod.ExportAPI

__all__ = ["StudyAPI", "AnalysisAPI", "ExportAPI"]
