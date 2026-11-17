# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.1] - 2026-11-16

### Added
- **Clinical Workstation UX Upgrades (`repolaris.app`, `repolaris.i18n`, `repolaris.resources`)**:
  - **Keyboard Beat Navigation (`Left`/`Right` Arrows & `◀`/`▶` Toolbar Buttons)**: Added `prev_beat()`, `next_beat()`, `btn_prev_beat`, and `btn_next_beat` to step cycle-by-cycle, sync `beat_table` row selection, and center Q/T calipers.
  - **Single-Key AAMI Reclassification Hotkeys (`N`, `V`, `S`, `F`, `Q`)**: Added `reclassify_active_beat()` and `keyPressEvent()` bindings so pressing `N`, `V`, `S`, `F`, or `Q` reclassifies the active beat in-place, re-evaluates `detect_rhythm_patterns()`, recalculates `ectopic_summary`, `hrv`, and `hrt`, and logs an immutable audit entry in `AnnotationManager`.
  - **Color-Coded Ectopic R-Peak Markers & On-Canvas Tags (`ECGPlotWidget.display_signal`)**: Color-codes R-peak markers by AAMI class (`#34d399` Normal, `#f87171` PVC, `#fbbf24` PAC, `#c084fc` Fusion) and renders on-canvas `pg.TextItem` tags (`V`, `S`, `F`, `Q`) above non-normal R-peaks.
  - **Live Caliper `RR` Readout & Persistent Caliper Drag Calibration (`_on_caliper_dragged`)**: Added `lbl_tag_rr` / `lbl_cal_rr` to the caliper HUD strip and persisted manual Q-onset/T-end drags directly into `analysis_results["beats"]`, `summary`, `beat_table`, and `card_qtc`.
  - **Expanded 8-Column Clinical Tables & 100% 5-Language Parity**: Expanded `beat_table` (adding `Pattern`, `RR (ms)`, `HR (BPM)`), `holter_af_table` (adding `Max HR`, `Shannon Ent.`, `Irregularity`), and `qtrr_models_table` (adding `Slope (α)`, `Pearson r`, `AIC`) to 8 columns each, and localized all remaining banners, labels, and tooltips across `en`, `es`, `fr`, `de`, and `pt`.
- **Python 3.14 Syntax Modernization & Additive `uv` / `ruff` Tooling Suite (`tests/test_tooling_uv_ruff.py`, `.github/workflows/build-artifacts.yml`)**:
  - Modernized all 56 Python modules across `src/repolaris/` and `tests/` to native `X | Y` unions, built-in generics (`list`, `dict`, `tuple`, `set`), `StrEnum`, `match`/`case` structural pattern matching, and `contextlib.suppress`, eliminating duplicated dispatch ladders and dead code.
  - Added `.python-version` (`3.14`), `[tool.uv]`, `[tool.ruff]` (`target-version = "py314"`), PEP 735 `[dependency-groups]`, the `uv-ruff-test` CI job, and `tests/test_tooling_uv_ruff.py` alongside the existing `pip` + `unittest` suite (**97 passing unit tests**).

### Fixed
- **Hostile Audit Signal & I/O Hardening (`ecg_loader.py`, `pipeline.py`, `hysteresis.py`, `sqi.py`, `hamilton_classifier.py`, `events.py`, `qtrr.py`, `qtvi.py`)**:
  - Fixed `load_ecg_dataset()` attribute mappings for ISHNE (`.ecg`) and EDF (`.edf`) records, added `SignalBuffer.close()` context-manager cleanup for temporary `np.memmap` directories, and removed the 10-second minimum chunk clamp in `stream_ecg_chunks()`.
  - Fixed hysteresis effective RR key resolution (`rr_eff_ew_sec` / `rr_eff_lw_sec`), assigned forward RR interval to Beat 0, evaluated `basSQI` and `snr_db` on raw pre-filtered signals while enforcing `kSQI` and `snr_db` in Stage 1 SQI gating, wired `HamiltonBeatClassifier` into `analyze_ecg()`, and added Tikhonov ridge stabilization for constant-rate QT-RR regression.

## [0.8.0] - 2026-11-14

### Added
- **Long-Term Holter Out-of-Core Streaming & `np.memmap` Buffering (`repolaris.io.ecg_loader`, `repolaris.detection.pipeline`)**:
  - Added `SignalBuffer`, `open_ecg_buffer()`, and `stream_ecg_chunks()` supporting memory-mapped (`np.memmap`) disk-backed signal buffers for continuous 24h–48h multi-lead recordings without RAM exhaustion.
  - Added `analyze_ecg_stream()` in `pipeline.py` (exposed via `AnalysisAPI.analyze_stream()` and CLI `--stream`) to process overlapping windows, eliminate filter edge transients, deduplicate boundary R-peaks, and aggregate study-wide HRV, HRT, AF burden, and hourly trends.
- **Automated Printable Clinical PDF Report Generator (`repolaris.io.pdf_report`, `ExportAPI.export_clinical_pdf`)**:
  - Added `generate_clinical_pdf_report()` producing publication-grade 2-page clinical PDF reports via `matplotlib.backends.backend_pdf.PdfPages`.
  - Page 1 includes Patient & Study Demographics, Executive Repolarization & Arrhythmia KPI Summary Table, a 10-second calibrated ECG disclosure strip with R-peak/Q-onset/T-end markers, and the Clinical Events Diary.
  - Page 2 includes the Hourly Holter Distribution Table, Poincaré Lorentz plot ($RR_n$ vs $RR_{n+1}$), and QT-RR Restitution & Hysteresis curve.
- **Workstation Holter Triage Tab & PDF Export (`repolaris.app`, `repolaris.i18n`, `repolaris.cli`)**:
  - Added the `🕒 Holter Triage` tab (`holter_trends_table`, `holter_af_table`, `lbl_holter_summary_banner`) with one-click seeking to any hourly epoch or AF episode.
  - Added `📄 PDF Report` toolbar button, `File -> Export Clinical PDF Report... (Ctrl+P)` menu action, and CLI `--pdf` / `--stream` flags across all 5 supported languages (`en`, `es`, `fr`, `de`, `pt`).
- **Comprehensive v0.8.0 Verification Suite (`tests/test_v080_streaming_and_pdf.py`)**:
  - Added 5 automated unit tests validating `np.memmap` chunk streaming, boundary R-peak deduplication, PDF report generation, CLI `--pdf`/`--stream` flags, and GUI Holter Triage tab widgets (full test suite: **90 passing unit tests**).

## [0.7.1] - 2026-11-06

### Added
- **Atrial Fibrillation (AF) / Flutter Detection and Burden Analysis (`repolaris.detection.af_detector`)**:
  - Added native `detect_atrial_fibrillation()`, `compute_rr_entropy()`, and `compute_rr_irregularity()`.
  - Implements sliding-window Shannon entropy analysis on local RR distributions coupled with successive RR median absolute difference (MAD) irregularity scoring.
  - Automatically segments sustained AF episodes ($\ge 30\text{ s}$), calculating episode onset, offset, duration, heart rate extrema, irregularity indices, and overall recording AF burden percentage conforming to clinical Holter standards.
- **Hourly Arrhythmia Trend Histograms & Holter Summary (`repolaris.detection.trends`)**:
  - Added `generate_hourly_trends()` producing 1-hour epoch distribution tables for 24h/48h Holter monitoring.
  - Tracks hourly heart rate extrema (Min, Mean, Max HR), ventricular ectopy counts (PVCs, Couplets, VT Runs), supraventricular ectopy (PACs), sinus pauses ($\ge 2.0\text{ s}$, $\ge 2.5\text{ s}$), and hourly AF burden.
- **AF Entropy Stabilizer for Hamilton Beat Classifier (`repolaris.detection.hamilton_classifier`)**:
  - Added rhythm-entropy gating to the Patrick Hamilton (2002) OSEA template matching classifier to prevent false-positive PVC classifications during chaotic rhythm variations (AF with rapid ventricular response).
- **Hardening and Edge-Case Ingestion Resilience (`repolaris.io`)**:
  - **SCP-ECG Guarding**: Hardened `read_scp_ecg` to explicitly check Section 0 pointer tables for Section 2 (Huffman table decompression) and Section 5 (Reference beat residual subtraction), gracefully raising `NotImplementedError` rather than parsing corrupted streams.
  - **HL7 aECG Locale Delimiter Normalization**: Hardened `read_hl7_aecg` to sanitize European comma decimal formatting (`0,005 mV`) to standard IEEE floats.
  - **Safe Pulse Metrics & Events Handling**: Protected `summarize_beats()` and `detect_clinical_events()` against `TypeError` when handling unassigned or NaN heart rates on initial cycles.
- **Comprehensive v0.7.1 Test Suite (`tests/test_v071_hardening.py`)**:
  - Added 5 new automated unit tests covering AF episode segmentation, Holter hourly binning, SCP compression guards, European decimal parsing, and pipeline integration (full test suite: **85 passing unit tests**).

## [0.7.0] - 2026-11-05

### Added
- **Open International Format Ingestion Layer (`repolaris.io`)**:
  - Added native **DICOM Waveform** reader (`read_dicom_waveform`, `is_dicom_file` in `repolaris.io.dicom_reader`) supporting 12-Lead (SOP Class `1.2.840.10008.5.1.4.1.1.9.1.1`) and Ambulatory ECG (SOP Class `1.2.840.10008.5.1.4.1.1.9.1.2`), extracting multiplexed 16-bit waveform arrays, channel sensitivity/baseline, and patient metadata into calibrated physical millivolts with zero external PACS software requirements.
  - Added native **HL7 Annotated ECG XML** reader (`read_hl7_aecg`, `is_hl7_xml` in `repolaris.io.hl7_reader`) for ANSI/HL7 aECG clinical trial files, parsing MDC_ECG lead sequences, increment sample rates, and scale multipliers.
  - Added native **SCP-ECG** standard communication protocol reader (`read_scp_ecg`, `is_scp_file` in `repolaris.io.scp_reader`) for European CEN EN 1064 / ISO 13713 files, decoding Section 0 pointer tables, Section 3 lead definitions, and Section 6 difference-encoded rhythm data.
  - Added intelligent format auto-detection state machine (`sniff_ecg_format`) in `ecg_loader.py` that inspects binary magic headers (`DICM`, SCP Section 0, HL7 XML namespaces, ISHNE tags) rather than relying solely on file extensions.
- **Patrick Hamilton (2002) OSEA Template Beat Classifier (`repolaris.detection.hamilton_classifier`)**:
  - Implemented the unencumbered, public-domain Hamilton (2002) Open Source ECG Analysis template-matching engine (`HamiltonBeatClassifier`).
  - Features dynamic morphology clustering with a 12.5% running adaptation rate on dominant normal templates, dual prematurity gating (local running RR context < 0.82), and compensatory pause detection, targeting &ge;95% ventricular positive predictivity on MIT-BIH benchmarks.
- **Workstation Open File Dialog Enhancements (`repolaris.app`)**:
  - Expanded `_open_file_dialog()` in `MainWindow` with native file filter selectors for DICOM Waveform (`*.dcm`, `*.dicom`), HL7 aECG XML (`*.xml`, `*.aecg`), and SCP-ECG Standard (`*.scp`).
- **Comprehensive v0.7.0 Verification Suite (`tests/test_v070_format_support.py`)**:
  - Added automated unit tests for DICOM waveform decoding, HL7 aECG XML parsing, SCP-ECG binary rhythm extraction, format sniffing, and Hamilton OSEA template classification, bringing the active test suite to 80 passing tests.

## [0.6.1] - 2026-11-03

### Added
- **Peer-Reviewed Anti-Regression Conditioning (`repolaris.config`, `repolaris.preprocessing`)**:
  - Updated `FilterConfig.lowcut` default to `0.05 Hz` (with `highcut = 45.0 Hz` and narrow powerline notch `notch_quality = 30.0`) to preserve low-frequency ST-T morphology per AHA/ACC/HRS guidelines (Kligfield et al., 2007), while retaining the cascaded two-stage median baseline filter (`200 ms / 600 ms`; de Chazal et al., 2004).
- **Two-Stage Signal Quality Assessment & Six-Index Pairwise Lead Voting (`repolaris.detection.sqi`)**:
  - Added fourth-moment kurtosis (`compute_ksqi`), third-moment skewness (`compute_ssqi`), and `rank_leads_two_stage()`.
  - Enforces Stage 1 absolute physiological rejection gates (`pSQI`, `basSQI`, `kSQI`, `sSQI`, `SNR_dB`, non-flatline ratio; Li, Rajagopalan & Clifford, 2014) prior to Stage 2 pairwise six-index relative lead voting (VI_k in [-6.0, +6.0]; Suárez-León et al., 2018) so detached or saturated leads can never win a relative vote.
- **Zhang (2006) Sliding-Window Area T-End Delineation (`repolaris.detection.t_end`)**:
  - Added `method="zhang_area"` implementing the sliding-window area (SWA) algorithm (Zhang et al., *IEEE TBME* 2006) alongside `hybrid`, `tangent` (ICH E14), and `threshold` modes.
- **Complete 10-Model Domain-Guarded QT-RR Restitution Suite (`repolaris.detection.qtrr`)**:
  - Expanded `SUPPORTED_QTRR_MODELS` and `fit_all_qtrr_models()` to all 10 biparametric models from Pueyo et al. (2004) (`linear`, `hyperbolic`, `parabolic_log`, `logarithmic`, `shifted_log`, `exponential`, `arctan`, `tanh`, `arcsinh`, `arccosh`) with Vandermonde and domain positivity conditioning guards (`_safe_linear_fit`) and individualized QTc,ind(RR = 1.0 s) estimation.
- **Interactive Workstation QT-RR Settings & Dynamics Visualization Tab (`repolaris.app`, `repolaris.i18n`)**:
  - Enhanced `SettingsDialog` (`⚙️ Settings`) with persistent selectors for all 10 Pueyo (2004) QT-RR models (plus `Auto-Select Best Model`), multi-beat hysteresis compensation (`EW`, `LW`, `Raw RR`), and T_end delineation method (`hybrid`, `tangent`, `zhang_area`, `threshold`).
  - Added the `📈 QT-RR Dynamics` tab in `MainWindow` featuring an interactive PyQtGraph (RR, QT) vs. (RR_eff, QT) hysteresis cloud, continuous parametric regression curve, individualized QTc,ind marker, live telemetry banner, and clickable 10-model leaderboard (`qtrr_models_table`).
