"""Repolaris Workstation GUI — Human-Centered Clinical Electrocardiogram Analyzer with i18n support.

Supports multi-language real-time switching:
- en: English (Default)
- es: Español (Spanish)
- fr: Français (French)
- de: Deutsch (German)
- pt: Português (Portuguese)

All source code remains strictly in English. UI text is managed via repolaris.i18n.
"""

from __future__ import annotations

from collections.abc import Callable
import contextlib
import logging
import os
import sys
import threading
from typing import Any

logger = logging.getLogger(__name__)

import numpy as np

from repolaris.api import AnalysisAPI, ExportAPI, StudyAPI
from repolaris.config import DetectionConfig, ECGConfig, FilterConfig
from repolaris.detection.annotations import AnnotationManager
from repolaris.detection.classifier import BeatClass, detect_rhythm_patterns
from repolaris.detection.pulse_metrics import summarize_beats
from repolaris.detection.qtrr import QTRR_MODEL_METADATA, SUPPORTED_QTRR_MODELS
from repolaris.i18n import SUPPORTED_LANGUAGES, get_current_locale, set_locale, tr

try:
    from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
    from PyQt6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QKeySequence
    from PyQt6.QtWidgets import (
        QApplication,
        QButtonGroup,
        QComboBox,
        QDialog,
        QFileDialog,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QInputDialog,
        QLabel,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
    import pyqtgraph as pg
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

    class _SignalMock:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def connect(self, slot: Any) -> None:
            pass

        def emit(self, *args: Any, **kwargs: Any) -> None:
            pass

        def blockSignals(self, b: bool) -> None:
            pass

    def pyqtSignal(*args: Any, **kwargs: Any) -> Any:
        return _SignalMock()

    class _QMockMeta(type):
        def __getattr__(cls, name: str) -> Any:
            mock = _QMock()
            setattr(cls, name, mock)
            return mock

    class _QMock(metaclass=_QMockMeta):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._text = args[0] if (args and isinstance(args[0], str)) else ""
            self._val = 0
            self._hidden = True
            self._tabs: list[Any] = []
            self._items: list[Any] = []
            self._curr_idx: int = 0
            self._rows: int = args[0] if (len(args) >= 2 and isinstance(args[0], int)) else 0
            self._cols: int = args[1] if (len(args) >= 2 and isinstance(args[1], int)) else 0
            self._cells: dict[Any, Any] = {}
            self.triggered = _SignalMock()
            self.toggled = _SignalMock()
            self.clicked = _SignalMock()
            self.currentIndexChanged = _SignalMock()
            self.currentTextChanged = _SignalMock()
            self.cellClicked = _SignalMock()
            self.cellDoubleClicked = _SignalMock()

        def setText(self, text: str) -> None:
            self._text = str(text)

        def text(self) -> str:
            return self._text

        def setValue(self, val: int) -> None:
            self._val = val

        def value(self) -> int:
            return self._val

        def show(self) -> None:
            self._hidden = False

        def hide(self) -> None:
            self._hidden = True

        def isHidden(self) -> bool:
            return self._hidden

        def width(self) -> int:
            return 800

        def height(self) -> int:
            return 400

        def blockSignals(self, b: bool) -> None:
            pass

        def addTab(self, widget: Any, label: str = "") -> None:
            self._tabs.append((widget, label))

        def setTabText(self, idx: int, label: str) -> None:
            if 0 <= idx < len(self._tabs):
                self._tabs[idx] = (self._tabs[idx][0], label)

        def addItem(self, label: Any, user_data: Any = None) -> None:
            self._items.append((str(label), user_data))

        def clear(self) -> None:
            self._items.clear()
            self._cells.clear()
            self._rows = 0

        def setCurrentIndex(self, idx: int) -> None:
            self._curr_idx = int(idx)

        def currentIndex(self) -> int:
            return self._curr_idx

        def currentText(self) -> str:
            if 0 <= self._curr_idx < len(self._items):
                return self._items[self._curr_idx][0]
            return ""

        def currentData(self) -> Any:
            if 0 <= self._curr_idx < len(self._items):
                return self._items[self._curr_idx][1]
            return None

        def itemData(self, idx: int) -> Any:
            if 0 <= idx < len(self._items):
                return self._items[idx][1]
            return None

        def setRowCount(self, rows: int) -> None:
            self._rows = int(rows)

        def rowCount(self) -> int:
            return self._rows

        def setItem(self, row: int, col: int, item: Any) -> None:
            self._cells[(int(row), int(col))] = item

        def item(self, row: int, col: int) -> Any:
            return self._cells.get((int(row), int(col)))

        def count(self) -> int:
            return len(self._tabs) if self._tabs else len(self._items)

        def __getattr__(self, name: str) -> Any:
            mock = _QMock()
            setattr(self, name, mock)
            return mock

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            return _QMock()

    class _QWindowBaseMock:
        """Strict headless base class for QMainWindow/QDialog without catch-all __getattr__."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._menubar = _QMock()
            self._statusbar = _QMock()
            self._central = None
            self._style = ""
            self._title = ""

        def setWindowTitle(self, title: str) -> None:
            self._title = str(title)

        def windowTitle(self) -> str:
            return self._title

        def resize(self, w: int, h: int) -> None:
            pass

        def setMinimumSize(self, w: int, h: int) -> None:
            pass

        def setMinimumWidth(self, w: int) -> None:
            pass

        def setCentralWidget(self, w: Any) -> None:
            self._central = w

        def centralWidget(self) -> Any:
            return self._central

        def menuBar(self) -> Any:
            return self._menubar

        def statusBar(self) -> Any:
            return self._statusbar

        def setStatusBar(self, sb: Any) -> None:
            self._statusbar = sb

        def setStyleSheet(self, qss: str) -> None:
            self._style = str(qss)

        def styleSheet(self) -> str:
            return self._style

        def show(self) -> None:
            pass

        def close(self) -> None:
            pass

        def exec(self) -> int:
            return 0

        def accept(self) -> None:
            pass

        def reject(self) -> None:
            pass

        def addAction(self, action: Any) -> None:
            pass

        def closeEvent(self, event: Any) -> None:
            pass

    QMainWindow = _QWindowBaseMock  # type: ignore
    QWidget = _QMock  # type: ignore
    QVBoxLayout = _QMock  # type: ignore
    QHBoxLayout = _QMock  # type: ignore
    QPushButton = _QMock  # type: ignore
    QLabel = _QMock  # type: ignore
    QFileDialog = _QMock  # type: ignore
    QTableWidget = _QMock  # type: ignore
    QTableWidgetItem = _QMock  # type: ignore
    QHeaderView = _QMock  # type: ignore
    QGroupBox = _QMock  # type: ignore
    QMessageBox = _QMock  # type: ignore
    QTabWidget = _QMock  # type: ignore
    QInputDialog = _QMock  # type: ignore
    QSplitter = _QMock  # type: ignore
    QComboBox = _QMock  # type: ignore
    QFrame = _QMock  # type: ignore
    QScrollArea = _QMock  # type: ignore
    QDialog = _QWindowBaseMock  # type: ignore
    QButtonGroup = _QMock  # type: ignore
    QMenuBar = _QMock  # type: ignore
    QMenu = _QMock  # type: ignore
    QProgressBar = _QMock  # type: ignore
    QStatusBar = _QMock  # type: ignore
    QAction = _QMock  # type: ignore
    QColor = _QMock  # type: ignore
    QActionGroup = _QMock  # type: ignore
    QDesktopServices = _QMock  # type: ignore
    QApplication = _QMock  # type: ignore

    class _QThreadMock:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._interruption_requested = False

        def start(self) -> None:
            pass

        def quit(self) -> None:
            pass

        def wait(self, msecs: int = -1) -> bool:
            return True

        def isRunning(self) -> bool:
            return False

        def requestInterruption(self) -> None:
            self._interruption_requested = True

        def isInterruptionRequested(self) -> bool:
            return self._interruption_requested

    QThread = _QThreadMock  # type: ignore

    class _QKeySequenceMock:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    QKeySequence = _QKeySequenceMock  # type: ignore

    class _QUrlMock:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        @staticmethod
        def fromLocalFile(path: str) -> Any:
            return _QUrlMock(path)

    QUrl = _QUrlMock  # type: ignore

    class _QtMock:
        class Key:
            Key_Left = 0x01000012
            Key_Right = 0x01000014
            Key_N = 0x4E
            Key_V = 0x56
            Key_S = 0x53
            Key_F = 0x46
            Key_Q = 0x51

        class Orientation:
            Horizontal = 1
            Vertical = 2

        class PenStyle:
            SolidLine = 1
            DashLine = 2
            DotLine = 3
            DashDotLine = 4

    Qt = _QtMock  # type: ignore
    pg = _QMock()  # type: ignore




class BackgroundTaskWorker(QThread):
    """Executes long-running API tasks in a dedicated background worker thread with cooperative cancellation."""
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, task_func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = dict(kwargs)
        self._is_cancelled = False

    def cancel(self) -> None:
        """Marks this worker as superseded/cancelled and requests thread interruption."""
        self._is_cancelled = True
        if hasattr(self, "requestInterruption"):
            with contextlib.suppress(Exception):
                self.requestInterruption()

    def is_cancelled(self) -> bool:
        """Returns True if cancellation or thread interruption was requested."""
        if self._is_cancelled:
            return True
        if hasattr(self, "isInterruptionRequested"):
            with contextlib.suppress(Exception):
                return bool(self.isInterruptionRequested())
        return False

    def run(self) -> None:
        task_name = getattr(self.task_func, "__name__", str(self.task_func))
        thread_name = threading.current_thread().name
        logger.debug("Starting BackgroundTaskWorker '%s' on thread %s", task_name, thread_name)
        try:
            def _callback(pct: float, msg: str) -> None:
                if not self.is_cancelled():
                    self.progress.emit(pct, msg)

            if self.is_cancelled():
                logger.debug("Skipping cancelled BackgroundTaskWorker '%s' before execution", task_name)
                return

            call_kwargs = dict(self.kwargs)
            call_kwargs["progress_callback"] = _callback
            result = self.task_func(*self.args, **call_kwargs)
            if not self.is_cancelled():
                logger.debug("Completed BackgroundTaskWorker '%s' on thread %s", task_name, thread_name)
                self.finished.emit(result)
            else:
                logger.info("Discarding stale result from superseded worker '%s'", task_name)
        except Exception as exc:
            logger.exception("Error in BackgroundTaskWorker '%s': %s", task_name, exc)
            if not self.is_cancelled():
                self.error.emit(str(exc))

# -----------------------------------------------------------------------------
# THEME SPECIFICATIONS (Dark, Light, Color Blind Friendly)
# -----------------------------------------------------------------------------
THEMES: dict[str, dict[str, Any]] = {
    "dark": {
        "id": "dark",
        "name_key": "theme_dark",
        "desc_key": "theme_dark_desc",
        "plot_bg": "#13151f",
        "axis_pen": "#475569",
        "axis_text": "#94a3b8",
        "grid_alpha": 0.18,
        "curve_color": "#38bdf8",
        "curve_width": 1.6,
        "r_peak_brush": "#f87171",
        "r_peak_symbol": "t1",
        "q_caliper_color": "#fbbf24",
        "t_caliper_color": "#c084fc",
        "caliper_label_fill": (26, 30, 44, 200),
        "qss": """
            QMainWindow { background-color: #0f111a; }
            QWidget { background-color: #0f111a; color: #cbd5e1; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 10pt; }

            QFrame#topBar { background-color: #1a1e2e; border: 1px solid #2e3650; border-radius: 8px; padding: 6px 12px; }
            QLabel#appTitle { font-size: 14pt; font-weight: bold; color: #60a5fa; }
            QLabel#fileBadge { background-color: #262c42; color: #94a3b8; border-radius: 4px; padding: 4px 8px; font-size: 9.5pt; font-weight: 500; }

            QPushButton { background-color: #242c44; border: 1px solid #3b4668; border-radius: 6px; padding: 6px 14px; font-weight: 600; color: #e2e8f0; }
            QPushButton:hover { background-color: #313b5c; border-color: #60a5fa; color: #ffffff; }
            QPushButton#btnPrimary { background-color: #2563eb; border: 1px solid #3b82f6; color: #ffffff; }
            QPushButton#btnPrimary:hover { background-color: #1d4ed8; }
            QPushButton#btnSecondary { background-color: #0d9488; border: 1px solid #14b8a6; color: #ffffff; }
            QPushButton#btnSecondary:hover { background-color: #0f766e; }
            QPushButton#btnSettings { background-color: #1e293b; border: 1px solid #334155; color: #94a3b8; }
            QPushButton#btnSettings:hover { background-color: #334155; color: #f8fafc; border-color: #60a5fa; }

            QComboBox { background-color: #242c44; border: 1px solid #3b4668; border-radius: 6px; padding: 5px 10px; color: #e2e8f0; font-weight: 600; min-width: 120px; }
            QComboBox:hover { border-color: #60a5fa; }
            QComboBox QAbstractItemView { background-color: #1a1e2e; selection-background-color: #2563eb; color: #f8fafc; border: 1px solid #3b4668; }

            QFrame#kpiCard { background-color: #1a1e2e; border: 1px solid #2e3650; border-radius: 8px; padding: 10px; }
            QLabel#kpiTitle { font-size: 8.5pt; font-weight: bold; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
            QLabel#kpiValue { font-size: 16pt; font-weight: bold; color: #f8fafc; margin-top: 2px; }
            QLabel#kpiSubtext { font-size: 8.5pt; color: #64748b; margin-top: 2px; }

            QFrame#caliperStrip { background-color: #161a29; border: 1px solid #283048; border-radius: 6px; padding: 6px 12px; }
            QLabel#caliperLabel { font-size: 9.5pt; font-weight: 600; color: #94a3b8; }
            QLabel#caliperVal { font-size: 11.5pt; font-weight: bold; color: #f8fafc; }

            QTabWidget::pane { border: 1px solid #2e3650; background-color: #141724; border-radius: 8px; }
            QTabBar::tab { background: #1a1e2e; color: #94a3b8; padding: 8px 16px; border-top-left-radius: 6px; border-top-right-radius: 6px; font-weight: 600; margin-right: 2px; }
            QTabBar::tab:selected { background: #2563eb; color: #ffffff; }
            QTableWidget { background-color: #141724; border: none; gridline-color: #23293d; selection-background-color: #1e3a8a; selection-color: #ffffff; }
            QHeaderView::section { background-color: #1a1e2e; color: #94a3b8; border: none; border-bottom: 1px solid #2e3650; padding: 6px; font-weight: 600; font-size: 9pt; }
            QGroupBox { font-weight: bold; border: 1px solid #2e3650; border-radius: 6px; margin-top: 8px; padding-top: 10px; color: #60a5fa; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QDialog { background-color: #0f111a; color: #cbd5e1; }
        """
    },
    "light": {
        "id": "light",
        "name_key": "theme_light",
        "desc_key": "theme_light_desc",
        "plot_bg": "#ffffff",
        "axis_pen": "#94a3b8",
        "axis_text": "#334155",
        "grid_alpha": 0.30,
        "curve_color": "#0284c7",
        "curve_width": 1.8,
        "r_peak_brush": "#dc2626",
        "r_peak_symbol": "t1",
        "q_caliper_color": "#d97706",
        "t_caliper_color": "#7c3aed",
        "caliper_label_fill": (241, 245, 249, 230),
        "qss": """
            QMainWindow { background-color: #f1f5f9; }
            QWidget { background-color: #f1f5f9; color: #1e293b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 10pt; }

            QFrame#topBar { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px 12px; }
            QLabel#appTitle { font-size: 14pt; font-weight: bold; color: #0284c7; }
            QLabel#fileBadge { background-color: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 8px; font-size: 9.5pt; font-weight: 500; }

            QPushButton { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px 14px; font-weight: 600; color: #1e293b; }
            QPushButton:hover { background-color: #f8fafc; border-color: #0284c7; color: #0284c7; }
            QPushButton#btnPrimary { background-color: #0284c7; border: 1px solid #0369a1; color: #ffffff; }
            QPushButton#btnPrimary:hover { background-color: #0369a1; }
            QPushButton#btnSecondary { background-color: #0f766e; border: 1px solid #115e59; color: #ffffff; }
            QPushButton#btnSecondary:hover { background-color: #115e59; }
            QPushButton#btnSettings { background-color: #f8fafc; border: 1px solid #cbd5e1; color: #475569; }
            QPushButton#btnSettings:hover { background-color: #e2e8f0; color: #0f172a; border-color: #0284c7; }

            QComboBox { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 10px; color: #1e293b; font-weight: 600; min-width: 120px; }
            QComboBox:hover { border-color: #0284c7; }
            QComboBox QAbstractItemView { background-color: #ffffff; selection-background-color: #e0f2fe; color: #0284c7; border: 1px solid #cbd5e1; }

            QFrame#kpiCard { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; }
            QLabel#kpiTitle { font-size: 8.5pt; font-weight: bold; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
            QLabel#kpiValue { font-size: 16pt; font-weight: bold; color: #0f172a; margin-top: 2px; }
            QLabel#kpiSubtext { font-size: 8.5pt; color: #64748b; margin-top: 2px; }

            QFrame#caliperStrip { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 12px; }
            QLabel#caliperLabel { font-size: 9.5pt; font-weight: 600; color: #475569; }
            QLabel#caliperVal { font-size: 11.5pt; font-weight: bold; color: #0f172a; }

            QTabWidget::pane { border: 1px solid #cbd5e1; background-color: #ffffff; border-radius: 8px; }
            QTabBar::tab { background: #e2e8f0; color: #475569; padding: 8px 16px; border-top-left-radius: 6px; border-top-right-radius: 6px; font-weight: 600; margin-right: 2px; }
            QTabBar::tab:selected { background: #0284c7; color: #ffffff; }
            QTableWidget { background-color: #ffffff; border: none; gridline-color: #f1f5f9; selection-background-color: #e0f2fe; selection-color: #0369a1; }
            QHeaderView::section { background-color: #f8fafc; color: #475569; border: none; border-bottom: 1px solid #cbd5e1; padding: 6px; font-weight: 600; font-size: 9pt; }
            QGroupBox { font-weight: bold; border: 1px solid #cbd5e1; border-radius: 6px; margin-top: 8px; padding-top: 10px; color: #0284c7; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QDialog { background-color: #f1f5f9; color: #1e293b; }
        """
    },
    "colorblind": {
        "id": "colorblind",
        "name_key": "theme_colorblind",
        "desc_key": "theme_colorblind_desc",
        "plot_bg": "#000000",
        "axis_pen": "#b0bec5",
        "axis_text": "#ffffff",
        "grid_alpha": 0.28,
        "curve_color": "#56b4e9",  # Okabe-Ito Sky Blue
        "curve_width": 2.0,
        "r_peak_brush": "#f0e442",  # Okabe-Ito Yellow
        "r_peak_symbol": "d",
        "q_caliper_color": "#e69f00",  # Okabe-Ito Orange
        "t_caliper_color": "#0072b2",  # Okabe-Ito Deep Blue
        "caliper_label_fill": (0, 0, 0, 230),
        "qss": """
            QMainWindow { background-color: #121212; }
            QWidget { background-color: #121212; color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 10pt; }

            QFrame#topBar { background-color: #1e1e1e; border: 2px solid #555555; border-radius: 8px; padding: 6px 12px; }
            QLabel#appTitle { font-size: 14pt; font-weight: bold; color: #56b4e9; }
            QLabel#fileBadge { background-color: #262626; color: #ffffff; border: 1px solid #777777; border-radius: 4px; padding: 4px 8px; font-size: 9.5pt; font-weight: bold; }

            QPushButton { background-color: #262626; border: 2px solid #777777; border-radius: 6px; padding: 6px 14px; font-weight: bold; color: #ffffff; }
            QPushButton:hover { background-color: #383838; border-color: #f0e442; color: #ffffff; }
            QPushButton#btnPrimary { background-color: #0072b2; border: 2px solid #56b4e9; color: #ffffff; }
            QPushButton#btnPrimary:hover { background-color: #005587; }
            QPushButton#btnSecondary { background-color: #e69f00; border: 2px solid #ffd54f; color: #000000; font-weight: bold; }
            QPushButton#btnSecondary:hover { background-color: #d18f00; }
            QPushButton#btnSettings { background-color: #262626; border: 2px solid #777777; color: #ffffff; }
            QPushButton#btnSettings:hover { background-color: #383838; border-color: #f0e442; }

            QComboBox { background-color: #1e1e1e; border: 2px solid #777777; border-radius: 6px; padding: 5px 10px; color: #ffffff; font-weight: bold; min-width: 120px; }
            QComboBox:hover { border-color: #f0e442; }
            QComboBox QAbstractItemView { background-color: #1e1e1e; selection-background-color: #0072b2; color: #ffffff; border: 2px solid #555555; }

            QFrame#kpiCard { background-color: #1e1e1e; border: 2px solid #555555; border-radius: 8px; padding: 10px; }
            QLabel#kpiTitle { font-size: 8.5pt; font-weight: bold; color: #b0bec5; text-transform: uppercase; letter-spacing: 0.5px; }
            QLabel#kpiValue { font-size: 16pt; font-weight: bold; color: #ffffff; margin-top: 2px; }
            QLabel#kpiSubtext { font-size: 8.5pt; color: #b0bec5; margin-top: 2px; }

            QFrame#caliperStrip { background-color: #1e1e1e; border: 2px solid #555555; border-radius: 6px; padding: 6px 12px; }
            QLabel#caliperLabel { font-size: 9.5pt; font-weight: bold; color: #ffffff; }
            QLabel#caliperVal { font-size: 11.5pt; font-weight: bold; color: #f0e442; }

            QTabWidget::pane { border: 2px solid #555555; background-color: #181818; border-radius: 8px; }
            QTabBar::tab { background: #262626; color: #b0bec5; padding: 8px 16px; border-top-left-radius: 6px; border-top-right-radius: 6px; font-weight: bold; margin-right: 2px; }
            QTabBar::tab:selected { background: #0072b2; color: #ffffff; border-bottom: 2px solid #f0e442; }
            QTableWidget { background-color: #181818; border: none; gridline-color: #333333; selection-background-color: #005587; selection-color: #ffffff; }
            QHeaderView::section { background-color: #262626; color: #ffffff; border: none; border-bottom: 2px solid #555555; padding: 6px; font-weight: bold; font-size: 9pt; }
            QGroupBox { font-weight: bold; border: 2px solid #555555; border-radius: 6px; margin-top: 8px; padding-top: 10px; color: #56b4e9; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QDialog { background-color: #121212; color: #ffffff; }
        """
    }
}


# -----------------------------------------------------------------------------
# INDEPENDENT CANVAS THEMES (Contrasting Waveform, Calipers & Grid)
# -----------------------------------------------------------------------------
_BEAT_CLASS_COLORS: dict[str, str] = {
    "V": "#f87171",
    "S": "#fbbf24",
    "F": "#c084fc",
    "N": "#34d399",
}
_SEVERITY_COLORS: dict[str, str] = {
    "CRITICAL": "#f87171",
    "WARNING": "#fbbf24",
}

CLINICAL_SPEEDS: list[float] = [12.5, 25.0, 50.0, 100.0]  # Standard ECG sweep speeds (mm/s)
CLINICAL_GAINS: list[float] = [2.5, 5.0, 10.0, 20.0]      # Standard ECG voltage sensitivities (mm/mV)

CANVAS_THEMES: dict[str, dict[str, Any]] = {
    "dark": {
        "id": "dark",
        "name_key": "canvas_dark",
        "plot_bg": "#13151f",
        "axis_pen": "#475569",
        "axis_text": "#94a3b8",
        "grid_color": "#2e3650",
        "grid_alpha": 0.22,
        "curve_color": "#38bdf8",         # Bright Medical Cyan (contrasts on dark canvas)
        "curve_width": 1.8,
        "r_peak_brush": "#f87171",        # Coral Salmon
        "r_peak_symbol": "t1",
        "q_caliper_color": "#fbbf24",     # Vibrant Gold/Amber (contrasts with cyan curve)
        "q_caliper_style": Qt.PenStyle.DashLine,
        "t_caliper_color": "#e879f9",     # Vivid Fuchsia/Magenta (contrasts with cyan & gold)
        "t_caliper_style": Qt.PenStyle.DashLine,
        "caliper_label_fill": (26, 30, 44, 220),
        "badge_bg": "rgba(26, 30, 44, 0.90)",
        "badge_border": "#38bdf8",
        "badge_text": "#38bdf8",
    },
    "light": {
        "id": "light",
        "name_key": "canvas_light",
        "plot_bg": "#ffffff",             # Pure Paper White
        "axis_pen": "#94a3b8",
        "axis_text": "#334155",
        "grid_color": "#cbd5e1",
        "grid_alpha": 0.40,
        "curve_color": "#0369a1",         # Deep Ocean Blue (sharp contrast on white)
        "curve_width": 2.0,
        "r_peak_brush": "#dc2626",        # Crimson Red
        "r_peak_symbol": "t1",
        "q_caliper_color": "#d97706",     # Deep Amber Orange (contrasts with blue curve & white bg)
        "q_caliper_style": Qt.PenStyle.DashLine,
        "t_caliper_color": "#7c3aed",     # Vivid Purple/Violet (contrasts with amber & blue)
        "t_caliper_style": Qt.PenStyle.DashLine,
        "caliper_label_fill": (241, 245, 249, 230),
        "badge_bg": "rgba(241, 245, 249, 0.95)",
        "badge_border": "#0284c7",
        "badge_text": "#0369a1",
    },
    "ecg_pink": {
        "id": "ecg_pink",
        "name_key": "canvas_ecg_pink",
        "plot_bg": "#fff1f2",             # Traditional ECG Thermal Paper Pink
        "axis_pen": "#9f1239",
        "axis_text": "#881337",
        "grid_color": "#fda4af",         # Classic Millimeter Red/Pink Grid
        "grid_alpha": 0.50,
        "curve_color": "#0f172a",         # Jet Black Trace (Standard clinical print appearance)
        "curve_width": 2.0,
        "r_peak_brush": "#e11d48",        # Deep Rose
        "r_peak_symbol": "t1",
        "q_caliper_color": "#2563eb",     # Electric Royal Blue (pops out from black trace & pink grid)
        "q_caliper_style": Qt.PenStyle.DashLine,
        "t_caliper_color": "#d97706",     # Bold Amber/Orange (pops out from blue & black)
        "t_caliper_style": Qt.PenStyle.DashLine,
        "caliper_label_fill": (255, 228, 230, 230),
        "badge_bg": "rgba(255, 228, 230, 0.95)",
        "badge_border": "#e11d48",
        "badge_text": "#9f1239",
    },
    "colorblind": {
        "id": "colorblind",
        "name_key": "canvas_colorblind",
        "plot_bg": "#000000",             # Pitch Black (Maximum luminance separation)
        "axis_pen": "#b0bec5",
        "axis_text": "#ffffff",
        "grid_color": "#525252",
        "grid_alpha": 0.35,
        "curve_color": "#56b4e9",         # Okabe-Ito Sky Blue
        "curve_width": 2.2,
        "r_peak_brush": "#f0e442",        # Okabe-Ito Bright Yellow (stands out on black)
        "r_peak_symbol": "d",             # Diamond symbol for shape-based distinction
        "q_caliper_color": "#e69f00",     # Okabe-Ito Vermilion/Orange
        "q_caliper_style": Qt.PenStyle.DashLine,
        "t_caliper_color": "#ffffff",     # High-luminance White (distinct line style & color)
        "t_caliper_style": Qt.PenStyle.DashDotLine,
        "caliper_label_fill": (0, 0, 0, 230),
        "badge_bg": "rgba(20, 20, 20, 0.95)",
        "badge_border": "#f0e442",
        "badge_text": "#ffffff",
    },
    "green_phosphor": {
        "id": "green_phosphor",
        "name_key": "canvas_green_phosphor",
        "plot_bg": "#021a0f",             # Deep Night Emerald
        "axis_pen": "#16a34a",
        "axis_text": "#86efac",
        "grid_color": "#14532d",
        "grid_alpha": 0.35,
        "curve_color": "#22c55e",         # Neon Phosphor Green
        "curve_width": 2.0,
        "r_peak_brush": "#facc15",        # Phosphor Amber
        "r_peak_symbol": "t1",
        "q_caliper_color": "#fb923c",     # Vivid Orange (contrasts with green trace & dark bg)
        "q_caliper_style": Qt.PenStyle.DashLine,
        "t_caliper_color": "#f43f5e",     # Hot Coral/Pink (contrasts with orange & green)
        "t_caliper_style": Qt.PenStyle.DashLine,
        "caliper_label_fill": (5, 46, 22, 230),
        "badge_bg": "rgba(5, 46, 22, 0.95)",
        "badge_border": "#22c55e",
        "badge_text": "#86efac",
    }
}

_AxisItemBase = pg.AxisItem if HAS_GUI else object


class TimeAxisItem(_AxisItemBase):  # type: ignore[misc]
    """Custom AxisItem formatting timestamps into clinical hh:mm:ss:xxx format with millisecond precision."""

    def __init__(self, orientation: str = "bottom", millisecond_separator: str = ":", **kwargs: Any) -> None:
        if HAS_GUI:
            super().__init__(orientation=orientation, **kwargs)
        self.millisecond_separator = millisecond_separator

    def format_timestamp(self, val: float, include_millis: bool = True) -> str:
        """Formats seconds into hh:mm:ss or hh:mm:ss:xxx with millisecond precision."""
        if val is None or not np.isfinite(val):
            return ""
        is_neg = val < 0
        v = abs(float(val))
        hours = int(v // 3600)
        minutes = int((v % 3600) // 60)
        int_secs = int(v % 60)
        millis = int(round((v - int(v)) * 1000))
        if millis >= 1000:
            millis = 0
            int_secs += 1
            if int_secs >= 60:
                int_secs = 0
                minutes += 1
                if minutes >= 60:
                    minutes = 0
                    hours += 1
        prefix = "-" if is_neg else ""
        if include_millis:
            return f"{prefix}{hours:02d}:{minutes:02d}:{int_secs:02d}{self.millisecond_separator}{millis:03d}"
        return f"{prefix}{hours:02d}:{minutes:02d}:{int_secs:02d}"

    def tickStrings(self, values: list[float], scale: float, spacing: float) -> list[str]:
        include_millis = spacing < 1.0
        return [self.format_timestamp(val, include_millis=include_millis) for val in values]

class ECGPlotWidget:
    """PyQtGraph-based high-performance interactive ECG waveform viewer with draggable calipers,
    independent canvas color schemes, hh:mm:ss clinical time axis, and scale overlays."""

    def __init__(self, parent: QWidget | None = None) -> None:
        # Initialize time axis with hh:mm:ss formatter
        self.time_axis = TimeAxisItem(orientation="bottom")
        self.plot_widget = pg.PlotWidget(parent=parent, axisItems={"bottom": self.time_axis})

        # Clinical axis labels
        self.plot_widget.setLabel("bottom", tr("axis_time"))
        self.plot_widget.setLabel("left", tr("axis_voltage"))
        self.plot_widget.setTitle(
            "ECG Waveform — Lead II (Standard)",
            color="#93c5fd",
            size="11pt"
        )

        self.current_canvas_theme = CANVAS_THEMES["dark"]
        self.current_grid_mode = "lines"
        self.current_speed = 25.0
        self.current_gain = 10.0
        self.calipers_visible = True
        self.extra_vertical_lines: list[Any] = []
        self.ectopic_text_items: list[Any] = []
        self.last_r_peak_classes: list[str] = []
        self.last_r_peak_colors: list[str] = []

        # Plot curves: Soft medical cyan-blue waveform
        self.signal_curve = self.plot_widget.plot(pen=pg.mkPen(color="#38bdf8", width=1.8))
        self.r_peak_scatter = pg.ScatterPlotItem(
            size=9, pen=pg.mkPen(None), brush=pg.mkBrush("#f87171"), symbol="t1"
        )
        self.plot_widget.addItem(self.r_peak_scatter)

        # Interactive draggable caliper lines for QT measurement
        self.q_line = pg.InfiniteLine(
            pos=0.0, angle=90, movable=True,
            pen=pg.mkPen(color="#fbbf24", width=2.2, style=Qt.PenStyle.DashLine),
            label="Q-Onset: {value:.3f}s",
            labelOpts={"position": 0.92, "color": "#fbbf24", "fill": (26, 30, 44, 220)}
        )
        self.t_line = pg.InfiniteLine(
            pos=0.0, angle=90, movable=True,
            pen=pg.mkPen(color="#e879f9", width=2.2, style=Qt.PenStyle.DashLine),
            label="T-End: {value:.3f}s",
            labelOpts={"position": 0.78, "color": "#e879f9", "fill": (26, 30, 44, 220)}
        )

        self.plot_widget.addItem(self.q_line)
        self.plot_widget.addItem(self.t_line)

        # On-canvas scale indicator badge (Top Right Corner)
        self.scale_corner_label = QLabel(f"📐 {tr('canvas_scale_badge')}", parent=self.plot_widget)
        self.scale_corner_label.setObjectName("cornerScaleBadge")
        self.scale_corner_label.setStyleSheet("""
            QLabel#cornerScaleBadge {
                background-color: rgba(26, 30, 44, 0.90);
                color: #38bdf8;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 8.5pt;
                font-weight: bold;
            }
        """)

        self.on_caliper_moved: Callable[[float, float], None] | None = None
        self.q_line.sigPositionChanged.connect(self._notify_caliper_change)
        self.t_line.sigPositionChanged.connect(self._notify_caliper_change)

        # Apply initial canvas scheme and grid
        self.apply_canvas_theme(self.current_canvas_theme)

    def clear_ectopic_markers(self) -> None:
        """Removes on-canvas ectopic beat class text tags."""
        for item in self.ectopic_text_items:
            with contextlib.suppress(Exception):
                self.plot_widget.removeItem(item)
        self.ectopic_text_items.clear()

    def display_signal(
        self,
        time_data: np.ndarray,
        signal_data: np.ndarray,
        r_peaks: np.ndarray,
        beat_classes: list[str] | None = None,
    ) -> None:
        """Updates the plot waveform curve, color-coded AAMI R-peak markers, and ectopic text overlays."""
        self.clear_ectopic_markers()
        self.signal_curve.setData(time_data, signal_data)
        if len(r_peaks) > 0:
            r_times = time_data[r_peaks]
            r_amps = signal_data[r_peaks]
            default_col = self.current_canvas_theme.get("r_peak_brush", "#34d399")
            classes = [
                str(beat_classes[i]) if (beat_classes and i < len(beat_classes)) else "N"
                for i in range(len(r_peaks))
            ]
            colors = [
                _BEAT_CLASS_COLORS.get(c, default_col) if c in _BEAT_CLASS_COLORS else default_col
                for c in classes
            ]
            self.last_r_peak_classes = classes
            self.last_r_peak_colors = colors
            brushes = [pg.mkBrush(c) for c in colors]
            self.r_peak_scatter.setData(x=r_times, y=r_amps, brush=brushes)

            for r_t, r_a, c_code, col_hex in zip(r_times, r_amps, classes, colors, strict=False):
                if c_code != "N":
                    txt_item = pg.TextItem(text=c_code, color=col_hex, anchor=(0.5, 1.2))
                    if hasattr(txt_item, "setPos"):
                        txt_item.setPos(float(r_t), float(r_a))
                    self.plot_widget.addItem(txt_item)
                    self.ectopic_text_items.append(txt_item)
        else:
            self.last_r_peak_classes = []
            self.last_r_peak_colors = []
            self.r_peak_scatter.clear()
        self.plot_widget.enableAutoRange()
        self.update_corner_badge()

    def set_calipers(self, q_time: float, t_time: float) -> None:
        """Sets the horizontal positions of the Q-onset and T-end calipers."""
        self.q_line.blockSignals(True)
        self.t_line.blockSignals(True)
        self.q_line.setValue(q_time)
        self.t_line.setValue(t_time)
        self.q_line.blockSignals(False)
        self.t_line.blockSignals(False)
        self._notify_caliper_change()

    def _notify_caliper_change(self) -> None:
        if self.on_caliper_moved:
            self.on_caliper_moved(self.q_line.value(), self.t_line.value())

    def get_scale_text(self) -> str:
        """Returns localized scale description based on active sweep speed and gain."""
        s_str = f"{int(self.current_speed)}" if self.current_speed.is_integer() else f"{self.current_speed}"
        g_str = f"{int(self.current_gain)}" if self.current_gain.is_integer() else f"{self.current_gain}"
        return tr("canvas_scale_fmt", speed=s_str, gain=g_str)

    def update_corner_badge(self) -> None:
        """Ensures the clinical scale badge stays pinned to the top-right corner.
        Scale badge is ONLY visible when the grid is enabled."""
        if hasattr(self, 'scale_corner_label') and self.scale_corner_label is not None:
            if self.current_grid_mode == "none":
                self.scale_corner_label.setVisible(False)
                return
            self.scale_corner_label.setVisible(True)
            self.scale_corner_label.setText(f"📐 {self.get_scale_text()}")
            w = self.scale_corner_label.sizeHint().width()
            self.scale_corner_label.move(max(10, self.plot_widget.width() - w - 16), 10)
            self.scale_corner_label.raise_()

    def apply_canvas_theme(self, theme: dict[str, Any]) -> None:
        """Applies independent canvas color scheme to plot, curves, calipers, and scale badge."""
        self.current_canvas_theme = theme
        self.plot_widget.setBackground(theme["plot_bg"])

        # Style axes and labels
        bottom_axis = self.plot_widget.getAxis("bottom")
        left_axis = self.plot_widget.getAxis("left")
        bottom_axis.setPen(pg.mkPen(color=theme["axis_pen"]))
        left_axis.setPen(pg.mkPen(color=theme["axis_pen"]))
        bottom_axis.setTextPen(pg.mkPen(color=theme["axis_text"]))
        left_axis.setTextPen(pg.mkPen(color=theme["axis_text"]))

        # Style lead curve & R-peak markers
        self.signal_curve.setPen(pg.mkPen(color=theme["curve_color"], width=theme.get("curve_width", 1.8)))
        self.r_peak_scatter.setBrush(pg.mkBrush(theme["r_peak_brush"]))
        if "r_peak_symbol" in theme:
            self.r_peak_scatter.setSymbol(theme["r_peak_symbol"])

        # Style calipers with high-contrast colors & distinct line styles
        q_style = theme.get("q_caliper_style", Qt.PenStyle.DashLine)
        t_style = theme.get("t_caliper_style", Qt.PenStyle.DashLine)

        self.q_line.setPen(pg.mkPen(color=theme["q_caliper_color"], width=2.2, style=q_style))
        self.q_line.label.setColor(theme["q_caliper_color"])
        self.q_line.label.fill = pg.mkBrush(*theme["caliper_label_fill"])

        self.t_line.setPen(pg.mkPen(color=theme["t_caliper_color"], width=2.2, style=t_style))
        self.t_line.label.setColor(theme["t_caliper_color"])
        self.t_line.label.fill = pg.mkBrush(*theme["caliper_label_fill"])

        # Style on-canvas corner scale badge
        if hasattr(self, 'scale_corner_label') and self.scale_corner_label is not None:
            self.scale_corner_label.setStyleSheet(f"""
                QLabel#cornerScaleBadge {{
                    background-color: {theme.get("badge_bg", "rgba(26, 30, 44, 0.90)")};
                    color: {theme.get("badge_text", "#38bdf8")};
                    border: 1px solid {theme.get("badge_border", "#38bdf8")};
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-size: 8.5pt;
                    font-weight: bold;
                }}
            """)
            self.update_corner_badge()

        # Re-apply current grid mode
        self.apply_grid(self.current_grid_mode)

    def apply_grid(self, mode: str) -> None:
        """Applies grid styling (Lines, Dots, or None) highlighting clinical scale.
        Only displays scale indicator badge if a grid is enabled."""
        self.current_grid_mode = mode
        if mode == "none":
            self.plot_widget.showGrid(x=False, y=False)
            if hasattr(self, 'scale_corner_label') and self.scale_corner_label is not None:
                self.scale_corner_label.setVisible(False)
            return

        alpha = self.current_canvas_theme.get("grid_alpha", 0.25)
        self.plot_widget.showGrid(x=True, y=True, alpha=alpha)

        bottom_axis = self.plot_widget.getAxis("bottom")
        left_axis = self.plot_widget.getAxis("left")

        bottom_axis.setGrid(alpha)
        left_axis.setGrid(alpha)

        if hasattr(self, 'scale_corner_label') and self.scale_corner_label is not None:
            self.scale_corner_label.setVisible(True)
            self.update_corner_badge()

    def set_scale(self, speed: float, gain: float, center_time: float | None = None) -> None:
        """Applies standardized clinical ECG sweep speed (mm/s) and voltage gain (mm/mV).
        Adjusts visible time window and amplitude span around the current viewport center."""
        self.current_speed = float(speed)
        self.current_gain = float(gain)

        window_duration = 250.0 / self.current_speed
        span_mv = 40.0 / self.current_gain

        if center_time is None:
            try:
                view_box = self.plot_widget.getViewBox()
                current_range = view_box.viewRange()
                center_time = (current_range[0][0] + current_range[0][1]) / 2.0
                if not np.isfinite(center_time):
                    center_time = (self.q_line.value() + self.t_line.value()) / 2.0
                if not np.isfinite(center_time):
                    center_time = 5.0
            except Exception:
                center_time = 5.0

        new_x_min = center_time - (window_duration / 2.0)
        new_x_max = center_time + (window_duration / 2.0)
        new_y_min = -span_mv * 0.4
        new_y_max = span_mv * 0.6

        self.plot_widget.setXRange(new_x_min, new_x_max, padding=0)
        self.plot_widget.setYRange(new_y_min, new_y_max, padding=0)
        self.update_corner_badge()

    def zoom_in(self) -> None:
        """Increases zoom level by stepping to the next clinical speed or gain."""
        s_idx = CLINICAL_SPEEDS.index(self.current_speed) if self.current_speed in CLINICAL_SPEEDS else 1
        g_idx = CLINICAL_GAINS.index(self.current_gain) if self.current_gain in CLINICAL_GAINS else 2

        if s_idx < len(CLINICAL_SPEEDS) - 1:
            self.set_scale(CLINICAL_SPEEDS[s_idx + 1], self.current_gain)
        elif g_idx < len(CLINICAL_GAINS) - 1:
            self.set_scale(self.current_speed, CLINICAL_GAINS[g_idx + 1])

    def zoom_out(self) -> None:
        """Decreases zoom level by stepping to the previous clinical speed or gain."""
        s_idx = CLINICAL_SPEEDS.index(self.current_speed) if self.current_speed in CLINICAL_SPEEDS else 1
        g_idx = CLINICAL_GAINS.index(self.current_gain) if self.current_gain in CLINICAL_GAINS else 2

        if s_idx > 0:
            self.set_scale(CLINICAL_SPEEDS[s_idx - 1], self.current_gain)
        elif g_idx > 0:
            self.set_scale(self.current_speed, CLINICAL_GAINS[g_idx - 1])

    def zoom_reset(self) -> None:
        """Resets view to clinical baseline standard: 25 mm/s and 10 mm/mV."""
        self.set_scale(25.0, 10.0)

    def zoom_fit(self) -> None:
        """Autoscales view to display full recording duration."""
        self.plot_widget.enableAutoRange()
        self.update_corner_badge()

    def set_calipers_visible(self, visible: bool) -> None:
        """Toggles visibility of draggable vertical measurement lines (calipers & cursors)."""
        self.calipers_visible = visible
        self.q_line.setVisible(visible)
        self.t_line.setVisible(visible)
        for line in self.extra_vertical_lines:
            line.setVisible(visible)

    def center_calipers(self) -> None:
        """Brings draggable vertical lines to the center of the current screen view."""
        with contextlib.suppress(Exception):
            view_box = self.plot_widget.getViewBox()
            x_range = view_box.viewRange()[0]
            center = (x_range[0] + x_range[1]) / 2.0
            width = x_range[1] - x_range[0]
            self.set_calipers(center - width * 0.10, center + width * 0.10)

    def add_draggable_vertical_line(self, pos: float | None = None, label: str | None = None) -> Any:
        """Adds an additional interactive draggable vertical measurement line."""
        if pos is None:
            try:
                view_box = self.plot_widget.getViewBox()
                x_range = view_box.viewRange()[0]
                pos = (x_range[0] + x_range[1]) / 2.0
            except Exception:
                pos = 0.0
        idx = len(self.extra_vertical_lines) + 1
        tag = label or f"Line {idx}"
        theme = self.current_canvas_theme
        color = theme.get("curve_color", "#38bdf8")
        line = pg.InfiniteLine(
            pos=pos, angle=90, movable=True,
            pen=pg.mkPen(color=color, width=2.0, style=Qt.PenStyle.DashDotLine),
            label=f"{tag}: " + "{value:.3f}s",
            labelOpts={"position": max(0.2, 0.70 - (idx * 0.12)), "color": color, "fill": theme.get("caliper_label_fill", (26, 30, 44, 200))}
        )
        line.setVisible(self.calipers_visible)
        self.plot_widget.addItem(line)
        self.extra_vertical_lines.append(line)
        return line

    def clear_extra_vertical_lines(self) -> None:
        """Removes all custom draggable vertical lines, retaining standard Q & T calipers."""
        for line in self.extra_vertical_lines:
            with contextlib.suppress(Exception):
                self.plot_widget.removeItem(line)
        self.extra_vertical_lines.clear()





class SettingsDialog(QDialog):
    """Modal preferences dialog for Language, Window Theme, Independent Canvas Scheme, and Grid."""

    def __init__(self, main_window: MainWindow) -> None:
        super().__init__(parent=main_window)
        self.main_window = main_window
        self.setWindowTitle(tr("settings_title"))
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        # 1. Interface Language Section
        self.lbl_lang_section = QLabel(tr("settings_language"))
        self.lbl_lang_section.setStyleSheet("font-weight: bold; font-size: 10pt;")
        layout.addWidget(self.lbl_lang_section)

        self.combo_lang = QComboBox()
        self.lang_codes = ["en", "es", "fr", "de", "pt"]
        current_locale = get_current_locale()
        curr_idx = 0
        for idx, code in enumerate(self.lang_codes):
            self.combo_lang.addItem(SUPPORTED_LANGUAGES.get(code, code), code)
            if code == current_locale:
                curr_idx = idx
        self.combo_lang.setCurrentIndex(curr_idx)
        self.combo_lang.currentIndexChanged.connect(self._on_language_selected)
        layout.addWidget(self.combo_lang)

        # 2. Window Color Scheme (Theme) Section
        self.lbl_theme_section = QLabel(tr("settings_theme"))
        self.lbl_theme_section.setStyleSheet("font-weight: bold; font-size: 10pt; margin-top: 4px;")
        layout.addWidget(self.lbl_theme_section)

        self.combo_theme = QComboBox()
        self.theme_ids = ["dark", "light", "colorblind"]
        theme_idx = 0
        for idx, tid in enumerate(self.theme_ids):
            self.combo_theme.addItem(tr(THEMES[tid]["name_key"]), tid)
            if tid == self.main_window.current_theme_id:
                theme_idx = idx
        self.combo_theme.setCurrentIndex(theme_idx)
        self.combo_theme.currentIndexChanged.connect(self._on_theme_selected)
        layout.addWidget(self.combo_theme)

        # 3. Independent Waveform Canvas Scheme Section
        self.lbl_canvas_section = QLabel(tr("settings_canvas_theme"))
        self.lbl_canvas_section.setStyleSheet("font-weight: bold; font-size: 10pt; margin-top: 4px;")
        layout.addWidget(self.lbl_canvas_section)

        self.combo_canvas = QComboBox()
        self.canvas_ids = list(CANVAS_THEMES.keys())
        canvas_idx = 0
        for idx, cid in enumerate(self.canvas_ids):
            self.combo_canvas.addItem(tr(CANVAS_THEMES[cid]["name_key"]), cid)
            if cid == self.main_window.current_canvas_theme_id:
                canvas_idx = idx
        self.combo_canvas.setCurrentIndex(canvas_idx)
        self.combo_canvas.currentIndexChanged.connect(self._on_canvas_theme_selected)
        layout.addWidget(self.combo_canvas)

        # 4. Clinical ECG Grid Section (Lines, Dots, None)
        self.lbl_grid_section = QLabel(tr("settings_grid"))
        self.lbl_grid_section.setStyleSheet("font-weight: bold; font-size: 10pt; margin-top: 4px;")
        layout.addWidget(self.lbl_grid_section)

        self.combo_grid = QComboBox()
        self.grid_modes = [("lines", tr("grid_lines")), ("dots", tr("grid_dots")), ("none", tr("grid_none"))]
        grid_idx = 0
        for idx, (gid, gname) in enumerate(self.grid_modes):
            self.combo_grid.addItem(gname, gid)
            if gid == self.main_window.current_grid_mode:
                grid_idx = idx
        self.combo_grid.setCurrentIndex(grid_idx)
        self.combo_grid.currentIndexChanged.connect(self._on_grid_selected)
        layout.addWidget(self.combo_grid)

        # 5. QT-RR Restitution Model Section (10 Pueyo 2004 Models + Auto-Best)
        self.lbl_qtrr_section = QLabel(tr("settings_qtrr_model"))
        self.lbl_qtrr_section.setStyleSheet("font-weight: bold; font-size: 10pt; margin-top: 4px;")
        layout.addWidget(self.lbl_qtrr_section)

        self.combo_qtrr_model = QComboBox()
        self.qtrr_model_options = [("auto_best", tr("qtrr_auto_best"))] + [
            (m_id, QTRR_MODEL_METADATA[m_id]["label"]) for m_id in SUPPORTED_QTRR_MODELS
        ]
        qtrr_idx = 0
        for idx, (mid, mlabel) in enumerate(self.qtrr_model_options):
            self.combo_qtrr_model.addItem(mlabel, mid)
            if mid == getattr(self.main_window, "current_qtrr_model", "linear"):
                qtrr_idx = idx
        self.combo_qtrr_model.setCurrentIndex(qtrr_idx)
        self.combo_qtrr_model.currentIndexChanged.connect(self._on_qtrr_model_selected)
        layout.addWidget(self.combo_qtrr_model)

        # 6. Multi-Beat QT-RR Hysteresis Compensation Section (EW / LW / Raw)
        self.lbl_hyst_section = QLabel(tr("settings_hysteresis_mode"))
        self.lbl_hyst_section.setStyleSheet("font-weight: bold; font-size: 10pt; margin-top: 4px;")
        layout.addWidget(self.lbl_hyst_section)

        self.combo_hysteresis = QComboBox()
        self.hyst_modes = [
            ("exponential", tr("hyst_mode_exp")),
            ("linear", tr("hyst_mode_lin")),
            ("raw", tr("hyst_mode_raw")),
        ]
        hyst_idx = 0
        for idx, (hid, hname) in enumerate(self.hyst_modes):
            self.combo_hysteresis.addItem(hname, hid)
            if hid == getattr(self.main_window, "current_hysteresis_mode", "exponential"):
                hyst_idx = idx
        self.combo_hysteresis.setCurrentIndex(hyst_idx)
        self.combo_hysteresis.currentIndexChanged.connect(self._on_hysteresis_selected)
        layout.addWidget(self.combo_hysteresis)

        # 7. T-Wave Offset (T-End) Delineation Algorithm Section
        self.lbl_tend_section = QLabel(tr("settings_t_end_method"))
        self.lbl_tend_section.setStyleSheet("font-weight: bold; font-size: 10pt; margin-top: 4px;")
        layout.addWidget(self.lbl_tend_section)

        self.combo_t_end = QComboBox()
        self.tend_modes = [
            ("hybrid", tr("tend_mode_hybrid")),
            ("tangent", tr("tend_mode_tangent")),
            ("zhang_area", tr("tend_mode_zhang")),
            ("threshold", tr("tend_mode_threshold")),
        ]
        tend_idx = 0
        for idx, (tid, tname) in enumerate(self.tend_modes):
            self.combo_t_end.addItem(tname, tid)
            if tid == getattr(self.main_window, "current_t_end_method", "hybrid"):
                tend_idx = idx
        self.combo_t_end.setCurrentIndex(tend_idx)
        self.combo_t_end.currentIndexChanged.connect(self._on_t_end_selected)
        layout.addWidget(self.combo_t_end)

        # Description Cue
        self.lbl_theme_desc = QLabel(tr(THEMES[self.main_window.current_theme_id]["desc_key"]))
        self.lbl_theme_desc.setWordWrap(True)
        self.lbl_theme_desc.setStyleSheet("color: #94a3b8; font-size: 8.5pt; font-style: italic; margin-top: 4px;")
        layout.addWidget(self.lbl_theme_desc)

        layout.addSpacing(10)

        # Action Buttons (Done)
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self.btn_done = QPushButton(tr("btn_close"))
        self.btn_done.setObjectName("btnPrimary")
        self.btn_done.setMinimumWidth(110)
        self.btn_done.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_done)
        layout.addLayout(btn_box)

    def _on_language_selected(self, index: int) -> None:
        if index < 0 or index >= len(self.lang_codes):
            return
        lang_code = self.lang_codes[index]
        self.main_window.set_language(lang_code)

        # Retranslate dialog's own labels
        self.setWindowTitle(tr("settings_title"))
        self.lbl_lang_section.setText(tr("settings_language"))
        self.lbl_theme_section.setText(tr("settings_theme"))
        self.lbl_canvas_section.setText(tr("settings_canvas_theme"))
        self.lbl_grid_section.setText(tr("settings_grid"))
        if hasattr(self, "lbl_qtrr_section"):
            self.lbl_qtrr_section.setText(tr("settings_qtrr_model"))
            self.lbl_hyst_section.setText(tr("settings_hysteresis_mode"))
            self.lbl_tend_section.setText(tr("settings_t_end_method"))
        self.btn_done.setText(tr("btn_close"))

        # Refresh theme dropdowns
        self.combo_theme.blockSignals(True)
        curr_t_idx = self.combo_theme.currentIndex()
        self.combo_theme.clear()
        for tid in self.theme_ids:
            self.combo_theme.addItem(tr(THEMES[tid]["name_key"]), tid)
        self.combo_theme.setCurrentIndex(curr_t_idx)
        self.combo_theme.blockSignals(False)

        self.combo_canvas.blockSignals(True)
        curr_c_idx = self.combo_canvas.currentIndex()
        self.combo_canvas.clear()
        for cid in self.canvas_ids:
            self.combo_canvas.addItem(tr(CANVAS_THEMES[cid]["name_key"]), cid)
        self.combo_canvas.setCurrentIndex(curr_c_idx)
        self.combo_canvas.blockSignals(False)

        self.combo_grid.blockSignals(True)
        curr_g_idx = self.combo_grid.currentIndex()
        self.combo_grid.clear()
        for gid, gname in [("lines", tr("grid_lines")), ("dots", tr("grid_dots")), ("none", tr("grid_none"))]:
            self.combo_grid.addItem(gname, gid)
        self.combo_grid.setCurrentIndex(curr_g_idx)
        self.combo_grid.blockSignals(False)

        self.lbl_theme_desc.setText(tr(THEMES[self.main_window.current_theme_id]["desc_key"]))

    def _on_theme_selected(self, index: int) -> None:
        if index < 0 or index >= len(self.theme_ids):
            return
        theme_id = self.theme_ids[index]
        self.main_window.set_theme(theme_id)
        self.lbl_theme_desc.setText(tr(THEMES[theme_id]["desc_key"]))

    def _on_canvas_theme_selected(self, index: int) -> None:
        if index < 0 or index >= len(self.canvas_ids):
            return
        canvas_id = self.canvas_ids[index]
        self.main_window.set_canvas_theme(canvas_id)

    def _on_grid_selected(self, index: int) -> None:
        if index < 0:
            return
        grid_id = self.combo_grid.itemData(index)
        if grid_id:
            self.main_window.set_grid_mode(grid_id)

    def _on_qtrr_model_selected(self, index: int) -> None:
        if index < 0:
            return
        model_id = self.combo_qtrr_model.itemData(index)
        if model_id:
            self.main_window.set_qtrr_model(model_id)

    def _on_hysteresis_selected(self, index: int) -> None:
        if index < 0:
            return
        hyst_id = self.combo_hysteresis.itemData(index)
        if hyst_id:
            self.main_window.set_hysteresis_mode(hyst_id)

    def _on_t_end_selected(self, index: int) -> None:
        if index < 0:
            return
        tend_id = self.combo_t_end.itemData(index)
        if tend_id:
            self.main_window.set_t_end_method(tend_id)

class MainWindow(QMainWindow):
    """Clinical Electrocardiogram Analysis & Colleague Exchange Workstation."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Repolaris — Ventricular Repolarization & ECG Workstation")
        self.resize(1420, 880)

        self.fs = 500.0
        self.time_data: np.ndarray | None = None
        self.signal_data: np.ndarray | None = None
        self.multi_lead_signals: dict[str, np.ndarray] = {}
        self.current_lead_name: str = "Lead II"
        self.current_filename: str = tr("demo_filename")
        self.analysis_results: dict[str, Any] | None = None
        self.annotation_manager: AnnotationManager | None = None
        self.current_beat_index: int = 0
        self.current_beat_rr = 0.85
        self.current_metadata: dict[str, Any] = {}
        self.current_theme_id: str = "dark"
        self.current_canvas_theme_id: str = "dark"
        self.current_grid_mode: str = "lines"
        self.current_speed: float = 25.0
        self.current_gain: float = 10.0
        self.current_qtrr_model: str = "linear"
        self.current_hysteresis_mode: str = "exponential"
        self.current_t_end_method: str = "hybrid"
        self._active_worker: Any | None = None
        self._retired_workers: list[Any] = []

        self._setup_ui()
        self._load_synthetic_demo()

    def _setup_ui(self) -> None:
        # ---------------------------------------------------------------------
        # APPLICATION MENU BAR (File, Settings, Help)
        # ---------------------------------------------------------------------
        self.menu_bar = self.menuBar()
        self.menu_bar.setStyleSheet("""
            QMenuBar {
                background-color: #1a1e2e;
                color: #e2e8f0;
                font-weight: 600;
                font-size: 9.5pt;
                border-bottom: 1px solid #2e3650;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background-color: #2563eb;
                color: #ffffff;
            }
            QMenu {
                background-color: #1a1e2e;
                color: #e2e8f0;
                border: 1px solid #2e3650;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2563eb;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #2e3650;
                margin: 4px 8px;
            }
        """)

        # ---------------------------------------------------------------------
        # 1. FILE MENU: open study | export study | close study || exit
        # ---------------------------------------------------------------------
        self.menu_file = self.menu_bar.addMenu(tr("menu_file"))

        self.action_open_study = QAction(tr("menu_open_study"), self)
        self.action_open_study.setShortcut(QKeySequence("Ctrl+O"))
        self.action_open_study.triggered.connect(self._open_file_dialog)
        self.menu_file.addAction(self.action_open_study)
        self.action_import = self.action_open_study  # Compatibility alias

        self.action_export_study = QAction(tr("menu_export_study"), self)
        self.action_export_study.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export_study.triggered.connect(self._export_pecg_dialog)
        self.menu_file.addAction(self.action_export_study)
        self.action_export = self.action_export_study  # Compatibility alias

        self.action_export_pdf = QAction(tr("menu_export_pdf"), self)
        self.action_export_pdf.setShortcut(QKeySequence("Ctrl+P"))
        self.action_export_pdf.triggered.connect(self._export_pdf_dialog)
        self.menu_file.addAction(self.action_export_pdf)

        self.action_close_study = QAction(tr("menu_close_study"), self)
        self.action_close_study.setShortcut(QKeySequence("Ctrl+W"))
        self.action_close_study.triggered.connect(self._close_study)
        self.menu_file.addAction(self.action_close_study)

        self.menu_file.addSeparator()

        self.action_exit = QAction(tr("menu_exit"), self)
        self.action_exit.setShortcut(QKeySequence("Ctrl+Q"))
        self.action_exit.triggered.connect(self.close)
        self.menu_file.addAction(self.action_exit)

        # ---------------------------------------------------------------------
        # 2. PREFERENCES MENU: Languages | Interface theme | Canvas theme | calipers toggle
        # ---------------------------------------------------------------------
        self.menu_preferences = self.menu_bar.addMenu(tr("menu_preferences"))
        self.menu_settings = self.menu_preferences  # Compatibility alias

        # Submenu: Languages ("drop box")
        self.menu_languages = self.menu_preferences.addMenu(tr("menu_languages"))
        self.lang_group = QActionGroup(self)
        self.lang_group.setExclusive(True)
        self.lang_actions: dict[str, QAction] = {}
        curr_lang = get_current_locale()
        for code, name in SUPPORTED_LANGUAGES.items():
            act = QAction(name, self)
            act.setCheckable(True)
            act.setChecked(code == curr_lang)
            act.triggered.connect(lambda checked, c=code: self.set_language(c))
            self.lang_group.addAction(act)
            self.menu_languages.addAction(act)
            self.lang_actions[code] = act

        # Submenu: Interface theme ("drop box")
        self.menu_interface_theme = self.menu_preferences.addMenu(tr("menu_interface_theme"))
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_actions: dict[str, QAction] = {}
        for tid, tspec in THEMES.items():
            act = QAction(tr(tspec["name_key"]), self)
            act.setCheckable(True)
            act.setChecked(tid == self.current_theme_id)
            act.triggered.connect(lambda checked, t=tid: self.set_theme(t))
            self.theme_group.addAction(act)
            self.menu_interface_theme.addAction(act)
            self.theme_actions[tid] = act

        # Submenu: Canvas theme ("drop box")
        self.menu_canvas_theme = self.menu_preferences.addMenu(tr("menu_canvas_theme"))
        self.canvas_theme_group = QActionGroup(self)
        self.canvas_theme_group.setExclusive(True)
        self.canvas_theme_actions: dict[str, QAction] = {}
        for cid, cspec in CANVAS_THEMES.items():
            act = QAction(tr(cspec["name_key"]), self)
            act.setCheckable(True)
            act.setChecked(cid == self.current_canvas_theme_id)
            act.triggered.connect(lambda checked, c=cid: self.set_canvas_theme(c))
            self.canvas_theme_group.addAction(act)
            self.menu_canvas_theme.addAction(act)
            self.canvas_theme_actions[cid] = act

        self.menu_preferences.addSeparator()

        # Calipers "toggle"
        self.action_toggle_calipers = QAction(tr("menu_toggle_calipers"), self)
        self.action_toggle_calipers.setCheckable(True)
        self.action_toggle_calipers.setChecked(True)
        self.action_toggle_calipers.setShortcut(QKeySequence("Ctrl+K"))
        self.action_toggle_calipers.toggled.connect(self._on_menu_calipers_toggled)
        self.menu_preferences.addAction(self.action_toggle_calipers)

        # ---------------------------------------------------------------------
        # 3. HELP MENU: "shortcut link to wiki" | License | about "brand, credits, release version"
        # ---------------------------------------------------------------------
        self.menu_help = self.menu_bar.addMenu(tr("menu_help"))

        # Shortcut link to wiki
        self.action_wiki = QAction(tr("menu_wiki"), self)
        self.action_wiki.setShortcut(QKeySequence("F1"))
        self.action_wiki.triggered.connect(self._open_wiki)
        self.menu_help.addAction(self.action_wiki)
        self.action_help = self.action_wiki  # Compatibility alias

        # License
        self.action_license = QAction(tr("menu_license"), self)
        self.action_license.triggered.connect(self._show_license_dialog)
        self.menu_help.addAction(self.action_license)

        self.menu_help.addSeparator()

        # About ("brand, credits, release version")
        self.action_about = QAction(tr("menu_about"), self)
        self.action_about.triggered.connect(self._show_about_dialog)
        self.menu_help.addAction(self.action_about)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 12, 16, 16)
        root_layout.setSpacing(10)

        # Style sheet: Calm, accessible dark clinical theme
        self.setStyleSheet("""
            QMainWindow { background-color: #0f111a; }
            QWidget { background-color: #0f111a; color: #cbd5e1; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 10pt; }

            /* Top Navigation Bar */
            QFrame#topBar { background-color: #1a1e2e; border: 1px solid #2e3650; border-radius: 8px; padding: 6px 12px; }
            QLabel#appTitle { font-size: 14pt; font-weight: bold; color: #60a5fa; }
            QLabel#fileBadge { background-color: #262c42; color: #94a3b8; border-radius: 4px; padding: 4px 8px; font-size: 9.5pt; font-weight: 500; }

            /* Buttons */
            QPushButton { background-color: #242c44; border: 1px solid #3b4668; border-radius: 6px; padding: 6px 14px; font-weight: 600; color: #e2e8f0; }
            QPushButton:hover { background-color: #313b5c; border-color: #60a5fa; color: #ffffff; }
            QPushButton#btnPrimary { background-color: #2563eb; border: 1px solid #3b82f6; color: #ffffff; }
            QPushButton#btnPrimary:hover { background-color: #1d4ed8; }
            QPushButton#btnSecondary { background-color: #0d9488; border: 1px solid #14b8a6; color: #ffffff; }
            QPushButton#btnSecondary:hover { background-color: #0f766e; }

            /* Dropdowns */
            QComboBox { background-color: #242c44; border: 1px solid #3b4668; border-radius: 6px; padding: 5px 10px; color: #e2e8f0; font-weight: 600; min-width: 120px; }
            QComboBox:hover { border-color: #60a5fa; }
            QComboBox QAbstractItemView { background-color: #1a1e2e; selection-background-color: #2563eb; color: #f8fafc; border: 1px solid #3b4668; }

            /* Card Containers */
            QFrame#kpiCard { background-color: #1a1e2e; border: 1px solid #2e3650; border-radius: 8px; padding: 10px; }
            QLabel#kpiTitle { font-size: 8.5pt; font-weight: bold; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
            QLabel#kpiValue { font-size: 16pt; font-weight: bold; color: #f8fafc; margin-top: 2px; }
            QLabel#kpiSubtext { font-size: 8.5pt; color: #64748b; margin-top: 2px; }

            /* Caliper HUD Strip */
            QFrame#caliperStrip { background-color: #161a29; border: 1px solid #283048; border-radius: 6px; padding: 6px 12px; }
            QLabel#caliperLabel { font-size: 9.5pt; font-weight: 600; color: #94a3b8; }
            QLabel#caliperVal { font-size: 11.5pt; font-weight: bold; color: #f8fafc; }

            /* Tabs & Tables */
            QTabWidget::pane { border: 1px solid #2e3650; background-color: #141724; border-radius: 8px; }
            QTabBar::tab { background: #1a1e2e; color: #94a3b8; padding: 8px 16px; border-top-left-radius: 6px; border-top-right-radius: 6px; font-weight: 600; margin-right: 2px; }
            QTabBar::tab:selected { background: #2563eb; color: #ffffff; }
            QTableWidget { background-color: #141724; border: none; gridline-color: #23293d; selection-background-color: #1e3a8a; selection-color: #ffffff; }
            QHeaderView::section { background-color: #1a1e2e; color: #94a3b8; border: none; border-bottom: 1px solid #2e3650; padding: 6px; font-weight: 600; font-size: 9pt; }
        """)

        self._setup_top_bar(root_layout)
        self._setup_main_splitter(root_layout)
        self._setup_status_bar()

    def _setup_top_bar(self, root_layout: Any) -> None:
        """Builds the top workspace header bar."""
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(8, 4, 8, 4)

        self.title_lbl = QLabel(tr("app_title"))
        self.title_lbl.setObjectName("appTitle")
        top_layout.addWidget(self.title_lbl)

        self.lbl_file_badge = QLabel(self.current_filename)
        self.lbl_file_badge.setObjectName("fileBadge")
        top_layout.addWidget(self.lbl_file_badge)

        top_layout.addStretch()

        # Settings & Preferences Button
        self.btn_settings = QPushButton(tr("btn_settings"))
        self.btn_settings.setObjectName("btnSettings")
        self.btn_settings.setToolTip(tr("btn_settings_tooltip"))
        self.btn_settings.clicked.connect(self._open_settings_dialog)
        top_layout.addWidget(self.btn_settings)

        top_layout.addSpacing(8)

        # Channel Selector Dropdown
        self.lead_lbl = QLabel(tr("channel_label"))
        self.lead_lbl.setStyleSheet("font-weight: 600; color: #94a3b8;")
        top_layout.addWidget(self.lead_lbl)

        self.combo_leads = QComboBox()
        self.combo_leads.currentIndexChanged.connect(self._on_lead_changed)
        top_layout.addWidget(self.combo_leads)

        top_layout.addSpacing(8)

        self.btn_open = QPushButton(tr("btn_open"))
        self.btn_open.setObjectName("btnPrimary")
        self.btn_open.setToolTip(tr("btn_open_tooltip"))
        self.btn_open.clicked.connect(self._open_file_dialog)
        top_layout.addWidget(self.btn_open)

        self.btn_demo = QPushButton(tr("btn_demo"))
        self.btn_demo.setToolTip(tr("btn_demo_tooltip"))
        self.btn_demo.clicked.connect(self._load_synthetic_demo)
        top_layout.addWidget(self.btn_demo)

        self.btn_export = QPushButton(tr("btn_export"))
        self.btn_export.setObjectName("btnSecondary")
        self.btn_export.setToolTip(tr("btn_export_tooltip"))
        self.btn_export.clicked.connect(self._export_pecg_dialog)
        top_layout.addWidget(self.btn_export)

        self.btn_export_pdf = QPushButton(tr("btn_export_pdf"))
        self.btn_export_pdf.setToolTip(tr("btn_export_pdf_tooltip"))
        self.btn_export_pdf.clicked.connect(self._export_pdf_dialog)
        top_layout.addWidget(self.btn_export_pdf)

        root_layout.addWidget(top_bar)

    def _setup_main_splitter(self, root_layout: Any) -> None:
        """Builds the horizontal splitter with waveform canvas and clinical inspector tabs."""
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter, stretch=1)

        # Left / Center Area: Waveform + Canvas Controls + Caliper HUD Strip
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Dedicated Canvas Header Toolbar
        self.canvas_bar = QFrame()
        self.canvas_bar.setObjectName("canvasBar")
        self.canvas_bar.setStyleSheet("""
            QFrame#canvasBar {
                background-color: #161a29;
                border: 1px solid #283048;
                border-radius: 6px;
                padding: 3px 8px;
            }
            QPushButton.toggleBtn {
                background-color: #242c44;
                border: 1px solid #3b4668;
                border-radius: 4px;
                padding: 3px 8px;
                color: #cbd5e1;
                font-weight: 600;
                font-size: 8.5pt;
            }
            QPushButton.toggleBtn:hover {
                background-color: #313b5c;
                border-color: #60a5fa;
                color: #ffffff;
            }
            QPushButton.toggleBtn:checked {
                background-color: #2563eb;
                border: 1px solid #60a5fa;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton.actionBtn {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 3px 7px;
                color: #94a3b8;
                font-weight: 600;
                font-size: 8.5pt;
            }
            QPushButton.actionBtn:hover {
                background-color: #334155;
                color: #ffffff;
                border-color: #60a5fa;
            }
        """)
        c_layout = QHBoxLayout(self.canvas_bar)
        c_layout.setContentsMargins(6, 2, 6, 2)
        c_layout.setSpacing(6)

        self.lbl_canvas_title = QLabel(f"ECG Waveform — {self.current_lead_name}")
        self.lbl_canvas_title.setStyleSheet("font-weight: bold; color: #93c5fd; font-size: 9.5pt;")
        c_layout.addWidget(self.lbl_canvas_title)

        c_layout.addStretch()

        # Canvas Color Scheme Dropdown
        self.lbl_canvas_scheme = QLabel(tr("canvas_theme_label"))
        self.lbl_canvas_scheme.setStyleSheet("font-weight: 600; color: #94a3b8; font-size: 8.5pt;")
        c_layout.addWidget(self.lbl_canvas_scheme)

        self.combo_canvas_theme = QComboBox()
        self.combo_canvas_theme.setToolTip(tr("canvas_theme_tooltip"))
        self.combo_canvas_theme.setStyleSheet("font-size: 8.5pt; min-width: 120px;")
        for cid, ctheme in CANVAS_THEMES.items():
            self.combo_canvas_theme.addItem(tr(ctheme["name_key"]), cid)
        self.combo_canvas_theme.currentIndexChanged.connect(self._on_canvas_theme_dropdown_changed)
        c_layout.addWidget(self.combo_canvas_theme)

        c_layout.addSpacing(4)

        # Grid Toggle Buttons Group (Lines, Dots, Off)
        self.lbl_grid = QLabel(tr("grid_style_label"))
        self.lbl_grid.setStyleSheet("font-weight: 600; color: #94a3b8; font-size: 8.5pt;")
        c_layout.addWidget(self.lbl_grid)

        self.grid_group = QButtonGroup(self)
        self.grid_group.setExclusive(True)

        self.btn_grid_lines = QPushButton(tr("grid_btn_lines"))
        self.btn_grid_lines.setProperty("class", "toggleBtn")
        self.btn_grid_lines.setCheckable(True)
        self.btn_grid_lines.setChecked(True)
        self.btn_grid_lines.setToolTip(tr("grid_lines_tooltip"))
        self.btn_grid_lines.clicked.connect(lambda: self.set_grid_mode("lines"))
        self.grid_group.addButton(self.btn_grid_lines)
        c_layout.addWidget(self.btn_grid_lines)

        self.btn_grid_dots = QPushButton(tr("grid_btn_dots"))
        self.btn_grid_dots.setProperty("class", "toggleBtn")
        self.btn_grid_dots.setCheckable(True)
        self.btn_grid_dots.setToolTip(tr("grid_dots_tooltip"))
        self.btn_grid_dots.clicked.connect(lambda: self.set_grid_mode("dots"))
        self.grid_group.addButton(self.btn_grid_dots)
        c_layout.addWidget(self.btn_grid_dots)

        self.btn_grid_off = QPushButton(tr("grid_btn_off"))
        self.btn_grid_off.setProperty("class", "toggleBtn")
        self.btn_grid_off.setCheckable(True)
        self.btn_grid_off.setToolTip(tr("grid_off_tooltip"))
        self.btn_grid_off.clicked.connect(lambda: self.set_grid_mode("none"))
        self.grid_group.addButton(self.btn_grid_off)
        c_layout.addWidget(self.btn_grid_off)

        c_layout.addSpacing(4)

        # Calipers / Draggable Vertical Lines Controls
        self.btn_calipers_toggle = QPushButton(tr("calipers_btn_toggle"))
        self.btn_calipers_toggle.setProperty("class", "toggleBtn")
        self.btn_calipers_toggle.setCheckable(True)
        self.btn_calipers_toggle.setChecked(True)
        self.btn_calipers_toggle.setToolTip(tr("calipers_toggle_tooltip"))
        self.btn_calipers_toggle.toggled.connect(self._on_calipers_toggled)
        c_layout.addWidget(self.btn_calipers_toggle)

        self.btn_calipers_center = QPushButton(tr("calipers_btn_center"))
        self.btn_calipers_center.setProperty("class", "actionBtn")
        self.btn_calipers_center.setToolTip(tr("calipers_center_tooltip"))
        self.btn_calipers_center.clicked.connect(self._on_calipers_center_clicked)
        c_layout.addWidget(self.btn_calipers_center)

        self.btn_add_line = QPushButton(tr("calipers_btn_add"))
        self.btn_add_line.setProperty("class", "actionBtn")
        self.btn_add_line.setToolTip(tr("calipers_add_tooltip"))
        self.btn_add_line.clicked.connect(self._on_add_line_clicked)
        c_layout.addWidget(self.btn_add_line)

        self.btn_prev_beat = QPushButton("◀")
        self.btn_prev_beat.setProperty("class", "actionBtn")
        self.btn_prev_beat.setToolTip(tr("prev_beat_tooltip"))
        self.btn_prev_beat.clicked.connect(self.prev_beat)
        c_layout.addWidget(self.btn_prev_beat)

        self.btn_next_beat = QPushButton("▶")
        self.btn_next_beat.setProperty("class", "actionBtn")
        self.btn_next_beat.setToolTip(tr("next_beat_tooltip"))
        self.btn_next_beat.clicked.connect(self.next_beat)
        c_layout.addWidget(self.btn_next_beat)

        self._setup_keyboard_shortcuts()

        c_layout.addSpacing(4)

        # Clinical Zoom & Scale Controls
        self.lbl_zoom = QLabel(tr("zoom_label"))
        self.lbl_zoom.setStyleSheet("font-weight: 600; color: #94a3b8; font-size: 8.5pt;")
        c_layout.addWidget(self.lbl_zoom)

        self.combo_speed = QComboBox()
        self.combo_speed.setToolTip(tr("speed_tooltip"))
        self.combo_speed.setStyleSheet("font-size: 8.5pt; min-width: 85px;")
        for spd in CLINICAL_SPEEDS:
            spd_label = f"{int(spd) if spd.is_integer() else spd} mm/s"
            if spd == 25.0:
                spd_label += " (Std)"
            self.combo_speed.addItem(spd_label, spd)
        self.combo_speed.setCurrentIndex(1)  # 25.0 mm/s
        self.combo_speed.currentIndexChanged.connect(self._on_speed_changed)
        c_layout.addWidget(self.combo_speed)

        self.combo_gain = QComboBox()
        self.combo_gain.setToolTip(tr("gain_tooltip"))
        self.combo_gain.setStyleSheet("font-size: 8.5pt; min-width: 85px;")
        for gn in CLINICAL_GAINS:
            gn_label = f"{int(gn) if gn.is_integer() else gn} mm/mV"
            if gn == 10.0:
                gn_label += " (Std)"
            self.combo_gain.addItem(gn_label, gn)
        self.combo_gain.setCurrentIndex(2)  # 10.0 mm/mV
        self.combo_gain.currentIndexChanged.connect(self._on_gain_changed)
        c_layout.addWidget(self.combo_gain)

        self.btn_zoom_out = QPushButton("−")
        self.btn_zoom_out.setProperty("class", "actionBtn")
        self.btn_zoom_out.setToolTip(tr("zoom_out_tooltip"))
        self.btn_zoom_out.clicked.connect(self._on_zoom_out_clicked)
        c_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setProperty("class", "actionBtn")
        self.btn_zoom_in.setToolTip(tr("zoom_in_tooltip"))
        self.btn_zoom_in.clicked.connect(self._on_zoom_in_clicked)
        c_layout.addWidget(self.btn_zoom_in)

        self.btn_zoom_reset = QPushButton("1:1")
        self.btn_zoom_reset.setProperty("class", "actionBtn")
        self.btn_zoom_reset.setToolTip(tr("zoom_reset_tooltip"))
        self.btn_zoom_reset.clicked.connect(self._on_zoom_reset_clicked)
        c_layout.addWidget(self.btn_zoom_reset)

        self.btn_zoom_fit = QPushButton("⤢")
        self.btn_zoom_fit.setProperty("class", "actionBtn")
        self.btn_zoom_fit.setToolTip(tr("zoom_fit_tooltip"))
        self.btn_zoom_fit.clicked.connect(self._on_zoom_fit_clicked)
        c_layout.addWidget(self.btn_zoom_fit)

        c_layout.addSpacing(6)

        # Scale Badge (Visible ONLY when grid is enabled)
        self.lbl_scale_badge = QLabel(f"📐 {tr('canvas_scale_badge')}")
        self.lbl_scale_badge.setStyleSheet("""
            QLabel {
                background-color: #1a1e2e;
                color: #38bdf8;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                padding: 3px 8px;
                font-weight: bold;
                font-size: 8.5pt;
            }
        """)
        c_layout.addWidget(self.lbl_scale_badge)

        left_layout.addWidget(self.canvas_bar)

        try:
            self.ecg_plot = ECGPlotWidget(self)
        except ImportError:
            self.ecg_plot = _QMock()
        self.ecg_plot.on_caliper_moved = self._on_caliper_dragged
        left_layout.addWidget(self.ecg_plot.plot_widget, stretch=1)

        # Caliper HUD Strip
        cal_strip = QFrame()
        cal_strip.setObjectName("caliperStrip")
        cal_layout = QHBoxLayout(cal_strip)
        cal_layout.setContentsMargins(14, 6, 14, 6)
        cal_layout.setSpacing(20)

        self.lbl_cal_cue = QLabel(tr("calipers_title"))
        self.lbl_cal_cue.setObjectName("caliperLabel")
        cal_layout.addWidget(self.lbl_cal_cue)

        self.lbl_tag_raw = QLabel(tr("cal_raw_qt"))
        self.lbl_cal_qt = QLabel("-- ms")
        self.lbl_cal_qt.setObjectName("caliperVal")
        self.lbl_cal_qt.setStyleSheet("color: #fbbf24;")
        cal_layout.addWidget(self.lbl_tag_raw)
        cal_layout.addWidget(self.lbl_cal_qt)

        self.lbl_tag_rr = QLabel(tr("cal_rr"))
        self.lbl_cal_rr = QLabel("-- ms")
        self.lbl_cal_rr.setObjectName("caliperVal")
        self.lbl_cal_rr.setStyleSheet("color: #34d399;")
        cal_layout.addWidget(self.lbl_tag_rr)
        cal_layout.addWidget(self.lbl_cal_rr)

        self.lbl_tag_bazett = QLabel(tr("cal_bazett"))
        self.lbl_cal_bazett = QLabel("-- ms")
        self.lbl_cal_bazett.setObjectName("caliperVal")
        self.lbl_cal_bazett.setStyleSheet("color: #60a5fa;")
        cal_layout.addWidget(self.lbl_tag_bazett)
        cal_layout.addWidget(self.lbl_cal_bazett)

        self.lbl_tag_fridericia = QLabel(tr("cal_fridericia"))
        self.lbl_cal_fridericia = QLabel("-- ms")
        self.lbl_cal_fridericia.setObjectName("caliperVal")
        self.lbl_cal_fridericia.setStyleSheet("color: #c084fc;")
        cal_layout.addWidget(self.lbl_tag_fridericia)
        cal_layout.addWidget(self.lbl_cal_fridericia)

        cal_layout.addStretch()

        self.help_cue = QLabel(tr("cal_tip"))
        self.help_cue.setStyleSheet("color: #64748b; font-size: 8.5pt; font-style: italic;")
        cal_layout.addWidget(self.help_cue)

        left_layout.addWidget(cal_strip)
        splitter.addWidget(left_container)

        # Right Area: Clean Tabbed Clinical Inspector
        sidebar = QWidget()
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)

        self.tabs = QTabWidget()

        # -----------------------------------------------------------------
        # TAB 1: OVERVIEW & HEALTH KPI CARDS
        # -----------------------------------------------------------------
        overview_tab = QWidget()
        ov_layout = QVBoxLayout(overview_tab)
        ov_layout.setContentsMargins(12, 12, 12, 12)
        ov_layout.setSpacing(8)

        self.card_hr = self._create_kpi_card(tr("kpi_hr_title"), "-- BPM", tr("hr_sub_normal"))
        ov_layout.addWidget(self.card_hr)

        self.card_qtc = self._create_kpi_card(tr("kpi_qtc_title"), "-- ms", tr("qtc_sub_normal"))
        ov_layout.addWidget(self.card_qtc)

        self.card_ectopic = self._create_kpi_card(tr("kpi_ectopic_title"), "0.0%", tr("ect_sub_normal"))
        ov_layout.addWidget(self.card_ectopic)

        self.card_sqi = self._create_kpi_card(tr("kpi_sqi_title"), "Good", tr("sqi_sub_clean", snr=20.0))
        ov_layout.addWidget(self.card_sqi)

        self.card_qtd = self._create_kpi_card(tr("kpi_qtd_title"), "N/A", tr("qtd_sub_single"))
        ov_layout.addWidget(self.card_qtd)

        # Advanced Section
        self.adv_group = QGroupBox(tr("adv_group_title"))
        adv_layout = QVBoxLayout(self.adv_group)
        adv_layout.setSpacing(4)
        self.lbl_adv_qtvi = QLabel(tr("adv_qtvi", val="--"))
        self.lbl_adv_qtrr = QLabel(tr("adv_qtrr", val="--"))
        self.lbl_adv_hyst = QLabel(tr("adv_hyst_na", val="--"))
        self.lbl_adv_hrv = QLabel(tr("adv_hrv_na", val="--"))
        self.lbl_adv_hrt = QLabel(tr("adv_hrt_na", val="--"))
        self.lbl_adv_twa = QLabel(tr("adv_twa_na", val="--"))
        self.lbl_adv_total = QLabel(tr("adv_total_cycles", count="--"))
        for lbl in (
            self.lbl_adv_qtvi,
            self.lbl_adv_qtrr,
            self.lbl_adv_hyst,
            self.lbl_adv_hrv,
            self.lbl_adv_hrt,
            self.lbl_adv_twa,
            self.lbl_adv_total,
        ):
            lbl.setStyleSheet("font-size: 9pt; color: #94a3b8;")
            adv_layout.addWidget(lbl)
        ov_layout.addWidget(self.adv_group)

        ov_layout.addStretch()
        self.tabs.addTab(overview_tab, tr("tab_overview"))

        # -----------------------------------------------------------------
        # TAB 2: CLINICAL EVENTS DIARY
        # -----------------------------------------------------------------
        events_tab = QWidget()
        ev_layout = QVBoxLayout(events_tab)
        ev_layout.setContentsMargins(8, 8, 8, 8)
        self.events_table = QTableWidget(0, 4)
        self.events_table.setHorizontalHeaderLabels([
            tr("hdr_time"), tr("hdr_event"), tr("hdr_value"), tr("hdr_severity")
        ])
        self.events_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.events_table.cellClicked.connect(self._on_event_selected)
        ev_layout.addWidget(self.events_table)
        self.tabs.addTab(events_tab, tr("tab_events"))

        # -----------------------------------------------------------------
        # TAB 3: CYCLE-BY-CYCLE BEAT INSPECTOR (AAMI)
        # -----------------------------------------------------------------
        beats_tab = QWidget()
        b_layout = QVBoxLayout(beats_tab)
        b_layout.setContentsMargins(8, 8, 8, 8)
        self.beat_table = QTableWidget(0, 8)
        self.beat_table.setHorizontalHeaderLabels([
            tr("hdr_beat_num"),
            tr("hdr_time"),
            tr("hdr_class"),
            tr("hdr_pattern"),
            tr("hdr_rr"),
            tr("hdr_hr"),
            tr("hdr_qt"),
            tr("hdr_qtc"),
        ])
        self.beat_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.beat_table.cellClicked.connect(self._on_beat_selected)
        self.beat_table.cellDoubleClicked.connect(self._on_beat_double_clicked)
        b_layout.addWidget(self.beat_table)
        self.tabs.addTab(beats_tab, tr("tab_beats"))

        # -----------------------------------------------------------------
        # TAB 4: INTERACTIVE QT-RR RESTITUTION & HYSTERESIS VISUALIZATION
        # -----------------------------------------------------------------
        qtrr_tab = QWidget()
        qtrr_layout = QVBoxLayout(qtrr_tab)
        qtrr_layout.setContentsMargins(8, 8, 8, 8)
        qtrr_layout.setSpacing(6)

        # Interactive Model & Hysteresis Selector Bar
        qtrr_ctrl_bar = QHBoxLayout()
        qtrr_ctrl_bar.setSpacing(6)

        self.lbl_tab_qtrr_model = QLabel(tr("qtrr_lbl_model"))
        self.lbl_tab_qtrr_model.setStyleSheet("font-weight: 600; color: #94a3b8; font-size: 8.5pt;")
        qtrr_ctrl_bar.addWidget(self.lbl_tab_qtrr_model)

        self.combo_tab_qtrr_model = QComboBox()
        self.combo_tab_qtrr_model.setStyleSheet("font-size: 8.5pt; min-width: 145px;")
        self.combo_tab_qtrr_model.addItem(tr("qtrr_auto_best"), "auto_best")
        for m_id in SUPPORTED_QTRR_MODELS:
            self.combo_tab_qtrr_model.addItem(QTRR_MODEL_METADATA[m_id]["label"], m_id)
        self.combo_tab_qtrr_model.setCurrentIndex(1)  # 'linear' default
        self.combo_tab_qtrr_model.currentIndexChanged.connect(self._on_tab_qtrr_model_changed)
        qtrr_ctrl_bar.addWidget(self.combo_tab_qtrr_model, stretch=1)

        self.lbl_tab_hyst_mode = QLabel(tr("qtrr_lbl_hyst"))
        self.lbl_tab_hyst_mode.setStyleSheet("font-weight: 600; color: #94a3b8; font-size: 8.5pt;")
        qtrr_ctrl_bar.addWidget(self.lbl_tab_hyst_mode)

        self.combo_tab_hyst_mode = QComboBox()
        self.combo_tab_hyst_mode.setStyleSheet("font-size: 8.5pt; min-width: 120px;")
        self.combo_tab_hyst_mode.addItem("EW (RR_eff)", "exponential")
        self.combo_tab_hyst_mode.addItem("LW (RR_eff)", "linear")
        self.combo_tab_hyst_mode.addItem("Raw (Instant RR)", "raw")
        self.combo_tab_hyst_mode.setCurrentIndex(0)
        self.combo_tab_hyst_mode.currentIndexChanged.connect(self._on_tab_hyst_mode_changed)
        qtrr_ctrl_bar.addWidget(self.combo_tab_hyst_mode)

        qtrr_layout.addLayout(qtrr_ctrl_bar)

        # Interactive PyQtGraph QT-RR Restitution & Hysteresis Cloud Plot
        self.qtrr_plot_widget = pg.PlotWidget()
        self.qtrr_plot_widget.setBackground("#13151f")
        self.qtrr_plot_widget.showGrid(x=True, y=True, alpha=0.22)
        self.qtrr_plot_widget.setLabel("bottom", tr("qtrr_axis_rr"))
        self.qtrr_plot_widget.setLabel("left", tr("qtrr_axis_qt"))
        self.qtrr_plot_widget.setMinimumHeight(210)

        self.qtrr_raw_scatter = pg.ScatterPlotItem(
            size=6,
            pen=pg.mkPen(None),
            brush=pg.mkBrush(148, 163, 184, 110),
            name="Raw (RR, QT)",
        )
        self.qtrr_eff_scatter = pg.ScatterPlotItem(
            size=8,
            pen=pg.mkPen("#0f172a", width=0.8),
            brush=pg.mkBrush("#38bdf8"),
            name="Compensated (RR_eff, QT)",
        )
        self.qtrr_fit_curve = self.qtrr_plot_widget.plot(
            [], [], pen=pg.mkPen("#fbbf24", width=2.4), name="Restitution Fit"
        )
        self.qtrr_ref_scatter = pg.ScatterPlotItem(
            size=12,
            symbol="star",
            pen=pg.mkPen("#ffffff", width=1.2),
            brush=pg.mkBrush("#34d399"),
            name="QTc,ind (RR=1.0s)",
        )
        self.qtrr_plot_widget.addItem(self.qtrr_raw_scatter)
        self.qtrr_plot_widget.addItem(self.qtrr_eff_scatter)
        self.qtrr_plot_widget.addItem(self.qtrr_ref_scatter)
        qtrr_layout.addWidget(self.qtrr_plot_widget, stretch=1)

        # Live Equation, Hysteresis Lag (lambda*, t90) & Individualized QTc Banner
        self.lbl_qtrr_summary_banner = QLabel(tr("qtrr_banner_ready"))
        self.lbl_qtrr_summary_banner.setWordWrap(True)
        self.lbl_qtrr_summary_banner.setStyleSheet(
            "background-color: #1a1e2e; border: 1px solid #2e3650; border-radius: 6px; "
            "padding: 6px 8px; font-size: 8.5pt; color: #e2e8f0;"
        )
        qtrr_layout.addWidget(self.lbl_qtrr_summary_banner)

        # 10-Model Comparative Ranking Table (Click row to switch active model)
        self.qtrr_models_table = QTableWidget(0, 8)
        self.qtrr_models_table.setHorizontalHeaderLabels([
            tr("qtrr_hdr_model"),
            tr("qtrr_hdr_eq"),
            tr("qtrr_hdr_slope"),
            tr("qtrr_hdr_r"),
            tr("qtrr_hdr_r2"),
            tr("qtrr_hdr_rmse"),
            tr("qtrr_hdr_aic"),
            tr("qtrr_hdr_qtc_ind"),
        ])
        self.qtrr_models_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.qtrr_models_table.setMinimumHeight(145)
        self.qtrr_models_table.cellClicked.connect(self._on_qtrr_table_row_clicked)
        qtrr_layout.addWidget(self.qtrr_models_table)

        self.tabs.addTab(qtrr_tab, tr("tab_qtrr"))

        # -----------------------------------------------------------------
        # TAB 5: HOLTER TRIAGE (Hourly Trends & AF Burden)
        # -----------------------------------------------------------------
        holter_tab = QWidget()
        holter_layout = QVBoxLayout(holter_tab)
        holter_layout.setContentsMargins(8, 8, 8, 8)
        holter_layout.setSpacing(6)

        self.lbl_holter_summary_banner = QLabel(tr("holter_summary_ready"))
        self.lbl_holter_summary_banner.setWordWrap(True)
        self.lbl_holter_summary_banner.setStyleSheet(
            "background-color: #1a1e2e; border: 1px solid #2e3650; border-radius: 6px; "
            "padding: 6px 8px; font-size: 8.5pt; color: #e2e8f0;"
        )
        holter_layout.addWidget(self.lbl_holter_summary_banner)

        self.holter_trends_table = QTableWidget(0, 8)
        self.holter_trends_table.setHorizontalHeaderLabels([
            tr("holter_hdr_hour"),
            tr("holter_hdr_beats"),
            tr("holter_hdr_hr"),
            tr("holter_hdr_pvc"),
            tr("holter_hdr_pac"),
            tr("holter_hdr_runs"),
            tr("holter_hdr_pauses"),
            tr("holter_hdr_af"),
        ])
        self.holter_trends_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.holter_trends_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.holter_trends_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.holter_trends_table.cellClicked.connect(self._on_holter_hour_clicked)
        holter_layout.addWidget(self.holter_trends_table, stretch=2)

        self.holter_af_table = QTableWidget(0, 8)
        self.holter_af_table.setHorizontalHeaderLabels([
            tr("af_hdr_ep"),
            tr("af_hdr_start"),
            tr("af_hdr_end"),
            tr("af_hdr_dur"),
            tr("af_hdr_hr"),
            tr("af_hdr_max_hr"),
            tr("af_hdr_entropy"),
            tr("af_hdr_irreg"),
        ])
        self.holter_af_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.holter_af_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.holter_af_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.holter_af_table.cellClicked.connect(self._on_holter_af_clicked)
        holter_layout.addWidget(self.holter_af_table, stretch=1)

        self.tabs.addTab(holter_tab, tr("tab_holter"))

        # -----------------------------------------------------------------
        # TAB 5: STUDY & PATIENT METADATA (Demographics & Clinical Context) - LAST TAB
        # -----------------------------------------------------------------
        metadata_tab = QWidget()
        meta_layout = QVBoxLayout(metadata_tab)
        meta_layout.setContentsMargins(8, 8, 8, 8)
        meta_layout.setSpacing(6)

        scroll_meta = QScrollArea()
        scroll_meta.setWidgetResizable(True)
        scroll_meta.setFrameShape(QFrame.Shape.NoFrame)
        scroll_meta.setStyleSheet("background-color: transparent;")

        scroll_content = QWidget()
        scroll_vbox = QVBoxLayout(scroll_content)
        scroll_vbox.setContentsMargins(2, 2, 2, 2)
        scroll_vbox.setSpacing(8)

        # Patient Demographics GroupBox
        self.grp_a_box = QGroupBox(tr("group_a_title"))
        grp_a_vbox = QVBoxLayout(self.grp_a_box)
        grp_a_vbox.setContentsMargins(8, 8, 8, 8)
        self.meta_table_a = QTableWidget(0, 2)
        self.meta_table_a.setHorizontalHeaderLabels([tr("hdr_field"), tr("hdr_value")])
        self.meta_table_a.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.meta_table_a.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.meta_table_a.verticalHeader().setVisible(False)
        self.meta_table_a.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.meta_table_a.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.meta_table_a.setMinimumHeight(135)
        grp_a_vbox.addWidget(self.meta_table_a)
        scroll_vbox.addWidget(self.grp_a_box)

        # Clinical Context & Study Specs GroupBox
        self.grp_b_box = QGroupBox(tr("group_b_title"))
        grp_b_vbox = QVBoxLayout(self.grp_b_box)
        grp_b_vbox.setContentsMargins(8, 8, 8, 8)
        self.meta_table_b = QTableWidget(0, 2)
        self.meta_table_b.setHorizontalHeaderLabels([tr("hdr_field"), tr("hdr_value")])
        self.meta_table_b.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.meta_table_b.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.meta_table_b.verticalHeader().setVisible(False)
        self.meta_table_b.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.meta_table_b.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.meta_table_b.setMinimumHeight(260)
        grp_b_vbox.addWidget(self.meta_table_b)
        scroll_vbox.addWidget(self.grp_b_box)

        scroll_vbox.addStretch()
        scroll_meta.setWidget(scroll_content)
        meta_layout.addWidget(scroll_meta)

        self.tabs.addTab(metadata_tab, tr("tab_metadata"))

        side_layout.addWidget(self.tabs)
        splitter.addWidget(sidebar)

        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)

    def _setup_status_bar(self) -> None:
        """Builds the bottom application status bar and background progress bar."""
        self.status_bar = self.statusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #1a1e2e;
                color: #94a3b8;
                font-size: 9pt;
                border-top: 1px solid #2e3650;
                padding: 2px 6px;
            }
        """)
        self.lbl_status_msg = QLabel(tr("status_ready"))
        self.lbl_status_msg.setStyleSheet("color: #cbd5e1; font-weight: 500;")
        self.status_progress = QProgressBar()
        self.status_progress.setRange(0, 100)
        self.status_progress.setTextVisible(True)
        self.status_progress.setFixedWidth(220)
        self.status_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3b4668;
                border-radius: 4px;
                background-color: #0f111a;
                text-align: center;
                color: #f8fafc;
                font-size: 8.5pt;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #2563eb;
                border-radius: 3px;
            }
        """)
        self.status_progress.hide()
        self.status_bar.addWidget(self.lbl_status_msg, 1)
        self.status_bar.addPermanentWidget(self.status_progress, 0)

    def _create_kpi_card(self, title: str, initial_val: str, subtext: str) -> QFrame:
        """Helper to create human-friendly, uncluttered KPI health cards."""
        card = QFrame()
        card.setObjectName("kpiCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("kpiTitle")
        val_lbl = QLabel(initial_val)
        val_lbl.setObjectName("kpiValue")
        sub_lbl = QLabel(subtext)
        sub_lbl.setObjectName("kpiSubtext")

        layout.addWidget(title_lbl)
        layout.addWidget(val_lbl)
        layout.addWidget(sub_lbl)

        card.title_lbl = title_lbl
        card.val_lbl = val_lbl
        card.sub_lbl = sub_lbl
        return card

    def _open_settings_dialog(self) -> None:
        """Opens the modal Settings & Preferences dialog."""
        dialog = SettingsDialog(self)
        dialog.exec()

    def _close_study(self) -> None:
        """Closes the active study and resets all waveform and clinical inspector panes."""
        self.multi_lead_signals.clear()
        self.current_filename = tr("no_study_loaded")
        self.lbl_file_badge.setText(self.current_filename)
        self.lbl_canvas_title.setText(tr("no_active_lead"))
        self.analysis_results = None
        self.annotation_manager = None
        self.current_metadata.clear()

        # Clear waveform plot & scatter
        self.ecg_plot.signal_curve.clear()
        self.ecg_plot.r_peak_scatter.clear()
        self.ecg_plot.clear_ectopic_markers()
        self.ecg_plot.clear_extra_vertical_lines()

        # Reset KPI cards
        self.card_hr.val_lbl.setText("-- BPM")
        self.card_hr.sub_lbl.setText(tr("hr_sub_normal"))
        self.card_qtc.val_lbl.setText("-- ms")
        self.card_qtc.sub_lbl.setText(tr("qtc_sub_normal"))
        self.card_ectopic.val_lbl.setText("0.0%")
        self.card_ectopic.sub_lbl.setText(tr("ect_sub_normal"))
        self.card_sqi.val_lbl.setText("--")
        self.card_sqi.sub_lbl.setText(tr("sqi_sub_clean", snr=0.0))

        # Reset caliper strip values
        self.lbl_cal_qt.setText("-- ms")
        if hasattr(self, "lbl_cal_rr"):
            self.lbl_cal_rr.setText("-- ms")
        self.lbl_cal_bazett.setText("-- ms")
        self.lbl_cal_fridericia.setText("-- ms")

        # Clear tables
        self.events_table.setRowCount(0)
        self.beat_table.setRowCount(0)
        self.meta_table_a.setRowCount(0)
        self.meta_table_b.setRowCount(0)
        if hasattr(self, "holter_trends_table"):
            self.holter_trends_table.setRowCount(0)
        if hasattr(self, "holter_af_table"):
            self.holter_af_table.setRowCount(0)

        # Clear lead dropdown
        self.combo_leads.blockSignals(True)
        self.combo_leads.clear()
        self.combo_leads.blockSignals(False)

        # Reset advanced group
        self.lbl_adv_qtvi.setText(tr("adv_qtvi", val="--"))
        self.lbl_adv_qtrr.setText(tr("adv_qtrr", val="--"))
        self.lbl_adv_hyst.setText(tr("adv_hyst_na", val="--"))
        self.lbl_adv_hrv.setText(tr("adv_hrv_na", val="--"))
        self.lbl_adv_hrt.setText(tr("adv_hrt_na", val="--"))
        self.lbl_adv_twa.setText(tr("adv_twa_na", val="--"))
        self.lbl_adv_total.setText(tr("adv_total_cycles", count="--"))

    def _open_wiki(self) -> None:
        """Opens workstation documentation wiki via desktop browser or accessible modal guide."""
        wiki_url = "https://github.com/numbecho/repolaris/wiki"
        with contextlib.suppress(Exception):
            QDesktopServices.openUrl(QUrl(wiki_url))
        self._show_help_dialog()

    def _show_license_dialog(self) -> None:
        """Displays Apache-2.0 open-source software license dialog."""
        license_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "LICENSE")
        license_text = ""
        if os.path.exists(license_path):
            with contextlib.suppress(OSError), open(license_path, encoding="utf-8") as f:
                license_text = f.read()
        if not license_text:
            license_text = tr("license_dialog_text")
        QMessageBox.information(self, tr("license_dialog_title"), license_text)

    def _show_about_dialog(self) -> None:
        """Displays About dialog with brand, credits, release version, and electrophysiology compliance."""
        QMessageBox.about(self, tr("about_title"), tr("about_text"))

    def _show_help_dialog(self) -> None:
        """Displays clinical reference and keyboard shortcuts help dialog."""
        QMessageBox.information(self, tr("help_dialog_title"), tr("help_dialog_text"))

    def set_theme(self, theme_id: str) -> None:
        """Applies chosen visual theme (Dark, Light, Color Blind Friendly) across all application widgets."""
        if theme_id not in THEMES:
            return
        self.current_theme_id = theme_id
        theme = THEMES[theme_id]
        self.setStyleSheet(theme["qss"])
        # If user hasn't explicitly customized canvas, match canvas to app theme
        if self.current_canvas_theme_id in ("dark", "light", "colorblind"):
            self.set_canvas_theme(theme_id)
        if hasattr(self, "theme_actions") and theme_id in self.theme_actions:
            self.theme_actions[theme_id].blockSignals(True)
            self.theme_actions[theme_id].setChecked(True)
            self.theme_actions[theme_id].blockSignals(False)
        if self.analysis_results:
            self._update_cards_and_tables()

    def set_canvas_theme(self, canvas_theme_id: str) -> None:
        """Applies independent canvas color scheme to the waveform plot, calipers, and badges."""
        if canvas_theme_id not in CANVAS_THEMES:
            return
        self.current_canvas_theme_id = canvas_theme_id
        ctheme = CANVAS_THEMES[canvas_theme_id]
        self.ecg_plot.apply_canvas_theme(ctheme)

        # Synchronize toolbar dropdown
        self.combo_canvas_theme.blockSignals(True)
        for i in range(self.combo_canvas_theme.count()):
            if self.combo_canvas_theme.itemData(i) == canvas_theme_id:
                self.combo_canvas_theme.setCurrentIndex(i)
                break
        self.combo_canvas_theme.blockSignals(False)

        if hasattr(self, "canvas_theme_actions") and canvas_theme_id in self.canvas_theme_actions:
            self.canvas_theme_actions[canvas_theme_id].blockSignals(True)
            self.canvas_theme_actions[canvas_theme_id].setChecked(True)
            self.canvas_theme_actions[canvas_theme_id].blockSignals(False)
        # Update scale badge styling on canvas bar
        self.lbl_scale_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {ctheme.get("badge_bg", "#1a1e2e")};
                color: {ctheme.get("badge_text", "#38bdf8")};
                border: 1px solid {ctheme.get("badge_border", "#38bdf8")};
                border-radius: 4px;
                padding: 3px 8px;
                font-weight: bold;
                font-size: 8.5pt;
            }}
        """)

    def set_grid_mode(self, grid_mode: str) -> None:
        """Applies grid mode (lines, dots, or none).
        Scale label and value are ONLY shown if grid is enabled."""
        self.current_grid_mode = grid_mode
        self.ecg_plot.apply_grid(grid_mode)

        # Scale label and value visibility
        is_grid_enabled = (grid_mode != "none")
        self.lbl_scale_badge.setVisible(is_grid_enabled)
        if hasattr(self.ecg_plot, "scale_corner_label") and self.ecg_plot.scale_corner_label is not None:
            self.ecg_plot.scale_corner_label.setVisible(is_grid_enabled)

        # Sync toggle buttons
        if hasattr(self, "btn_grid_lines"):
            self.btn_grid_lines.blockSignals(True)
            self.btn_grid_dots.blockSignals(True)
            self.btn_grid_off.blockSignals(True)
            if grid_mode == "lines":
                self.btn_grid_lines.setChecked(True)
            elif grid_mode == "dots":
                self.btn_grid_dots.setChecked(True)
            else:
                self.btn_grid_off.setChecked(True)
            self.btn_grid_lines.blockSignals(False)
            self.btn_grid_dots.blockSignals(False)
            self.btn_grid_off.blockSignals(False)

    def _on_canvas_theme_dropdown_changed(self, index: int) -> None:
        if index < 0:
            return
        cid = self.combo_canvas_theme.itemData(index)
        if cid:
            self.set_canvas_theme(cid)

    def _on_calipers_toggled(self, checked: bool) -> None:
        self.ecg_plot.set_calipers_visible(checked)
        if hasattr(self, "cal_strip"):
            self.cal_strip.setEnabled(checked)
        if hasattr(self, "action_toggle_calipers"):
            self.action_toggle_calipers.blockSignals(True)
            self.action_toggle_calipers.setChecked(checked)
            self.action_toggle_calipers.blockSignals(False)

    def _on_menu_calipers_toggled(self, checked: bool) -> None:
        if hasattr(self, "btn_calipers_toggle"):
            self.btn_calipers_toggle.setChecked(checked)
        else:
            self._on_calipers_toggled(checked)

    def _on_calipers_center_clicked(self) -> None:
        self.ecg_plot.center_calipers()

    def _on_add_line_clicked(self) -> None:
        self.ecg_plot.add_draggable_vertical_line()

    def _on_speed_changed(self, index: int) -> None:
        if index < 0:
            return
        spd = self.combo_speed.itemData(index)
        if spd:
            self.current_speed = float(spd)
            self.ecg_plot.set_scale(self.current_speed, self.current_gain)
            self._update_scale_badge_display()

    def _on_gain_changed(self, index: int) -> None:
        if index < 0:
            return
        gn = self.combo_gain.itemData(index)
        if gn:
            self.current_gain = float(gn)
            self.ecg_plot.set_scale(self.current_speed, self.current_gain)
            self._update_scale_badge_display()

    def _on_zoom_in_clicked(self) -> None:
        self.ecg_plot.zoom_in()
        self.current_speed = self.ecg_plot.current_speed
        self.current_gain = self.ecg_plot.current_gain
        self._sync_zoom_combos()
        self._update_scale_badge_display()

    def _on_zoom_out_clicked(self) -> None:
        self.ecg_plot.zoom_out()
        self.current_speed = self.ecg_plot.current_speed
        self.current_gain = self.ecg_plot.current_gain
        self._sync_zoom_combos()
        self._update_scale_badge_display()

    def _on_zoom_reset_clicked(self) -> None:
        self.ecg_plot.zoom_reset()
        self.current_speed = 25.0
        self.current_gain = 10.0
        self._sync_zoom_combos()
        self._update_scale_badge_display()

    def _on_zoom_fit_clicked(self) -> None:
        self.ecg_plot.zoom_fit()
        self._update_scale_badge_display()

    def _sync_zoom_combos(self) -> None:
        if hasattr(self, "combo_speed"):
            self.combo_speed.blockSignals(True)
            for i in range(self.combo_speed.count()):
                if self.combo_speed.itemData(i) == self.current_speed:
                    self.combo_speed.setCurrentIndex(i)
                    break
            self.combo_speed.blockSignals(False)

        if hasattr(self, "combo_gain"):
            self.combo_gain.blockSignals(True)
            for i in range(self.combo_gain.count()):
                if self.combo_gain.itemData(i) == self.current_gain:
                    self.combo_gain.setCurrentIndex(i)
                    break
            self.combo_gain.blockSignals(False)

    def _update_scale_badge_display(self) -> None:
        scale_text = f"📐 {self.ecg_plot.get_scale_text()}"
        self.lbl_scale_badge.setText(scale_text)
        is_grid_enabled = (self.current_grid_mode != "none")
        self.lbl_scale_badge.setVisible(is_grid_enabled)
        if hasattr(self.ecg_plot, "scale_corner_label") and self.ecg_plot.scale_corner_label is not None:
            self.ecg_plot.scale_corner_label.setVisible(is_grid_enabled)

    def set_language(self, lang_code: str) -> None:
        """Dynamically switches active language and retranslates all UI components."""
        set_locale(lang_code)
        if hasattr(self, "lang_actions") and lang_code in self.lang_actions:
            self.lang_actions[lang_code].blockSignals(True)
            self.lang_actions[lang_code].setChecked(True)
            self.lang_actions[lang_code].blockSignals(False)
        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        """Updates all UI text elements to reflect current language."""
        # Menu Bar
        if hasattr(self, "menu_file"):
            self.menu_file.setTitle(tr("menu_file"))
            self.action_open_study.setText(tr("menu_open_study"))
            self.action_export_study.setText(tr("menu_export_study"))
            if hasattr(self, "action_export_pdf"):
                self.action_export_pdf.setText(tr("menu_export_pdf"))
            self.action_close_study.setText(tr("menu_close_study"))
            self.action_exit.setText(tr("menu_exit"))

            self.menu_preferences.setTitle(tr("menu_preferences"))
            self.menu_languages.setTitle(tr("menu_languages"))
            self.menu_interface_theme.setTitle(tr("menu_interface_theme"))
            self.menu_canvas_theme.setTitle(tr("menu_canvas_theme"))
            self.action_toggle_calipers.setText(tr("menu_toggle_calipers"))

            self.menu_help.setTitle(tr("menu_help"))
            self.action_wiki.setText(tr("menu_wiki"))
            self.action_license.setText(tr("menu_license"))
            self.action_about.setText(tr("menu_about"))

            if hasattr(self, "theme_actions"):
                for tid, act in self.theme_actions.items():
                    if tid in THEMES:
                        act.setText(tr(THEMES[tid]["name_key"]))
            if hasattr(self, "canvas_theme_actions"):
                for cid, act in self.canvas_theme_actions.items():
                    if cid in CANVAS_THEMES:
                        act.setText(tr(CANVAS_THEMES[cid]["name_key"]))

        self.title_lbl.setText(tr("app_title"))
        self.btn_settings.setText(tr("btn_settings"))
        self.lead_lbl.setText(tr("channel_label"))
        self.btn_open.setText(tr("btn_open"))
        self.btn_open.setToolTip(tr("btn_open_tooltip"))
        self.btn_demo.setText(tr("btn_demo"))
        self.btn_demo.setToolTip(tr("btn_demo_tooltip"))
        self.btn_export.setText(tr("btn_export"))
        self.btn_export.setToolTip(tr("btn_export_tooltip"))
        if hasattr(self, "btn_export_pdf"):
            self.btn_export_pdf.setText(tr("btn_export_pdf"))
            self.btn_export_pdf.setToolTip(tr("btn_export_pdf_tooltip"))

        # Calipers Strip
        self.lbl_cal_cue.setText(tr("calipers_title"))
        self.lbl_tag_raw.setText(tr("cal_raw_qt"))
        if hasattr(self, "lbl_tag_rr"):
            self.lbl_tag_rr.setText(tr("cal_rr"))
        self.lbl_tag_bazett.setText(tr("cal_bazett"))
        self.lbl_tag_fridericia.setText(tr("cal_fridericia"))
        self.help_cue.setText(tr("cal_tip"))

        # Canvas Control Strip & Axes
        self.lbl_canvas_title.setText(f"ECG Waveform — {self.current_lead_name}")
        self.lbl_canvas_scheme.setText(tr("canvas_theme_label"))
        self.lbl_grid.setText(tr("grid_style_label"))
        if hasattr(self, "btn_grid_lines"):
            self.btn_grid_lines.setText(tr("grid_btn_lines"))
            self.btn_grid_dots.setText(tr("grid_btn_dots"))
            self.btn_grid_off.setText(tr("grid_btn_off"))
            self.btn_calipers_toggle.setText(tr("calipers_btn_toggle"))
            self.btn_calipers_center.setText(tr("calipers_btn_center"))
            self.btn_add_line.setText(tr("calipers_btn_add"))
            self.lbl_zoom.setText(tr("zoom_label"))
            self.btn_zoom_out.setToolTip(tr("zoom_out_tooltip"))
            self.btn_zoom_in.setToolTip(tr("zoom_in_tooltip"))
            self.btn_zoom_reset.setToolTip(tr("zoom_reset_tooltip"))
            self.btn_zoom_fit.setToolTip(tr("zoom_fit_tooltip"))
            self.btn_settings.setToolTip(tr("btn_settings_tooltip"))
            self.combo_canvas_theme.setToolTip(tr("canvas_theme_tooltip"))
            self.btn_grid_lines.setToolTip(tr("grid_lines_tooltip"))
            self.btn_grid_dots.setToolTip(tr("grid_dots_tooltip"))
            self.btn_grid_off.setToolTip(tr("grid_off_tooltip"))
            self.btn_calipers_toggle.setToolTip(tr("calipers_toggle_tooltip"))
            self.btn_calipers_center.setToolTip(tr("calipers_center_tooltip"))
            self.btn_add_line.setToolTip(tr("calipers_add_tooltip"))
            self.combo_speed.setToolTip(tr("speed_tooltip"))
            self.combo_gain.setToolTip(tr("gain_tooltip"))
        self._update_scale_badge_display()
        self.ecg_plot.plot_widget.setLabel("bottom", tr("axis_time"))
        self.ecg_plot.plot_widget.setLabel("left", tr("axis_voltage"))
        self.ecg_plot.update_corner_badge()

        # Retranslate Canvas Theme dropdown
        self.combo_canvas_theme.blockSignals(True)
        curr_c_idx = self.combo_canvas_theme.currentIndex()
        self.combo_canvas_theme.clear()
        for cid, ctheme in CANVAS_THEMES.items():
            self.combo_canvas_theme.addItem(tr(ctheme["name_key"]), cid)
        self.combo_canvas_theme.setCurrentIndex(curr_c_idx)
        self.combo_canvas_theme.blockSignals(False)

        # Retranslate Grid dropdown if present
        if hasattr(self, "combo_grid"):
            self.combo_grid.blockSignals(True)
            curr_g_idx = self.combo_grid.currentIndex()
            self.combo_grid.clear()
            self.combo_grid.addItem(tr("grid_lines"), "lines")
            self.combo_grid.addItem(tr("grid_dots"), "dots")
            self.combo_grid.addItem(tr("grid_none"), "none")
            self.combo_grid.setCurrentIndex(curr_g_idx)
            self.combo_grid.blockSignals(False)

        # Tabs
        self.tabs.setTabText(0, tr("tab_overview"))
        self.tabs.setTabText(1, tr("tab_events"))
        self.tabs.setTabText(2, tr("tab_beats"))
        if self.tabs.count() >= 6:
            self.tabs.setTabText(3, tr("tab_qtrr"))
            self.tabs.setTabText(4, tr("tab_holter"))
            self.tabs.setTabText(5, tr("tab_metadata"))
        elif self.tabs.count() >= 5:
            self.tabs.setTabText(3, tr("tab_qtrr"))
            self.tabs.setTabText(4, tr("tab_metadata"))
        else:
            self.tabs.setTabText(3, tr("tab_metadata"))
        if hasattr(self, "holter_trends_table"):
            self.holter_trends_table.setHorizontalHeaderLabels([
                tr("holter_hdr_hour"),
                tr("holter_hdr_beats"),
                tr("holter_hdr_hr"),
                tr("holter_hdr_pvc"),
                tr("holter_hdr_pac"),
                tr("holter_hdr_runs"),
                tr("holter_hdr_pauses"),
                tr("holter_hdr_af"),
            ])
            self.holter_af_table.setHorizontalHeaderLabels([
                tr("af_hdr_ep"),
                tr("af_hdr_start"),
                tr("af_hdr_end"),
                tr("af_hdr_dur"),
                tr("af_hdr_hr"),
                tr("af_hdr_max_hr"),
                tr("af_hdr_entropy"),
                tr("af_hdr_irreg"),
            ])
        if hasattr(self, "lbl_tab_qtrr_model"):
            self.lbl_tab_qtrr_model.setText(tr("qtrr_lbl_model"))
            self.lbl_tab_hyst_mode.setText(tr("qtrr_lbl_hyst"))
            self.qtrr_plot_widget.setLabel("bottom", tr("qtrr_axis_rr"))
            self.qtrr_plot_widget.setLabel("left", tr("qtrr_axis_qt"))
            self.qtrr_models_table.setHorizontalHeaderLabels([
                tr("qtrr_hdr_model"),
                tr("qtrr_hdr_eq"),
                tr("qtrr_hdr_slope"),
                tr("qtrr_hdr_r"),
                tr("qtrr_hdr_r2"),
                tr("qtrr_hdr_rmse"),
                tr("qtrr_hdr_aic"),
                tr("qtrr_hdr_qtc_ind"),
            ])

        self.grp_a_box.setTitle(tr("group_a_title"))
        self.grp_b_box.setTitle(tr("group_b_title"))
        self.meta_table_a.setHorizontalHeaderLabels([tr("hdr_field"), tr("hdr_value")])
        self.meta_table_b.setHorizontalHeaderLabels([tr("hdr_field"), tr("hdr_value")])

        # KPI Card Titles
        self.card_hr.title_lbl.setText(tr("kpi_hr_title"))
        self.card_qtc.title_lbl.setText(tr("kpi_qtc_title"))
        self.card_ectopic.title_lbl.setText(tr("kpi_ectopic_title"))
        self.card_sqi.title_lbl.setText(tr("kpi_sqi_title"))
        if hasattr(self, "card_qtd"):
            self.card_qtd.title_lbl.setText(tr("kpi_qtd_title"))
        self.adv_group.setTitle(tr("adv_group_title"))

        # Table Headers
        self.events_table.setHorizontalHeaderLabels([
            tr("hdr_time"), tr("hdr_event"), tr("hdr_value"), tr("hdr_severity")
        ])
        self.beat_table.setHorizontalHeaderLabels([
            tr("hdr_beat_num"),
            tr("hdr_time"),
            tr("hdr_class"),
            tr("hdr_pattern"),
            tr("hdr_rr"),
            tr("hdr_hr"),
            tr("hdr_qt"),
            tr("hdr_qtc"),
        ])

        # Re-render current metric evaluations or fallback placeholders
        if self.analysis_results:
            self._update_cards_and_tables()
        else:
            if hasattr(self, "card_qtd"):
                self.card_qtd.sub_lbl.setText(tr("qtd_sub_single"))
            self.lbl_adv_qtvi.setText(tr("adv_qtvi", val="--"))
            self.lbl_adv_qtrr.setText(tr("adv_qtrr", val="--"))
            self.lbl_adv_hyst.setText(tr("adv_hyst_na", val="--"))
            self.lbl_adv_hrv.setText(tr("adv_hrv_na", val="--"))
            self.lbl_adv_hrt.setText(tr("adv_hrt_na", val="--"))
            self.lbl_adv_twa.setText(tr("adv_twa_na", val="--"))
            self.lbl_adv_total.setText(tr("adv_total_cycles", count="--"))
            if hasattr(self, "lbl_qtrr_summary_banner"):
                self.lbl_qtrr_summary_banner.setText(tr("qtrr_banner_ready"))
            if hasattr(self, "lbl_holter_summary_banner"):
                self.lbl_holter_summary_banner.setText(tr("holter_summary_ready"))


    def set_task_progress(self, fraction: float, message: str) -> None:
        """Updates status bar message and progress indicator."""
        pct = int(min(max(fraction, 0.0), 1.0) * 100)
        if hasattr(self, "status_progress") and hasattr(self.status_progress, "setValue"):
            self.status_progress.setValue(pct)
            if hasattr(self.status_progress, "isHidden") and self.status_progress.isHidden():
                self.status_progress.show()
        if hasattr(self, "lbl_status_msg") and hasattr(self.lbl_status_msg, "setText"):
            self.lbl_status_msg.setText(message)

    def set_task_finished(self, final_message: str = "Ready") -> None:
        """Hides progress indicator and displays final status message."""
        if hasattr(self, "status_progress") and hasattr(self.status_progress, "hide"):
            self.status_progress.setValue(100)
            self.status_progress.hide()
        if hasattr(self, "lbl_status_msg") and hasattr(self.lbl_status_msg, "setText"):
            self.lbl_status_msg.setText(final_message)

    def _retire_active_worker(self, timeout_ms: int = 1000) -> None:
        """Cancels any active background worker and retains running threads until they exit safely."""
        if not hasattr(self, "_retired_workers"):
            self._retired_workers = []
        prev = getattr(self, "_active_worker", None)
        if prev is None:
            return
        self._active_worker = None
        if hasattr(prev, "cancel"):
            prev.cancel()
        if hasattr(prev, "isRunning") and prev.isRunning():
            logger.info("Superseding active BackgroundTaskWorker; waiting up to %d ms", timeout_ms)
            prev.quit()
            if not prev.wait(timeout_ms):
                logger.warning("Superseded worker still running after %d ms; holding reference in _retired_workers", timeout_ms)
                self._retired_workers.append(prev)
        # Prune any retired workers that have finished
        self._retired_workers = [
            w for w in self._retired_workers if hasattr(w, "isRunning") and w.isRunning()
        ]

    def _run_background_task(
        self,
        task_func: Callable[..., Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
        initial_msg: str = "Processing...",
        *args: Any,
        **kwargs: Any
    ) -> Any | None:
        """Runs a heavy API task either in a QThread (GUI mode) or synchronously (mock mode)."""
        self._retire_active_worker(timeout_ms=500)
        self.set_task_progress(0.0, initial_msg)

        if not HAS_GUI:
            try:
                def _prog(pct: float, msg: str) -> None:
                    self.set_task_progress(pct, msg)

                call_kwargs = dict(kwargs)
                call_kwargs["progress_callback"] = _prog
                res = task_func(*args, **call_kwargs)
                on_success(res)
                self.set_task_finished(tr("status_ready"))
            except Exception as exc:
                logger.exception("Synchronous background task failed: %s", exc)
                if on_error:
                    on_error(str(exc))
                else:
                    self.set_task_finished(f"Error: {exc}")
            return None

        worker = BackgroundTaskWorker(task_func, *args, **kwargs)
        self._active_worker = worker

        def _on_worker_progress(pct: float, msg: str) -> None:
            if self._active_worker is not worker or worker.is_cancelled():
                return
            self.set_task_progress(pct, msg)

        def _on_worker_finished(result: Any) -> None:
            if hasattr(self, "_retired_workers") and worker in self._retired_workers:
                self._retired_workers.remove(worker)
            if self._active_worker is not worker or worker.is_cancelled():
                logger.debug("Ignored finished signal from superseded BackgroundTaskWorker")
                return
            self._active_worker = None
            on_success(result)
            self.set_task_finished(tr("status_ready"))

        def _on_worker_error(err_msg: str) -> None:
            if hasattr(self, "_retired_workers") and worker in self._retired_workers:
                self._retired_workers.remove(worker)
            if self._active_worker is not worker or worker.is_cancelled():
                logger.debug("Ignored error signal from superseded BackgroundTaskWorker: %s", err_msg)
                return
            self._active_worker = None
            self.set_task_finished(f"Error: {err_msg}")
            if on_error:
                on_error(err_msg)
            else:
                QMessageBox.critical(self, tr("error_spec_title"), err_msg)

        worker.progress.connect(_on_worker_progress)
        worker.finished.connect(_on_worker_finished)
        worker.error.connect(_on_worker_error)
        worker.start()
        return worker

    def _load_synthetic_demo(self) -> None:
        """Loads synthetic benchmark rhythms and populates standard demo leads."""
        self.fs = 500.0
        self.current_filename = tr("demo_filename")
        if hasattr(self, "lbl_file_badge") and hasattr(self.lbl_file_badge, "setText"):
            self.lbl_file_badge.setText(self.current_filename)

        demo_fs = float(self.fs)

        def _task(progress_callback=None):
            return StudyAPI.generate_demo_study(
                duration_sec=12.0, fs=demo_fs, heart_rate_bpm=72.0, progress_callback=progress_callback
            )

        def _on_done(demo_res):
            self.time_data, lead2, _true_r = demo_res
            lead_v5 = lead2 * 0.82
            lead1 = lead2 * 0.65

            self.multi_lead_signals = {
                "Lead II (Standard)": lead2,
                "Lead V5 (Precordial)": lead_v5,
                "Lead I (Frontal)": lead1,
            }

            self.current_metadata = {
                "format": "Synthetic Demo (PECG Framework)",
                "patient_id": "DEMO-001",
                "age": 45,
                "gender": "Female",
                "race": "Unspecified",
                "pacemaker": "NO",
                "record_date": "2026-10-30",
                "start_time": "08:00:00",
                "indication": "Normal Sinus Rhythm Simulation",
                "clinical_notes": "Generated by repolaris.utils.signal asymmetric Gaussian wave synthesizer.",
            }

            if hasattr(self, "combo_leads"):
                self.combo_leads.blockSignals(True)
                self.combo_leads.clear()
                for name in self.multi_lead_signals:
                    self.combo_leads.addItem(name)
                self.combo_leads.setCurrentIndex(0)
                self.combo_leads.blockSignals(False)

            self.current_lead_name = "Lead II (Standard)"
            self.signal_data = self.multi_lead_signals[self.current_lead_name]
            self._run_pipeline_and_display()

        self._run_background_task(
            _task,
            _on_done,
            initial_msg=tr("status_loading")
        )

    def _open_file_dialog(self) -> None:
        """Opens any clinical recording, detects all available channels, and sets active lead."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("btn_open"),
            "",
            "All Supported ECG (*.pecg *.ecg *.dcm *.dicom *.xml *.aecg *.scp *.e3c *.edf *.hea *.dat *.csv *.npy);;"
            "DICOM Waveform (*.dcm *.dicom);;"
            "HL7 aECG XML (*.xml *.aecg);;"
            "SCP-ECG Standard (*.scp);;"
            "PECG Colleague Study (*.pecg);;"
            "ISHNE Holter Standard (*.ecg);;"
            "Excorde 3C Holter (*.e3c);;"
            "EDF Telemetry Patch (*.edf);;"
            "PhysioNet WFDB (*.hea *.dat);;"
            "All Files (*)",
        )
        if not path:
            return
        def _task(progress_callback=None):
            return StudyAPI.load_study_dataset(path, progress_callback=progress_callback)

        def _on_done(dataset):
            signals, fs, meta = dataset
            self.multi_lead_signals = signals
            self.fs = fs
            self.current_metadata = meta or {}

            # Detect zeroed or missing leads across the recording
            zeroed_leads = []
            for name, sig in self.multi_lead_signals.items():
                if len(sig) == 0 or np.all(sig == 0) or np.std(sig) < 1e-6:
                    zeroed_leads.append(name)

            if len(zeroed_leads) == len(self.multi_lead_signals) and len(self.multi_lead_signals) > 0:
                QMessageBox.warning(
                    self,
                    tr("warning_title"),
                    tr("warn_signal_all_zeroed", name=os.path.basename(path)),
                )
            elif zeroed_leads:
                QMessageBox.warning(
                    self,
                    tr("warning_title"),
                    tr("warn_signal_some_zeroed", leads=", ".join(zeroed_leads[:4])),
                )

            self.current_filename = os.path.basename(path)
            if hasattr(self, "lbl_file_badge"):
                self.lbl_file_badge.setText(self.current_filename)

            if hasattr(self, "combo_leads"):
                self.combo_leads.blockSignals(True)
                self.combo_leads.clear()
                lead_names = list(signals.keys())
                for name in lead_names:
                    self.combo_leads.addItem(name)

                default_idx = 0
                for idx, name in enumerate(lead_names):
                    clean_name = name.lower().replace(" ", "").replace("_", "")
                    if clean_name in ("leadii", "ii", "v5", "lead5", "ch2"):
                        default_idx = idx
                        break

                self.combo_leads.setCurrentIndex(default_idx)
                self.combo_leads.blockSignals(False)

                self.current_lead_name = lead_names[default_idx]
            else:
                self.current_lead_name = list(signals.keys())[0]

            self.signal_data = self.multi_lead_signals[self.current_lead_name]
            self.time_data = np.arange(len(self.signal_data)) / self.fs
            self._run_pipeline_and_display()

        self._run_background_task(
            _task,
            _on_done,
            initial_msg=tr("status_loading")
        )

    def _on_lead_changed(self, index: int) -> None:
        """Dynamically re-analyzes and renders the newly selected lead."""
        if index < 0 or not self.multi_lead_signals:
            return
        lead_name = self.combo_leads.currentText()
        if lead_name in self.multi_lead_signals:
            self.current_lead_name = lead_name
            self.signal_data = self.multi_lead_signals[lead_name]
            self.time_data = np.arange(len(self.signal_data)) / self.fs
            self._run_pipeline_and_display()

    def _evaluate_channel_capabilities(self) -> dict[str, Any]:
        """Dynamic channel-sensing state machine adapting UI between single-lead and multi-lead modes."""
        n_channels = len(self.multi_lead_signals)
        is_multilead = n_channels >= 3
        if hasattr(self, "card_qtd"):
            self.card_qtd.setEnabled(is_multilead)
            if not is_multilead:
                self.card_qtd.val_lbl.setText("N/A")
                self.card_qtd.sub_lbl.setText(tr("qtd_sub_single"))
        return {
            "channel_count": n_channels,
            "is_multilead_quorum": is_multilead,
            "mode": "MULTI_LEAD_HOLTER" if is_multilead else "SINGLE_LEAD_PATCH",
        }

    def _run_pipeline_and_display(self) -> None:
        if self.signal_data is None or len(self.signal_data) == 0:
            QMessageBox.warning(self, tr("warning_title"), tr("warn_signal_missing"))
            return
        if np.all(self.signal_data == 0) or np.std(self.signal_data) < 1e-6:
            QMessageBox.warning(
                self,
                tr("warning_title"),
                tr("warn_signal_zeroed", name=self.current_lead_name),
            )

        sig = self.signal_data
        fs = self.fs

        self._evaluate_channel_capabilities()
        multi_sigs = self.multi_lead_signals if len(self.multi_lead_signals) >= 3 else None

        cfg = ECGConfig(
            sampling_rate=fs,
            filter_cfg=FilterConfig(lowcut=0.05, highcut=45.0, notch_quality=30.0),
            detection_cfg=DetectionConfig(
                t_end_method=self.current_t_end_method,
                qtrr_model=self.current_qtrr_model,
                enable_hysteresis=(self.current_hysteresis_mode != "raw"),
                hysteresis_kernel=(
                    self.current_hysteresis_mode
                    if self.current_hysteresis_mode in ("exponential", "linear")
                    else "exponential"
                ),
            ),
        )

        def _task(progress_callback=None):
            return AnalysisAPI.analyze_signal(
                sig,
                fs=fs,
                config=cfg,
                progress_callback=progress_callback,
                multi_lead_signals=multi_sigs,
            )

        def _on_done(results):
            self.analysis_results = results
            clean = self.analysis_results["clean_signal"]
            r_peaks = self.analysis_results["r_peaks"]
            beats = self.analysis_results["beats"]
            events = self.analysis_results.get("events", [])
            self.annotation_manager = self.analysis_results.get("annotations")

            if self.time_data is not None and hasattr(self, "ecg_plot"):
                beat_classes = [str(b.get("beat_class", "N")) for b in beats]
                self.ecg_plot.display_signal(self.time_data, clean, r_peaks, beat_classes=beat_classes)
                if hasattr(self.ecg_plot, "plot_widget"):
                    self.ecg_plot.plot_widget.setTitle(
                        f"ECG Waveform — {self.current_lead_name}",
                        color="#93c5fd",
                        size="11pt",
                    )
                if hasattr(self, "lbl_canvas_title"):
                    self.lbl_canvas_title.setText(f"ECG Waveform — {self.current_lead_name}")

            self._update_cards_and_tables()

            if events:
                self._select_event(0)
            elif beats:
                self._select_beat(0)

        self._run_background_task(
            _task,
            _on_done,
            initial_msg=tr("status_analyzing")
        )

    def _update_cards_and_tables(self) -> None:
        """Refreshes KPI cards and tables with current localized descriptions."""
        if not self.analysis_results:
            return

        summary = self.analysis_results["summary"]
        ectopic = self.analysis_results.get("ectopic_summary", {})
        qtvi = self.analysis_results.get("qtvi")
        qtrr = self.analysis_results.get("qtrr")
        sqi = self.analysis_results.get("sqi", {})
        beats = self.analysis_results["beats"]
        events = self.analysis_results.get("events", [])

        # 1. Heart Rate KPI Card
        mean_hr = summary["mean_hr_bpm"]
        hr_text = f"{mean_hr:.0f} BPM"
        if mean_hr < 50:
            hr_sub = tr("hr_sub_brady")
            hr_color = "#fbbf24"
        elif mean_hr > 100:
            hr_sub = tr("hr_sub_tachy")
            hr_color = "#fbbf24"
        else:
            hr_sub = tr("hr_sub_normal")
            hr_color = "#34d399"
        self.card_hr.val_lbl.setText(hr_text)
        self.card_hr.val_lbl.setStyleSheet(f"color: {hr_color};")
        self.card_hr.sub_lbl.setText(hr_sub)

        # 2. QTc KPI Card
        qtc_val = summary["mean_qtc_bazett_ms"]
        qtc_text = f"{qtc_val:.0f} ms"
        if qtc_val >= 500:
            qtc_sub = tr("qtc_sub_critical")
            qtc_color = "#f87171"
        elif qtc_val >= 460:
            qtc_sub = tr("qtc_sub_borderline")
            qtc_color = "#fbbf24"
        elif qtc_val <= 340:
            qtc_sub = tr("qtc_sub_short")
            qtc_color = "#fbbf24"
        else:
            qtc_sub = tr("qtc_sub_normal")
            qtc_color = "#34d399"
        self.card_qtc.val_lbl.setText(qtc_text)
        self.card_qtc.val_lbl.setStyleSheet(f"color: {qtc_color};")
        self.card_qtc.sub_lbl.setText(qtc_sub)

        # 3. Ectopic Burden Card
        burden = ectopic.get("ectopic_burden_pct", 0.0)
        pvc_cnt = ectopic.get("pvc_count", 0)
        pac_cnt = ectopic.get("pac_count", 0)
        if burden > 5.0:
            ect_color = "#f87171"
            ect_sub = tr("ect_sub_high", pvc=pvc_cnt, pac=pac_cnt)
        elif burden > 0.0:
            ect_color = "#fbbf24"
            ect_sub = tr("ect_sub_low", pvc=pvc_cnt, pac=pac_cnt)
        else:
            ect_color = "#34d399"
            ect_sub = tr("ect_sub_normal")
        self.card_ectopic.val_lbl.setText(f"{burden:.1f}%")
        self.card_ectopic.val_lbl.setStyleSheet(f"color: {ect_color};")
        self.card_ectopic.sub_lbl.setText(ect_sub)

        # 4. Signal Quality Card
        verdict = sqi.get("verdict", "Good")
        snr = sqi.get("snr_db", 20.0)
        if snr >= 18.0:
            sqi_color = "#34d399"
            sqi_sub = tr("sqi_sub_clean", snr=snr)
        elif snr >= 12.0:
            sqi_color = "#fbbf24"
            sqi_sub = tr("sqi_sub_mod", snr=snr)
        else:
            sqi_color = "#f87171"
            sqi_sub = tr("sqi_sub_noisy", snr=snr)
        self.card_sqi.val_lbl.setText(verdict)
        self.card_sqi.val_lbl.setStyleSheet(f"color: {sqi_color};")
        self.card_sqi.sub_lbl.setText(sqi_sub)

        # 4b. Spatial QT Dispersion Card (Multi-Lead Gated)
        disp = self.analysis_results.get("dispersion")
        if hasattr(self, "card_qtd"):
            if disp and "summary" in disp:
                mean_qtd = disp["summary"].get("mean_qtd_ms", 0.0)
                mean_tped = disp["summary"].get("mean_tped_ms", 0.0)
                valid_cnt = disp["summary"].get("valid_lead_count", 0)
                self.card_qtd.setEnabled(True)
                self.card_qtd.val_lbl.setText(f"{mean_qtd:.1f} ms")
                self.card_qtd.sub_lbl.setText(tr("qtd_sub_multi", tped=mean_tped, cnt=valid_cnt))
            else:
                self._evaluate_channel_capabilities()

        # 5. Advanced Repolarization section
        if qtvi is not None:
            self.lbl_adv_qtvi.setText(tr("adv_qtvi", val=f"{qtvi:.2f}"))
        else:
            self.lbl_adv_qtvi.setText(tr("adv_qtvi_na"))

        if qtrr is not None:
            m_tag = qtrr.get("model", "linear")
            self.lbl_adv_qtrr.setText(
                tr("adv_qtrr", val=f"[{m_tag}] {qtrr['slope']:.3f} (r={qtrr['pearson_r']:.2f}, R²={qtrr.get('r_squared', 0.0):.2f})")
            )
        else:
            self.lbl_adv_qtrr.setText(tr("adv_qtrr_na"))

        hyst_res = self.analysis_results.get("hysteresis") or {}
        if hyst_res and "optimal_lambda" in hyst_res:
            self.lbl_adv_hyst.setText(
                tr(
                    "adv_hyst",
                    lam=hyst_res["optimal_lambda"],
                    t90=hyst_res.get("t90_sec", 0.0),
                    red=hyst_res.get("loop_reduction_percent", 0.0),
                )
            )
        else:
            self.lbl_adv_hyst.setText(tr("adv_hyst_na", val="N/A"))

        hrv_res = self.analysis_results.get("hrv") or {}
        if hrv_res and "time_domain" in hrv_res:
            td = hrv_res.get("time_domain") or {}
            fd = hrv_res.get("frequency_domain") or {}
            nl = hrv_res.get("nonlinear") or {}
            self.lbl_adv_hrv.setText(
                tr(
                    "adv_hrv",
                    sdnn=td.get("sdnn", 0.0),
                    rmssd=td.get("rmssd", 0.0),
                    lfhf=fd.get("lf_hf_ratio", 0.0),
                    sd12=nl.get("sd1_sd2_ratio", 0.0),
                )
            )
        else:
            self.lbl_adv_hrv.setText(tr("adv_hrv_na", val="N/A"))

        hrt_res = self.analysis_results.get("hrt") or {}
        if hrt_res and hrt_res.get("category") is not None:
            self.lbl_adv_hrt.setText(
                tr(
                    "adv_hrt",
                    to=hrt_res.get("turbulence_onset", 0.0),
                    ts=hrt_res.get("turbulence_slope", 0.0),
                    cat=hrt_res.get("category"),
                    pvcs=hrt_res.get("valid_pvc_count", 0),
                )
            )
        else:
            self.lbl_adv_hrt.setText(tr("adv_hrt_na", val="N/A"))

        twa_res = self.analysis_results.get("twa") or {}
        if twa_res and ("spectral" in twa_res or "mma" in twa_res):
            spec_twa = twa_res.get("spectral") or {}
            mma_twa = twa_res.get("mma") or {}
            verdict_str = "POSITIVE" if spec_twa.get("is_positive") else "NEGATIVE"
            self.lbl_adv_twa.setText(
                tr(
                    "adv_twa",
                    valt=spec_twa.get("v_alt_uv", 0.0),
                    k=spec_twa.get("k_score", 0.0),
                    verdict=verdict_str,
                    mma=mma_twa.get("max_v_mma_uv", 0.0),
                )
            )
        else:
            self.lbl_adv_twa.setText(tr("adv_twa_na", val="N/A"))

        self._update_qtrr_visualization()

        self.lbl_adv_total.setText(tr("adv_total_cycles", count=summary['total_beats']))

        # Populate Beat Table (8 documented columns: Beat #, Time, Class, Pattern, RR, HR, QT, QTc)
        self.beat_table.setRowCount(len(beats))
        for row, b in enumerate(beats):
            self.beat_table.setItem(row, 0, QTableWidgetItem(str(b["beat_index"] + 1)))
            self.beat_table.setItem(row, 1, QTableWidgetItem(f"{b['time_sec']:.2f}"))

            b_class = b.get("beat_class", "N")
            class_item = QTableWidgetItem(b_class)
            class_item.setForeground(QColor(_BEAT_CLASS_COLORS.get(b_class, "#94a3b8")))
            self.beat_table.setItem(row, 2, class_item)

            pattern_str = str(b.get("rhythm_pattern", "NSR"))
            self.beat_table.setItem(row, 3, QTableWidgetItem(pattern_str))

            rr_ms_val = float(b.get("rr_sec", 0.0)) * 1000.0
            self.beat_table.setItem(row, 4, QTableWidgetItem(f"{rr_ms_val:.0f}" if rr_ms_val > 0 else "--"))

            hr_val = float(b.get("hr_bpm", 0.0))
            self.beat_table.setItem(row, 5, QTableWidgetItem(f"{hr_val:.1f}" if np.isfinite(hr_val) and hr_val > 0 else "--"))

            self.beat_table.setItem(row, 6, QTableWidgetItem(f"{b['qt_ms']:.0f}"))
            qtc_b_val = (b.get("qtc") or {}).get("bazett_ms")
            self.beat_table.setItem(row, 7, QTableWidgetItem(f"{qtc_b_val:.0f}" if qtc_b_val is not None else "--"))

        # Populate Events Diary
        self.events_table.setRowCount(len(events))
        for row, ev in enumerate(events):
            item_time = QTableWidgetItem(f"{ev['timestamp_sec']:.2f}s")
            item_type = QTableWidgetItem(ev["event_type"].replace("_", " "))
            item_val = QTableWidgetItem(f"{ev['metric_value']:.0f} {ev['unit']}")
            item_sev = QTableWidgetItem(ev["severity"])

            color = QColor(_SEVERITY_COLORS.get(ev["severity"], "#60a5fa"))

            item_type.setForeground(color)
            item_sev.setForeground(color)

            self.events_table.setItem(row, 0, item_time)
            self.events_table.setItem(row, 1, item_type)
            self.events_table.setItem(row, 2, item_val)
            self.events_table.setItem(row, 3, item_sev)

        # Populate Holter Triage Tab (Hourly Trends & AF Episodes)
        self._update_holter_triage_tab()

        # Populate Study & Patient Metadata Tab (meta_table_a & meta_table_b)
        self._populate_metadata_tables()

    def set_qtrr_model(self, model_id: str) -> None:
        """Sets the active Pueyo (2004) QT-RR restitution regression model and refreshes visualization."""
        self.current_qtrr_model = model_id
        if hasattr(self, "combo_tab_qtrr_model"):
            self.combo_tab_qtrr_model.blockSignals(True)
            for i in range(self.combo_tab_qtrr_model.count()):
                if self.combo_tab_qtrr_model.itemData(i) == model_id:
                    self.combo_tab_qtrr_model.setCurrentIndex(i)
                    break
            self.combo_tab_qtrr_model.blockSignals(False)
        self._update_qtrr_visualization()

    def set_hysteresis_mode(self, mode_id: str) -> None:
        """Sets multi-beat QT-RR hysteresis lag mode ('exponential', 'linear', or 'raw') and refreshes plot."""
        if mode_id not in ("exponential", "linear", "raw"):
            return
        self.current_hysteresis_mode = mode_id
        if hasattr(self, "combo_tab_hyst_mode"):
            self.combo_tab_hyst_mode.blockSignals(True)
            for i in range(self.combo_tab_hyst_mode.count()):
                if self.combo_tab_hyst_mode.itemData(i) == mode_id:
                    self.combo_tab_hyst_mode.setCurrentIndex(i)
                    break
            self.combo_tab_hyst_mode.blockSignals(False)
        self._update_qtrr_visualization()

    def set_t_end_method(self, method_id: str) -> None:
        """Sets T-wave offset delineation algorithm ('hybrid', 'tangent', 'zhang_area', 'threshold') and re-runs pipeline."""
        if method_id not in ("hybrid", "tangent", "zhang_area", "threshold"):
            return
        self.current_t_end_method = method_id
        if self.signal_data is not None and len(self.signal_data) > 0:
            self._run_pipeline_and_display()

    def _on_tab_qtrr_model_changed(self, index: int) -> None:
        if index < 0:
            return
        mid = self.combo_tab_qtrr_model.itemData(index)
        if mid:
            self.set_qtrr_model(mid)

    def _on_tab_hyst_mode_changed(self, index: int) -> None:
        if index < 0:
            return
        hid = self.combo_tab_hyst_mode.itemData(index)
        if hid:
            self.set_hysteresis_mode(hid)

    def _on_qtrr_table_row_clicked(self, row: int, col: int) -> None:
        item = self.qtrr_models_table.item(row, 0)
        if item is not None:
            model_name = item.text().strip()
            if model_name in SUPPORTED_QTRR_MODELS:
                self.set_qtrr_model(model_name)

    def _update_qtrr_visualization(self) -> None:
        """Evaluates all 10 Pueyo (2004) QT-RR models under current hysteresis settings and renders scatter + curve."""
        if not self.analysis_results or not hasattr(self, "qtrr_plot_widget"):
            return
        beats = self.analysis_results.get("beats", [])
        if len(beats) < 4:
            return

        rr_raw = np.array([b["rr_sec"] for b in beats], dtype=np.float64)
        qt_sec = np.array([b["qt_ms"] / 1000.0 for b in beats], dtype=np.float64)
        qt_ms = qt_sec * 1000.0

        hyst_info = self.analysis_results.get("hysteresis") or {}
        opt_lambda = float(hyst_info.get("optimal_lambda", 0.08))
        t90_sec = float(hyst_info.get("t90_sec", 0.0))

        try:
            eval_res = AnalysisAPI.evaluate_qtrr_models(
                rr_raw,
                qt_sec,
                preferred_model=self.current_qtrr_model,
                hysteresis_mode=self.current_hysteresis_mode,
                optimal_lambda=opt_lambda,
            )
        except Exception:
            return

        active_fit = eval_res["active_fit"]
        ranking = eval_res["ranking"]
        rr_used = np.asarray(eval_res["rr_used_sec"], dtype=np.float64)

        # Update scatter points & regression curve on qtrr_plot_widget
        self.qtrr_raw_scatter.setData(rr_raw, qt_ms)
        self.qtrr_eff_scatter.setData(rr_used, qt_ms)

        rr_min = max(0.30, float(np.min(rr_used)) * 0.92)
        rr_max = min(2.00, float(np.max(rr_used)) * 1.08)
        rr_grid = np.linspace(rr_min, rr_max, 120)
        qt_curve_ms = np.asarray(active_fit["predict_fn"](rr_grid), dtype=np.float64) * 1000.0
        self.qtrr_fit_curve.setData(rr_grid, qt_curve_ms)

        qtc_ind_ms = float(active_fit["qtc_individual_ms"])
        self.qtrr_ref_scatter.setData([1.0], [qtc_ind_ms])

        # Update summary banner
        hyst_tag = (
            f"EW Hysteresis (λ*={opt_lambda:.3f}, t90={t90_sec:.1f}s)"
            if self.current_hysteresis_mode == "exponential"
            else (
                "LW Hysteresis (25-beat kernel)"
                if self.current_hysteresis_mode == "linear"
                else "Uncompensated Instantaneous RR"
            )
        )
        self.lbl_qtrr_summary_banner.setText(
            tr(
                "qtrr_banner_fmt",
                label=active_fit["label"],
                slope=active_fit["slope"],
                intercept=active_fit["intercept"],
                r=active_fit["pearson_r"],
                r2=active_fit["r_squared"],
                rmse=active_fit["rmse_ms"],
                qtc_ind=qtc_ind_ms,
                hyst_tag=hyst_tag,
            )
        )

        self.lbl_adv_qtrr.setText(
            tr(
                "adv_qtrr",
                val=f"[{active_fit['model']}] {active_fit['slope']:.3f} (r={active_fit['pearson_r']:.2f}, R²={active_fit['r_squared']:.2f})",
            )
        )

        # Populate 10-model comparison table (8 columns: Model, Equation, Slope, Pearson r, R², RMSE, AIC, QTc,ind)
        self.qtrr_models_table.setRowCount(len(ranking))
        for r_idx, m_info in enumerate(ranking):
            is_active = (m_info["model"] == active_fit["model"])
            row_color = QColor("#38bdf8") if is_active else QColor("#cbd5e1")

            cells = [
                QTableWidgetItem(str(m_info["model"])),
                QTableWidgetItem(str(m_info["equation"])),
                QTableWidgetItem(f"{m_info.get('slope', 0.0):.4f}"),
                QTableWidgetItem(f"{m_info.get('pearson_r', 0.0):.3f}"),
                QTableWidgetItem(f"{m_info['r_squared']:.3f}"),
                QTableWidgetItem(f"{m_info['rmse_ms']:.2f}"),
                QTableWidgetItem(f"{m_info.get('aic', 0.0):.1f}"),
                QTableWidgetItem(f"{m_info['qtc_individual_ms']:.1f}"),
            ]
            for c_idx, it in enumerate(cells):
                it.setForeground(row_color)
                self.qtrr_models_table.setItem(r_idx, c_idx, it)

    def _setup_keyboard_shortcuts(self) -> None:
        """Registers keyboard shortcuts for beat-by-beat navigation (Left/Right) and AAMI hotkeys (N, V, S, F, Q)."""
        self.action_prev_beat = QAction("Previous Beat", self)
        self.action_prev_beat.setShortcut(QKeySequence("Left"))
        self.action_prev_beat.triggered.connect(self.prev_beat)
        self.addAction(self.action_prev_beat)

        self.action_next_beat = QAction("Next Beat", self)
        self.action_next_beat.setShortcut(QKeySequence("Right"))
        self.action_next_beat.triggered.connect(self.next_beat)
        self.addAction(self.action_next_beat)

        self.aami_hotkey_actions: dict[str, Any] = {}
        for code in ("N", "V", "S", "F", "Q"):
            act = QAction(f"Classify {code}", self)
            act.setShortcut(QKeySequence(code))
            act.triggered.connect(lambda checked=False, c=code: self.reclassify_active_beat(c))
            self.addAction(act)
            self.aami_hotkey_actions[code] = act

    def prev_beat(self) -> None:
        """Steps to the previous cardiac cycle and centers calipers on it."""
        if not self.analysis_results or not self.analysis_results.get("beats"):
            return
        target = max(0, self.current_beat_index - 1)
        self._select_beat(target)
        if hasattr(self.beat_table, "selectRow"):
            self.beat_table.selectRow(target)

    def next_beat(self) -> None:
        """Steps to the next cardiac cycle and centers calipers on it."""
        if not self.analysis_results or not self.analysis_results.get("beats"):
            return
        beats = self.analysis_results["beats"]
        target = min(len(beats) - 1, self.current_beat_index + 1)
        self._select_beat(target)
        if hasattr(self.beat_table, "selectRow"):
            self.beat_table.selectRow(target)

    def reclassify_active_beat(self, new_label: str) -> None:
        """Reclassifies the currently selected beat using a single-key AAMI hotkey (N, V, S, F, Q)."""
        clean_lbl = new_label.strip().upper()
        if clean_lbl not in ("N", "V", "S", "F", "Q"):
            return
        self.reclassify_beat(self.current_beat_index, clean_lbl)

    def keyPressEvent(self, event: Any) -> None:
        """Handles Left/Right beat navigation and N/V/S/F/Q AAMI reclassification hotkeys."""
        key_code = event.key() if hasattr(event, "key") and callable(event.key) else None
        key_text = event.text().upper() if hasattr(event, "text") and callable(event.text) and event.text() else ""

        if key_code == getattr(Qt.Key, "Key_Left", 0x01000012) or key_text == "LEFT":
            self.prev_beat()
            return
        if key_code == getattr(Qt.Key, "Key_Right", 0x01000014) or key_text == "RIGHT":
            self.next_beat()
            return
        if key_text in ("N", "V", "S", "F", "Q"):
            self.reclassify_active_beat(key_text)
            return
        for code in ("N", "V", "S", "F", "Q"):
            if key_code == getattr(Qt.Key, f"Key_{code}", None):
                self.reclassify_active_beat(code)
                return

    def _select_beat(self, index: int) -> None:
        if not self.analysis_results or index < 0 or index >= len(self.analysis_results["beats"]):
            return
        self.current_beat_index = index
        beat = self.analysis_results["beats"][index]
        q_sec = beat["q_onset_sample"] / self.fs
        t_sec = beat["t_end_sample"] / self.fs
        self.current_beat_rr = float(beat.get("rr_sec", 0.85) or 0.85)
        if hasattr(self, "lbl_cal_rr"):
            self.lbl_cal_rr.setText(f"{self.current_beat_rr * 1000.0:.0f} ms")

        self.ecg_plot.set_calipers(q_sec, t_sec)
        r_sec = beat["r_peak_sample"] / self.fs
        self.ecg_plot.plot_widget.setXRange(max(0.0, r_sec - 0.4), r_sec + 0.6, padding=0)

    def _select_event(self, event_row: int) -> None:
        if not self.analysis_results or event_row >= len(self.analysis_results.get("events", [])):
            return
        ev = self.analysis_results["events"][event_row]
        beat_idx = ev.get("beat_index", 0)
        self._select_beat(beat_idx)

    def _on_beat_selected(self, row: int, col: int) -> None:
        self._select_beat(row)

    def reclassify_beat(self, row: int, new_label: str) -> None:
        """Reclassifies a beat and propagates the override across rhythm patterns, ectopic burden, HRV, HRT, and UI tables."""
        if not self.analysis_results or row < 0 or row >= len(self.analysis_results["beats"]):
            return
        beats = self.analysis_results["beats"]
        beat = beats[row]
        current_class = beat.get("beat_class", "N")
        beat["beat_class"] = new_label

        if self.annotation_manager:
            self.annotation_manager.override_beat_label(
                sample=beat["r_peak_sample"],
                new_label=new_label,
                reviewer="Physician",
                notes=f"Manual override from {current_class} to {new_label}",
            )

        classified_beats = self.analysis_results.get("classified_beats", [])
        if row < len(classified_beats):
            with contextlib.suppress(ValueError):
                classified_beats[row].beat_class = BeatClass(new_label)
            detect_rhythm_patterns(classified_beats)
            for idx, cb in enumerate(classified_beats):
                if idx < len(beats):
                    beats[idx]["rhythm_pattern"] = cb.rhythm_pattern.value

        counts: dict[str, int] = {}
        for b in beats:
            cls_code = str(b.get("beat_class", "N"))
            counts[cls_code] = counts.get(cls_code, 0) + 1
        tot_b = len(beats)
        pvc_cnt = counts.get("V", 0)
        pac_cnt = counts.get("S", 0)
        ect_summary = self.analysis_results.get("ectopic_summary") or {}
        ect_summary.update({
            "total_beats": tot_b,
            "counts": counts,
            "pvc_count": pvc_cnt,
            "pac_count": pac_cnt,
            "pvc_percentage": round(pvc_cnt / tot_b * 100.0, 2) if tot_b > 0 else 0.0,
            "ectopic_burden_pct": round((pvc_cnt + pac_cnt) / tot_b * 100.0, 2) if tot_b > 0 else 0.0,
        })
        self.analysis_results["ectopic_summary"] = ect_summary
        if "summary" in self.analysis_results:
            self.analysis_results["summary"]["ectopic_summary"] = ect_summary

        nn_ms = [b["rr_sec"] * 1000.0 for b in beats if b.get("beat_class") == "N" and b.get("rr_sec", 0.0) > 0.2]
        hrv_in = nn_ms if len(nn_ms) >= 4 else [b["rr_sec"] * 1000.0 for b in beats if b.get("rr_sec", 0.0) > 0.2]
        if len(hrv_in) >= 2:
            self.analysis_results["hrv"] = AnalysisAPI.analyze_hrv(hrv_in)
        r_peaks = self.analysis_results.get("r_peaks")
        if classified_beats and r_peaks is not None:
            self.analysis_results["hrt"] = AnalysisAPI.analyze_hrt(classified_beats, r_peaks, fs=self.fs)

        clean_sig = self.analysis_results.get("clean_signal")
        if self.time_data is not None and clean_sig is not None and r_peaks is not None:
            beat_classes = [str(b.get("beat_class", "N")) for b in beats]
            self.ecg_plot.display_signal(self.time_data, clean_sig, r_peaks, beat_classes=beat_classes)

        self._update_cards_and_tables()

    def _on_beat_double_clicked(self, row: int, col: int) -> None:
        """Physician manual override: double clicking a beat allows diagnosis reclassification."""
        if not self.analysis_results or row >= len(self.analysis_results["beats"]):
            return
        current_class = self.analysis_results["beats"][row].get("beat_class", "N")
        options = [tr("opt_n"), tr("opt_v"), tr("opt_s"), tr("opt_f"), tr("opt_q")]
        choice, ok = QInputDialog.getItem(
            self,
            tr("override_title", num=row + 1),
            tr("override_prompt", curr=current_class),
            options,
            0,
            False,
        )
        if not ok or not choice:
            return
        self.reclassify_beat(row, choice[0])

    def _on_event_selected(self, row: int, col: int) -> None:
        self._select_event(row)

    def _on_caliper_dragged(self, q_sec: float, t_sec: float) -> None:
        """Updates live caliper HUD and persists calibrated Q-onset/T-end into the active beat and study summary."""
        qt_sec = abs(t_sec - q_sec)
        qt_ms = qt_sec * 1000.0
        rr_val = self.current_beat_rr if self.current_beat_rr > 0 else 0.85
        qtc = AnalysisAPI.calculate_qtc(qt_sec, rr_val)
        self.lbl_cal_qt.setText(f"{qt_ms:.0f} ms")
        if hasattr(self, "lbl_cal_rr"):
            self.lbl_cal_rr.setText(f"{rr_val * 1000.0:.0f} ms")
        self.lbl_cal_bazett.setText(f"{qtc['bazett_ms']:.0f} ms")
        self.lbl_cal_fridericia.setText(f"{qtc['fridericia_ms']:.0f} ms")

        if self.analysis_results and "beats" in self.analysis_results:
            beats = self.analysis_results["beats"]
            if 0 <= self.current_beat_index < len(beats):
                beat = beats[self.current_beat_index]
                q_samp = max(0, int(round(min(q_sec, t_sec) * self.fs)))
                t_samp = max(q_samp + 1, int(round(max(q_sec, t_sec) * self.fs)))
                beat["q_onset_sample"] = q_samp
                beat["t_end_sample"] = t_samp
                beat["qt_sec"] = float(qt_sec)
                beat["qt_ms"] = float(qt_ms)
                beat["qtc"] = qtc

                ect_keep = self.analysis_results.get("ectopic_summary", {})
                new_sum = summarize_beats(beats)
                new_sum["ectopic_summary"] = ect_keep
                self.analysis_results["summary"] = new_sum

                self.beat_table.setItem(self.current_beat_index, 6, QTableWidgetItem(f"{qt_ms:.0f}"))
                self.beat_table.setItem(self.current_beat_index, 7, QTableWidgetItem(f"{qtc['bazett_ms']:.0f}"))
                mean_qtc_b = new_sum.get("mean_qtc_bazett_ms", qtc["bazett_ms"])
                self.card_qtc.val_lbl.setText(f"{mean_qtc_b:.0f} ms")

    def _export_pecg_dialog(self) -> None:
        if self.signal_data is None:
            QMessageBox.warning(self, tr("no_rec_title"), tr("no_rec_msg"))
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("export_dialog_title"), "study_export.pecg", "Repolaris Study (*.pecg)"
        )
        if not path:
            return

        age, ok = QInputDialog.getInt(self, tr("patient_age_title"), tr("patient_age_prompt"), 55, 0, 120)
        if not ok:
            return
        race, ok = QInputDialog.getText(self, tr("patient_race_title"), tr("patient_race_prompt"), text="Unspecified")
        if not ok:
            return
        pm_items = ["NO", "YES (Unspecified)", "VVI", "AAI", "DDD", "BIVENTRICULAR / CRT"]
        pacemaker, ok = QInputDialog.getItem(
            self, tr("patient_pm_title"), tr("patient_pm_prompt"), pm_items, 0, False
        )
        if not ok:
            return
        notes, ok = QInputDialog.getText(self, tr("notes_title"), tr("notes_prompt"), text="")
        if not ok:
            return

        ann_payload = {"physician_notes": [{"comment": notes}]}
        if self.annotation_manager:
            ann_payload["beats"] = self.annotation_manager.to_dict_list()

        if self.multi_lead_signals:
            lead_names = list(self.multi_lead_signals.keys())
            lead_matrix = np.array([self.multi_lead_signals[k] for k in lead_names])
        else:
            lead_names = [self.current_lead_name]
            lead_matrix = self.signal_data

        export_fs = float(self.fs)
        export_events = list(self.analysis_results.get("events", [])) if self.analysis_results else []

        def _task(progress_callback=None):
            return ExportAPI.export_study_pecg(
                filepath=path,
                signals=lead_matrix,
                sampling_rate=export_fs,
                lead_names=lead_names,
                patient_info={"age": age, "race": race, "sex": "UNKNOWN", "indication": notes, "pacemaker": pacemaker},
                annotations=ann_payload,
                events=export_events,
                compression="zstd",
                progress_callback=progress_callback,
            )

        def _on_done(saved_path):
            QMessageBox.information(self, tr("export_success_title"), tr("export_success_msg", path=saved_path))

        self._run_background_task(
            _task,
            _on_done,
            initial_msg=tr("status_exporting")
        )


    def _populate_metadata_tables(self) -> None:
        """Populates Group A (Demographics & Timing) and Group B (Clinical Context & Study Specs) tables."""
        meta = self.current_metadata or {}
        patient_sub = meta.get("patient", {}) if isinstance(meta.get("patient"), dict) else {}
        rec_sub = meta.get("recording", {}) if isinstance(meta.get("recording"), dict) else {}

        pid = str(meta.get("patient_id") or patient_sub.get("patient_id") or meta.get("record_name") or "ANONYMOUS")
        sex = str(meta.get("gender") or meta.get("sex") or patient_sub.get("sex") or tr("meta_unspecified"))
        age_val = meta.get("age") if meta.get("age") is not None else patient_sub.get("age")
        bdate = str(meta.get("birth_date") or "")
        if age_val is not None and bdate:
            age_str = f"{age_val} yrs ({bdate})"
        elif age_val is not None:
            age_str = f"{age_val} yrs"
        elif bdate:
            age_str = bdate
        else:
            age_str = tr("meta_unspecified")

        rdate = str(meta.get("record_date") or meta.get("study_date") or meta.get("start_date") or meta.get("effective_time") or "")
        stime = str(meta.get("start_time") or meta.get("study_time") or "")
        timing_str = f"{rdate} {stime}".strip() or tr("meta_unspecified")

        rows_a = [
            (tr("meta_patient_id"), pid),
            (tr("meta_sex"), sex),
            (tr("meta_age"), age_str),
            (tr("meta_timing"), timing_str),
        ]
        self.meta_table_a.setRowCount(len(rows_a))
        for r_idx, (field_lbl, val_str) in enumerate(rows_a):
            self.meta_table_a.setItem(r_idx, 0, QTableWidgetItem(str(field_lbl)))
            self.meta_table_a.setItem(r_idx, 1, QTableWidgetItem(str(val_str)))

        pm_str = str(meta.get("pacemaker") or patient_sub.get("pacemaker") or "NO")
        ind_str = str(meta.get("indication") or patient_sub.get("indication") or tr("meta_unspecified"))
        race_str = str(meta.get("race") or patient_sub.get("race") or tr("meta_unspecified"))
        fmt_str = str(meta.get("format") or "Standard ECG")
        if "PECG" in fmt_str.upper():
            name_str = tr("meta_deidentified")
        else:
            name_str = str(meta.get("patient_name") or f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip() or tr("meta_deidentified"))

        n_ch = len(self.multi_lead_signals) if self.multi_lead_signals else 1
        ch_str = f"{n_ch} leads @ {self.fs:.0f} Hz"
        dur_sec = float(
            meta.get("duration_sec")
            or rec_sub.get("duration_sec")
            or (len(self.signal_data) / self.fs if (self.signal_data is not None and self.fs > 0) else 0.0)
        )
        dur_str = f"{dur_sec:.1f} s ({dur_sec / 60.0:.1f} min)"
        notes_str = str(meta.get("clinical_notes") or tr("meta_unspecified"))

        rows_b = [
            (tr("meta_pacemaker"), pm_str),
            (tr("meta_indication"), ind_str),
            (tr("meta_race"), race_str),
            (tr("meta_name"), name_str),
            (tr("meta_format"), fmt_str),
            (tr("meta_channels"), ch_str),
            (tr("meta_duration"), dur_str),
            (tr("meta_notes"), notes_str),
        ]
        self.meta_table_b.setRowCount(len(rows_b))
        for r_idx, (field_lbl, val_str) in enumerate(rows_b):
            self.meta_table_b.setItem(r_idx, 0, QTableWidgetItem(str(field_lbl)))
            self.meta_table_b.setItem(r_idx, 1, QTableWidgetItem(str(val_str)))

    def _update_holter_triage_tab(self) -> None:
        """Populates the Holter Triage tab with hourly trend bins and AF episodes."""
        if not self.analysis_results or not hasattr(self, "holter_trends_table"):
            return
        trends = self.analysis_results.get("trends") or {}
        af_rep = self.analysis_results.get("af_report") or {}
        bins = trends.get("hourly_bins", [])
        episodes = af_rep.get("episodes", [])

        af_burden = af_rep.get("af_burden_pct", 0.0)
        tot_pvc = trends.get("total_pvcs", 0)
        tot_pac = trends.get("total_pacs", 0)
        tot_pauses = trends.get("total_pauses", 0)
        max_pause = trends.get("max_pause_sec", 0.0)
        self.lbl_holter_summary_banner.setText(
            tr(
                "holter_banner_fmt",
                hours=len(bins),
                pvc=tot_pvc,
                pac=tot_pac,
                pauses=tot_pauses,
                max_pause=max_pause,
                af=af_burden,
                episodes=len(episodes),
            )
        )

        self.holter_trends_table.setRowCount(len(bins))
        for r_idx, b in enumerate(bins):
            self.holter_trends_table.setItem(r_idx, 0, QTableWidgetItem(f"H{b.get('hour_index', r_idx + 1)}"))
            self.holter_trends_table.setItem(r_idx, 1, QTableWidgetItem(str(b.get("total_beats", 0))))
            self.holter_trends_table.setItem(r_idx, 2, QTableWidgetItem(f"{b.get('mean_hr_bpm', 0.0):.1f}"))
            self.holter_trends_table.setItem(r_idx, 3, QTableWidgetItem(str(b.get("pvc_count", 0))))
            self.holter_trends_table.setItem(r_idx, 4, QTableWidgetItem(str(b.get("pac_count", 0))))
            self.holter_trends_table.setItem(
                r_idx, 5, QTableWidgetItem(f"{b.get('couplet_count', 0)}/{b.get('vt_run_count', 0)}")
            )
            self.holter_trends_table.setItem(r_idx, 6, QTableWidgetItem(str(b.get("pause_count", 0))))
            self.holter_trends_table.setItem(r_idx, 7, QTableWidgetItem(f"{b.get('af_burden_pct', 0.0):.1f}%"))

        self.holter_af_table.setRowCount(len(episodes))
        for r_idx, ep in enumerate(episodes):
            self.holter_af_table.setItem(r_idx, 0, QTableWidgetItem(str(ep.get("episode_index", r_idx + 1))))
            self.holter_af_table.setItem(r_idx, 1, QTableWidgetItem(f"{ep.get('start_time_sec', 0.0):.1f}"))
            self.holter_af_table.setItem(r_idx, 2, QTableWidgetItem(f"{ep.get('end_time_sec', 0.0):.1f}"))
            self.holter_af_table.setItem(r_idx, 3, QTableWidgetItem(f"{ep.get('duration_sec', 0.0):.1f}"))
            self.holter_af_table.setItem(r_idx, 4, QTableWidgetItem(f"{ep.get('mean_hr_bpm', 0.0):.1f}"))
            self.holter_af_table.setItem(r_idx, 5, QTableWidgetItem(f"{ep.get('max_hr_bpm', 0.0):.1f}"))
            self.holter_af_table.setItem(r_idx, 6, QTableWidgetItem(f"{ep.get('shannon_entropy', 0.0):.2f}"))
            self.holter_af_table.setItem(r_idx, 7, QTableWidgetItem(f"{ep.get('irregularity_score', 0.0):.3f}"))

    def _on_holter_hour_clicked(self, row: int, col: int) -> None:
        """Seeks the waveform plot to the start of the selected hourly bin."""
        if not self.analysis_results:
            return
        bins = (self.analysis_results.get("trends") or {}).get("hourly_bins", [])
        if 0 <= row < len(bins):
            t_start = float(bins[row].get("start_time_sec", 0.0))
            self.ecg_plot.plot_widget.setXRange(t_start, t_start + 10.0, padding=0)

    def _on_holter_af_clicked(self, row: int, col: int) -> None:
        """Seeks the waveform plot to the start of the selected AF episode."""
        if not self.analysis_results:
            return
        episodes = (self.analysis_results.get("af_report") or {}).get("episodes", [])
        if 0 <= row < len(episodes):
            t_start = float(episodes[row].get("start_time_sec", 0.0))
            self.ecg_plot.plot_widget.setXRange(t_start, t_start + 10.0, padding=0)

    def _export_pdf_dialog(self) -> None:
        """Exports a printable multi-page clinical PDF report of the active study."""
        if not self.analysis_results:
            QMessageBox.warning(self, tr("no_rec_title"), tr("no_rec_msg"))
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("export_pdf_dialog_title"), "repolaris_clinical_report.pdf", "PDF Report (*.pdf)"
        )
        if not path:
            return

        results_snap = dict(self.analysis_results)
        meta_snap = dict(self.current_metadata) if self.current_metadata else {}
        fs_snap = float(self.fs)
        lead_snap = str(self.current_lead_name)

        def _task(progress_callback=None):
            return ExportAPI.export_clinical_pdf(
                filepath=path,
                analysis_results=results_snap,
                patient_metadata=meta_snap,
                fs=fs_snap,
                lead_name=lead_snap,
                progress_callback=progress_callback,
            )

        def _on_done(saved_path):
            QMessageBox.information(self, tr("export_success_title"), tr("export_success_msg", path=saved_path))

        self._run_background_task(
            _task,
            _on_done,
            initial_msg=tr("status_exporting"),
        )

    def closeEvent(self, event: Any) -> None:
        """Safely clean up any active or retired background worker threads before window destruction."""
        self._retire_active_worker(timeout_ms=2000)
        for retired in list(getattr(self, "_retired_workers", [])):
            if hasattr(retired, "isRunning") and retired.isRunning():
                retired.quit()
                retired.wait(1000)
        if hasattr(self, "_retired_workers"):
            self._retired_workers.clear()
        if hasattr(super(), "closeEvent"):
            super().closeEvent(event)


def main() -> None:
    """Entrypoint for the PyQtGraph GUI application."""
    if not HAS_GUI:
        print("GUI dependencies not installed. Run: pip install 'repolaris[gui]'")
        sys.exit(1)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
