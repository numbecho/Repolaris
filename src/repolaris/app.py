"""Repolaris Workstation GUI — Human-Centered Clinical Electrocardiogram Analyzer with i18n support.

Supports multi-language real-time switching:
- en: English (Default)
- es: Español (Spanish)
- fr: Français (French)
- de: Deutsch (German)

All source code remains strictly in English. UI text is managed via repolaris.i18n.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable, Dict, List, Optional
import numpy as np

try:
    import pyqtgraph as pg
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QFileDialog, QTableWidget, QTableWidgetItem,
        QHeaderView, QGroupBox, QMessageBox, QTabWidget,
        QInputDialog, QSplitter, QComboBox, QFrame
    )
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtGui import QColor, QFont
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

from repolaris.detection.pipeline import analyze_ecg
from repolaris.detection.pulse_metrics import compute_qtc
from repolaris.detection.classifier import BeatClass
from repolaris.detection.annotations import AnnotationManager
from repolaris.utils.signal import generate_synthetic_ecg
from repolaris.io.ecg_loader import load_ecg_dataset
from repolaris.io.pecg_format import save_pecg
from repolaris.i18n import tr, set_locale, get_current_locale, SUPPORTED_LANGUAGES


class ECGPlotWidget:
    """PyQtGraph-based high-performance interactive ECG waveform viewer with draggable calipers."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        if not HAS_GUI:
            raise ImportError("PyQt6 and pyqtgraph are required for GUI components.")

        self.plot_widget = pg.PlotWidget(parent=parent)
        self.plot_widget.setBackground("#13151f")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.18)
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setLabel("left", "Voltage", units="mV")
        self.plot_widget.setTitle(
            "ECG Waveform — Lead II (Standard)",
            color="#93c5fd",
            size="11pt"
        )

        # Plot curves: Soft medical cyan-blue waveform
        self.signal_curve = self.plot_widget.plot(pen=pg.mkPen(color="#38bdf8", width=1.6))
        self.r_peak_scatter = pg.ScatterPlotItem(
            size=9, pen=pg.mkPen(None), brush=pg.mkBrush("#f87171"), symbol="t1"
        )
        self.plot_widget.addItem(self.r_peak_scatter)

        # Interactive draggable caliper lines for QT measurement
        self.q_line = pg.InfiniteLine(
            pos=0.0, angle=90, movable=True,
            pen=pg.mkPen(color="#fbbf24", width=2, style=Qt.PenStyle.DashLine),
            label="Q-Onset: {value:.3f}s",
            labelOpts={"position": 0.92, "color": "#fbbf24", "fill": (26, 30, 44, 200)}
        )
        self.t_line = pg.InfiniteLine(
            pos=0.0, angle=90, movable=True,
            pen=pg.mkPen(color="#c084fc", width=2, style=Qt.PenStyle.DashLine),
            label="T-End: {value:.3f}s",
            labelOpts={"position": 0.78, "color": "#c084fc", "fill": (26, 30, 44, 200)}
        )

        self.plot_widget.addItem(self.q_line)
        self.plot_widget.addItem(self.t_line)

        self.on_caliper_moved: Optional[Callable[[float, float], None]] = None
        self.q_line.sigPositionChanged.connect(self._notify_caliper_change)
        self.t_line.sigPositionChanged.connect(self._notify_caliper_change)

    def display_signal(self, time_data: np.ndarray, signal_data: np.ndarray, r_peaks: np.ndarray) -> None:
        """Updates the plot waveform curve and R-peak markers."""
        self.signal_curve.setData(time_data, signal_data)
        if len(r_peaks) > 0:
            self.r_peak_scatter.setData(x=time_data[r_peaks], y=signal_data[r_peaks])
        else:
            self.r_peak_scatter.clear()
        self.plot_widget.enableAutoRange()

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


class MainWindow(QMainWindow):
    """Clinical Electrocardiogram Analysis & Colleague Exchange Workstation."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Repolaris — Ventricular Repolarization & ECG Workstation")
        self.resize(1420, 880)

        self.fs = 500.0
        self.time_data: Optional[np.ndarray] = None
        self.signal_data: Optional[np.ndarray] = None
        self.multi_lead_signals: Dict[str, np.ndarray] = {}
        self.current_lead_name: str = "Lead II"
        self.current_filename: str = tr("demo_filename")
        self.analysis_results: Optional[Dict[str, Any]] = None
        self.annotation_manager: Optional[AnnotationManager] = None
        self.current_beat_rr = 0.85

        self._setup_ui()
        self._load_synthetic_demo()

    def _setup_ui(self) -> None:
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

        # ---------------------------------------------------------------------
        # TOP WORKSPACE HEADER BAR (Actions & Active Record)
        # ---------------------------------------------------------------------
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

        # Language Selector Dropdown
        self.lbl_lang = QLabel(tr("language_label"))
        self.lbl_lang.setStyleSheet("font-weight: 600; color: #94a3b8;")
        top_layout.addWidget(self.lbl_lang)

        self.combo_lang = QComboBox()
        self.combo_lang.setToolTip("Switch application interface language (en, es, fr, de)")
        self.lang_codes = ["en", "es", "fr", "de"]
        for code in self.lang_codes:
            self.combo_lang.addItem(SUPPORTED_LANGUAGES[code], code)
        self.combo_lang.currentIndexChanged.connect(self._on_language_changed)
        top_layout.addWidget(self.combo_lang)

        top_layout.addSpacing(12)

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

        root_layout.addWidget(top_bar)

        # ---------------------------------------------------------------------
        # MAIN WORKSPACE SPLITTER (Waveform Canvas + Inspector Sidebar)
        # ---------------------------------------------------------------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter, stretch=1)

        # Left / Center Area: Waveform + Caliper HUD Strip
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.ecg_plot = ECGPlotWidget(self)
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

        # Advanced Section
        self.adv_group = QGroupBox(tr("adv_group_title"))
        adv_layout = QVBoxLayout(self.adv_group)
        adv_layout.setSpacing(4)
        self.lbl_adv_qtvi = QLabel(tr("adv_qtvi", val="--"))
        self.lbl_adv_qtrr = QLabel(tr("adv_qtrr", val="--"))
        self.lbl_adv_total = QLabel(tr("adv_total_cycles", count="--"))
        for lbl in (self.lbl_adv_qtvi, self.lbl_adv_qtrr, self.lbl_adv_total):
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
        self.beat_table = QTableWidget(0, 5)
        self.beat_table.setHorizontalHeaderLabels([
            tr("hdr_beat_num"), tr("hdr_time"), tr("hdr_class"), tr("hdr_qt"), tr("hdr_qtc")
        ])
        self.beat_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.beat_table.cellClicked.connect(self._on_beat_selected)
        self.beat_table.cellDoubleClicked.connect(self._on_beat_double_clicked)
        b_layout.addWidget(self.beat_table)
        self.tabs.addTab(beats_tab, tr("tab_beats"))

        side_layout.addWidget(self.tabs)
        splitter.addWidget(sidebar)

        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)

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

    def _on_language_changed(self, index: int) -> None:
        """Dynamically retranslates the UI when a new language is chosen."""
        if index < 0 or index >= len(self.lang_codes):
            return
        lang_code = self.lang_codes[index]
        set_locale(lang_code)
        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        """Updates all UI text elements to reflect current language."""
        self.title_lbl.setText(tr("app_title"))
        self.lbl_lang.setText(tr("language_label"))
        self.lead_lbl.setText(tr("channel_label"))
        self.btn_open.setText(tr("btn_open"))
        self.btn_open.setToolTip(tr("btn_open_tooltip"))
        self.btn_demo.setText(tr("btn_demo"))
        self.btn_demo.setToolTip(tr("btn_demo_tooltip"))
        self.btn_export.setText(tr("btn_export"))
        self.btn_export.setToolTip(tr("btn_export_tooltip"))

        # Calipers Strip
        self.lbl_cal_cue.setText(tr("calipers_title"))
        self.lbl_tag_raw.setText(tr("cal_raw_qt"))
        self.lbl_tag_bazett.setText(tr("cal_bazett"))
        self.lbl_tag_fridericia.setText(tr("cal_fridericia"))
        self.help_cue.setText(tr("cal_tip"))

        # Tabs
        self.tabs.setTabText(0, tr("tab_overview"))
        self.tabs.setTabText(1, tr("tab_events"))
        self.tabs.setTabText(2, tr("tab_beats"))

        # KPI Card Titles
        self.card_hr.title_lbl.setText(tr("kpi_hr_title"))
        self.card_qtc.title_lbl.setText(tr("kpi_qtc_title"))
        self.card_ectopic.title_lbl.setText(tr("kpi_ectopic_title"))
        self.card_sqi.title_lbl.setText(tr("kpi_sqi_title"))
        self.adv_group.setTitle(tr("adv_group_title"))

        # Table Headers
        self.events_table.setHorizontalHeaderLabels([
            tr("hdr_time"), tr("hdr_event"), tr("hdr_value"), tr("hdr_severity")
        ])
        self.beat_table.setHorizontalHeaderLabels([
            tr("hdr_beat_num"), tr("hdr_time"), tr("hdr_class"), tr("hdr_qt"), tr("hdr_qtc")
        ])

        # Re-render current metric evaluations
        if self.analysis_results:
            self._update_cards_and_tables()

    def _load_synthetic_demo(self) -> None:
        """Loads synthetic benchmark rhythms and populates standard demo leads."""
        self.fs = 500.0
        self.current_filename = tr("demo_filename")
        self.lbl_file_badge.setText(self.current_filename)

        self.time_data, lead2, true_r = generate_synthetic_ecg(
            duration_sec=12.0, fs=self.fs, heart_rate_bpm=72.0
        )
        lead_v5 = lead2 * 0.82
        lead1 = lead2 * 0.65

        self.multi_lead_signals = {
            "Lead II (Standard)": lead2,
            "Lead V5 (Precordial)": lead_v5,
            "Lead I (Frontal)": lead1,
        }

        self.combo_leads.blockSignals(True)
        self.combo_leads.clear()
        for name in self.multi_lead_signals:
            self.combo_leads.addItem(name)
        self.combo_leads.setCurrentIndex(0)
        self.combo_leads.blockSignals(False)

        self.current_lead_name = "Lead II (Standard)"
        self.signal_data = self.multi_lead_signals[self.current_lead_name]
        self._run_pipeline_and_display()

    def _open_file_dialog(self) -> None:
        """Opens any clinical recording, detects all available channels, and sets active lead."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("btn_open"),
            "",
            "All Supported ECG (*.pecg *.ecg *.e3c *.edf *.hea *.dat *.csv *.npy);;"
            "PECG Colleague Study (*.pecg);;"
            "ISHNE Holter Standard (*.ecg);;"
            "Excorde 3C Holter (*.e3c);;"
            "EDF Telemetry Patch (*.edf);;"
            "PhysioNet WFDB (*.hea *.dat);;"
            "All Files (*)",
        )
        if not path:
            return
        try:
            signals, fs, meta = load_ecg_dataset(path)
            self.multi_lead_signals = signals
            self.fs = fs

            self.current_filename = os.path.basename(path)
            self.lbl_file_badge.setText(self.current_filename)

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
            self.signal_data = self.multi_lead_signals[self.current_lead_name]
            self.time_data = np.arange(len(self.signal_data)) / self.fs
            self._run_pipeline_and_display()
        except Exception as e:
            QMessageBox.critical(self, tr("error_title"), str(e))

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

    def _run_pipeline_and_display(self) -> None:
        if self.signal_data is None:
            return
        self.analysis_results = analyze_ecg(self.signal_data, fs=self.fs)
        clean = self.analysis_results["clean_signal"]
        r_peaks = self.analysis_results["r_peaks"]
        beats = self.analysis_results["beats"]
        events = self.analysis_results.get("events", [])
        self.annotation_manager = self.analysis_results.get("annotations")

        if self.time_data is not None:
            self.ecg_plot.display_signal(self.time_data, clean, r_peaks)
            self.ecg_plot.plot_widget.setTitle(
                f"ECG Waveform — {self.current_lead_name}",
                color="#93c5fd",
                size="11pt",
            )

        self._update_cards_and_tables()

        if events:
            self._select_event(0)
        elif beats:
            self._select_beat(0)

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

        # 5. Advanced Repolarization section
        if qtvi is not None:
            self.lbl_adv_qtvi.setText(tr("adv_qtvi", val=f"{qtvi:.2f}"))
        else:
            self.lbl_adv_qtvi.setText(tr("adv_qtvi_na"))

        if qtrr is not None:
            self.lbl_adv_qtrr.setText(tr("adv_qtrr", val=f"{qtrr['slope']:.2f} (r={qtrr['pearson_r']:.2f})"))
        else:
            self.lbl_adv_qtrr.setText(tr("adv_qtrr_na"))

        self.lbl_adv_total.setText(tr("adv_total_cycles", count=summary['total_beats']))

        # Populate Beat Table
        self.beat_table.setRowCount(len(beats))
        for row, b in enumerate(beats):
            self.beat_table.setItem(row, 0, QTableWidgetItem(str(b["beat_index"] + 1)))
            self.beat_table.setItem(row, 1, QTableWidgetItem(f"{b['time_sec']:.2f}"))

            b_class = b.get("beat_class", "N")
            class_item = QTableWidgetItem(b_class)
            if b_class == "V":
                class_item.setForeground(QColor("#f87171"))
            elif b_class == "S":
                class_item.setForeground(QColor("#fbbf24"))
            elif b_class == "F":
                class_item.setForeground(QColor("#c084fc"))
            elif b_class == "N":
                class_item.setForeground(QColor("#34d399"))
            else:
                class_item.setForeground(QColor("#94a3b8"))

            self.beat_table.setItem(row, 2, class_item)
            self.beat_table.setItem(row, 3, QTableWidgetItem(f"{b['qt_ms']:.0f}"))
            self.beat_table.setItem(row, 4, QTableWidgetItem(f"{b['qtc']['bazett_ms']:.0f}"))

        # Populate Events Diary
        self.events_table.setRowCount(len(events))
        for row, ev in enumerate(events):
            item_time = QTableWidgetItem(f"{ev['timestamp_sec']:.2f}s")
            item_type = QTableWidgetItem(ev["event_type"].replace("_", " "))
            item_val = QTableWidgetItem(f"{ev['metric_value']:.0f} {ev['unit']}")
            item_sev = QTableWidgetItem(ev["severity"])

            if ev["severity"] == "CRITICAL":
                color = QColor("#f87171")
            elif ev["severity"] == "WARNING":
                color = QColor("#fbbf24")
            else:
                color = QColor("#60a5fa")

            item_type.setForeground(color)
            item_sev.setForeground(color)

            self.events_table.setItem(row, 0, item_time)
            self.events_table.setItem(row, 1, item_type)
            self.events_table.setItem(row, 2, item_val)
            self.events_table.setItem(row, 3, item_sev)

    def _select_beat(self, index: int) -> None:
        if not self.analysis_results or index >= len(self.analysis_results["beats"]):
            return
        beat = self.analysis_results["beats"][index]
        q_sec = beat["q_onset_sample"] / self.fs
        t_sec = beat["t_end_sample"] / self.fs
        self.current_beat_rr = beat["rr_sec"]

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

    def _on_beat_double_clicked(self, row: int, col: int) -> None:
        """Physician manual override: double clicking a beat allows diagnosis reclassification."""
        if not self.analysis_results or row >= len(self.analysis_results["beats"]):
            return
        beat = self.analysis_results["beats"][row]
        current_class = beat.get("beat_class", "N")

        options = [
            tr("opt_n"),
            tr("opt_v"),
            tr("opt_s"),
            tr("opt_f"),
            tr("opt_q"),
        ]
        choice, ok = QInputDialog.getItem(
            self,
            tr("override_title", num=row + 1),
            tr("override_prompt", curr=current_class),
            options,
            0,
            False,
        )
        if not ok:
            return

        new_label = choice[0]
        beat["beat_class"] = new_label

        if self.annotation_manager:
            self.annotation_manager.override_beat_label(
                sample=beat["r_peak_sample"],
                new_label=new_label,
                reviewer="Physician",
                notes=f"Manual override from {current_class} to {new_label}",
            )

        class_item = QTableWidgetItem(new_label)
        if new_label == "V":
            class_item.setForeground(QColor("#f87171"))
        elif new_label == "S":
            class_item.setForeground(QColor("#fbbf24"))
        elif new_label == "F":
            class_item.setForeground(QColor("#c084fc"))
        elif new_label == "N":
            class_item.setForeground(QColor("#34d399"))
        else:
            class_item.setForeground(QColor("#94a3b8"))
        self.beat_table.setItem(row, 2, class_item)

    def _on_event_selected(self, row: int, col: int) -> None:
        self._select_event(row)

    def _on_caliper_dragged(self, q_sec: float, t_sec: float) -> None:
        qt_sec = abs(t_sec - q_sec)
        qt_ms = qt_sec * 1000.0
        qtc = compute_qtc(qt_sec, self.current_beat_rr)
        self.lbl_cal_qt.setText(f"{qt_ms:.0f} ms")
        self.lbl_cal_bazett.setText(f"{qtc['bazett_ms']:.0f} ms")
        self.lbl_cal_fridericia.setText(f"{qtc['fridericia_ms']:.0f} ms")

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

        save_pecg(
            filepath=path,
            signals=lead_matrix,
            sampling_rate=self.fs,
            lead_names=lead_names,
            patient_info={"age": age, "race": race, "sex": "UNKNOWN", "indication": notes},
            annotations=ann_payload,
            events=self.analysis_results.get("events", []) if self.analysis_results else [],
            compression="zstd",
        )
        QMessageBox.information(self, tr("export_success_title"), tr("export_success_msg", path=path))


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
