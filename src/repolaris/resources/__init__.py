"""Repolaris UI Resources and Precompiled Presentation Assets."""

from __future__ import annotations

import sys
from pathlib import Path
import importlib.util

# Handle 9p filesystem dynamic loading if needed
_res_dir = Path(__file__).resolve().parent

try:
    from repolaris.resources.compile_ui import compile_ui, get_ui_path
except ImportError:
    _comp_path = _res_dir / "compile_ui.py"
    if _comp_path.exists():
        _spec = importlib.util.spec_from_file_location("repolaris.resources.compile_ui", _comp_path)
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            sys.modules["repolaris.resources.compile_ui"] = _mod
            _spec.loader.exec_module(_mod)
            compile_ui = _mod.compile_ui
            get_ui_path = _mod.get_ui_path

try:
    from repolaris.resources.ui_app import Ui_MainWindow
except ImportError:
    _ui_py = _res_dir / "ui_app.py"
    if _ui_py.exists():
        _spec = importlib.util.spec_from_file_location("repolaris.resources.ui_app", _ui_py)
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            sys.modules["repolaris.resources.ui_app"] = _mod
            _spec.loader.exec_module(_mod)
            Ui_MainWindow = _mod.Ui_MainWindow

__all__ = ["Ui_MainWindow", "compile_ui", "get_ui_path"]
