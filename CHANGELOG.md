# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-10-31

### Added
- **Multi-Threaded I/O & Parallel Channel Calibration**:
  - Parallelized multi-lead signal decoupling and channel calibration in `src/repolaris/io/ecg_loader.py` using `concurrent.futures.ThreadPoolExecutor`.
  - Enabled multi-threaded Zstandard waveform compression in `src/repolaris/io/pecg_format.py` utilizing available CPU cores (`threads=min(os.cpu_count(), 4)`).
  - Standardized `progress_callback: Optional[Callable[[float, str], None]] = None` across `StudyAPI`, `AnalysisAPI`, and `ExportAPI`.
- **Asynchronous Desktop GUI StatusBar & Progress Bar**:
  - Integrated `QStatusBar` into `MainWindow` and `app.ui` featuring real-time task status messages and high-contrast `QProgressBar`.
  - Implemented `BackgroundTaskWorker(QThread)` in `src/repolaris/app.py` for non-blocking asynchronous execution during study loading, signal analysis, and `.pecg` container export.
  - Added localized status messages (`status_ready`, `status_loading`, `status_analyzing`, `status_exporting`) across all 5 supported languages (`en`, `es`, `fr`, `de`, `pt`).
- **Dynamic CLI Terminal Progress Reporting**:
  - Implemented responsive ANSI block progress bars (`[██████████░░░░] 70% — <message>`) in `src/repolaris/cli.py` across `demo`, `analyze`, and `export` subcommands.
- **UI Layout Precompiler Engine**:
  - Added automated UI precompiler tool in `src/repolaris/resources/compile_ui.py` supporting `pyuic6`, `PyQt6.uic`, `pyside6-uic`, and a standalone zero-dependency fallback generator.
  - Precompiled `src/repolaris/resources/app.ui` into `src/repolaris/resources/ui_app.py` providing `Ui_MainWindow` for cold-start performance and static type safety.
  - Documented manual and automated UI compilation workflows across `README.md`, `wiki/Developer-Guide.md`, and `docs/wiki/Developer-Guide.md`.

## [0.4.0] - 2026-10-30

### Added
- **In-Process Model-View-Controller (MVC) Architecture**:
  - Established unified in-process controller service layer in `src/repolaris/api/` (`StudyAPI`, `AnalysisAPI`, `ExportAPI`) providing high-level, zero-copy orchestration over domain models.
  - Refactored CLI (`cli.py`) and Desktop GUI (`app.py`) into pure View clients consuming `repolaris.api` exclusively, removing analytical duplication and enabling the CLI to execute headlessly without Qt dependencies.
  - Relocated declarative UI presentation assets to `src/repolaris/resources/` (`app.ui`), keeping `src/repolaris/utils/` (`signal.py`) strictly isolated for numerical signal synthesis and pure mathematical algorithms.
  - Configured `[tool.setuptools.package-data]` in `pyproject.toml` to automatically bundle `repolaris.resources` assets.
- **Application Menu Bar & Import/Export Workflow**:
  - Replaced legacy "Open file" button with standardized **"Import"** (`📂 Import`) across the workstation header and all 5 localization dictionaries (`en`, `es`, `fr`, `de`, `pt`).
  - Added full desktop Application Menu Bar (`QMenuBar`) structured into File, Preferences, and Help:
    - **File (`File(open study | export study | close study || exit)`):** Open Study (`Ctrl+O`), Export Study (`Ctrl+E`), Close Study (`Ctrl+W`), and Exit (`Ctrl+Q`).
    - **Preferences (`Preferences(Languages | Interface theme | Canvas theme | calipers toggle)`):** Direct dropdown submenus for Languages (5 locales), Interface Theme (3 schemes), Canvas Theme (5 palettes), and checkable Calipers toggle (`Ctrl+K`).
    - **Help (`Help(shortcut link to wiki | License | about)`):** Documentation & Wiki link (`F1`), Apache-2.0 License viewer, and About Repolaris modal detailing brand, credits, and release version (v0.4.0).
- **QT Dispersion (QTd) & Transmural Dispersion (Tpe Dispersion)**:
  - Multi-lead spatial repolarization heterogeneity quantification across synchronous recording channels.
  - Formulations for absolute dispersion ($QT_d = \max QT - \min QT$), Fridericia rate-corrected dispersion ($QTc_d$), and T-peak to T-end dispersion ($T_{pe,d}$).
  - Lead-masking filters enforcing minimum signal quality ($\text{pSQI} \ge 0.65$, $\text{basSQI} \ge 0.85$, $\text{SNR} \ge 12\text{ dB}$) and minimum T-wave amplitude ($> 50\ \mu\text{V}$) across a minimum quorum of $\ge 3$ diagnostic leads.
- **Microvolt T-Wave Alternans (TWA)**:
  - Dual analytical pathways: 128-beat Spectral FFT analysis ($0.5\text{ cycles/beat}$ alternans power with statistical $k$-score significance) and continuous Modified Moving Average (MMA) method for ambulatory Holter monitoring.
  - Automated beat selector isolating Class `N` (sinus) rhythms during sustained heart rate intervals ($90\text{--}120\text{ bpm}$) with cubic-spline baseline wander suppression.
- **Heart Rate Turbulence (HRT)**:
  - Biphasic baroreflex responsiveness modeling following solitary Premature Ventricular Contractions (Class `V` / PVCs).
  - Algorithmic formulation of Turbulence Onset ($TO$) and Turbulence Slope ($TS$) across a 20-beat post-extrasystolic window.
  - Standardized three-tier autonomic mortality risk stratification (Category 0, 1, and 2).
- **Comprehensive Heart Rate Variability (HRV) Suite**:
  - Time-Domain: $SDNN$, $RMSSD$, $pNN50$, and 24-hour circadian metrics ($SDANN$, $SDNN_\text{index}$) over validated Normal-to-Normal ($NN$) sequences.
  - Frequency-Domain: Welch power spectral density estimation (VLF, LF, HF, $LF/HF$ ratio, and normalized units $LF_\text{nu}$ / $HF_\text{nu}$) resampled onto a uniform 4 Hz grid via Berger step-integration.
  - Non-Linear Dynamics: Poincaré plot geometry ($SD1$, $SD2$, $SD1/SD2$ ratio), Sample Entropy ($SampEn(m=2, r=0.2)$), and Detrended Fluctuation Analysis (short-term $\alpha_1$ and long-term $\alpha_2$ scaling exponents).
- **Multi-Beat QT-RR Hysteresis & Lag-Weighted Profiles**:
  - Cardiac repolarization memory compensation replacing instantaneous $RR$ intervals with memory-weighted effective cycle length ($RR_\text{eff}$).
  - Exponential Weighting (EW) state-space recursive realization and Linear Weighting (LW) historical decay profiles.
  - Optimization routine for patient-specific lag decay parameter ($\lambda^*$) and 90% adaptation time metric ($t_{90}$).
- **Portuguese (Português) Internationalization**:
  - Full native Portuguese translation dictionary across all UI labels, KPI cards, caliper metrics, diagnostic overrides, and triage alerts.
  - Added Portuguese locale toggle (`pt`) to the workstation language selector dropdown.
- **Security & Ingestion Hardening (Anti-DoS & Decompression Bomb Mitigations)**:
  - Applied defensive boundaries across `.pecg`, ISHNE `.ecg`, EDF/EDF+, PhysioNet WFDB, Excorde 3C `.e3c`, and delimited files.
  - Neutralized decompression bombs in Zstandard (`max_output_size`), Deflate (`zlib.decompressobj` bounded stream), and Excorde 3C ZIP archives (`ZipInfo.file_size <= 2 GB`).
  - Enforced 2 GB global file ceiling, 250 MB text ingestion ceiling, 10 MB metadata block ceilings, and bounded channel ($1\le N\le 64$) and sample counts ($1\le N\le 100\text{M}$).
  - Enforced `allow_pickle=False` on `.npy` matrix ingestion and sanitized path traversal risks in WFDB headers.
  - Implemented GUI error modal popups for security/specification violations and clinical warnings for zeroed or flat-line leads.
- **Workstation UI/UX Integration & Conditional Multi-Lead Gating**:
  - Moved interface language selection from the top navigation bar into a dedicated modal `SettingsDialog` (`⚙️ Settings`).
  - Added comprehensive Color Scheme (Theme) engine supporting **Clinical Dark (Default)**, **Clinical Light (Paper)**, and **High Contrast / Color Blind Safe (Okabe-Ito / Tol)**.
  - Implemented WCAG AAA-compliant accessibility: Okabe-Ito palette, distinct dashed vs. dash-dot caliper line styles for achromatopsia, and high-visibility diamond R-peak markers.
  - Enabled live real-time theme and locale propagation across PyQtGraph canvases, curves, calipers, KPI cards, tables, and dialogs without restarting.
  - Dynamic channel-sensing state machine in `repolaris-gui` (`app.py`): automatically disables and badges spatial dispersion widgets during single-lead wearable patch analysis while activating full multi-channel butterfly overlays and 12-lead polar radar plots when $\ge 3$ synchronous leads are detected.
  - Dedicated diagnostic docks for Poincaré ellipse scatter, Welch PSD frequency band distribution, ST-T alternans overlay, post-PVC ensemble tachogram, and dynamic QT-RR hysteresis loop collapse.
- **Waveform Canvas Customization, Clinical Grid, Calipers & Zoom**:
  - Independent canvas color scheme selector (Canvas Theme dropdown in canvas header and Settings dialog) supporting 5 high-contrast palettes: Dark (Obsidian & Cyan), Clinical Light (Paper & Midnight), Classic ECG Paper (Thermal Pink & Jet Black), High Contrast / Color Blind Safe (Pitch Black & Okabe-Ito Sky Blue), and Emerald Phosphor.
  - Enhanced caliper contrast and stroke distinction (Q-onset vs. T-end) guaranteeing sharp visual separation against all canvas backgrounds and lead plots, with distinct line patterns (dashed vs. dash-dot) for monochromatic and achromatopsia accessibility.
  - Step-wise clinical ECG zoom engine providing standardized paper sweep speeds ($12.5$, $25$, $50$, $100\text{ mm/s}$) and voltage sensitivity gains ($2.5$, $5$, $10$, $20\text{ mm/mV}$), paired with step-wise zoom buttons (`+` / `−`), baseline standard reset (`1:1`), and full recording fit (`⤢`).
  - Segmented toggle buttons for clinical ECG grid (`⊞ Lines`, `⁚ Dots`, `⊘ Off`) providing one-click switching directly from the canvas toolbar.
  - Interactive draggable vertical lines controls: toggle button (`📏 Calipers`) to show/hide measurement cursors, `⟲ Center` to snap calipers to the visible window center, and `➕ Line` to drop arbitrary draggable vertical measurement cursors.
  - Grid-linked scale indicator badge: dynamically formats active calibration (`📐 Scale: {speed} mm/s | {gain} mm/mV`) and is visible ONLY when a grid is enabled, automatically hiding when grid is toggled to Off.
  - Clinical axis nomenclature: Y-axis explicitly named `Voltage (mV)` and X-axis explicitly named `Time (hh:mm:ss:xxx)` with custom `TimeAxisItem` formatting seconds down to millisecond precision (`hh:mm:ss:xxx`).
- **Qt 6 Designer XML UI File Export (`mainwindow.ui`)**:
  - Exported complete, well-formed Qt 6 Designer XML UI definition (`mainwindow.ui` and `src/repolaris/mainwindow.ui`) modeling the full 76-widget workstation layout.
  - Fully mapped layouts, top action header, canvas toolbar (zoom, grid toggles, caliper controls), promoted pyqtgraph `PlotWidget`, caliper HUD strip, and 4-tab clinical inspector sidebar (Overview, Events Diary, Beat Classification, and Study & Patient Metadata).

## [0.3.0] - 2026-10-29

### Added
- Upgraded runtime to Python >= 3.14 minimum.
- Automated packaging with BeeWare Briefcase (Debian, Windows MSI, macOS bundles).
- Native Rich Text License (`LICENSE.rtf`) for Windows WiX installer.
- Modern ISO 8601 UTC timestamp logging via `datetime.now(timezone.utc)`.

### Removed
- Legacy MATLAB matrix loader (`mat_reader.py`) and associated `.mat` ingestion branches.
- Nuitka prototype build scripts and packaging dependencies.

### Changed
- Refactored Excorde 3C unit tests into `test_pipeline.py`.
- Modernized package metadata to strict PEP 639 standard.

### Fixed
- Fixed Debian packaging requirement by providing formal `CHANGELOG.md`.
- Fixed macOS ARM64 SciPy wheel installation via `min_os_version = "13.0"`.
- Fixed Windows WiX XML entity parsing by replacing raw ampersand in description.
- Fixed Linux system Python version alignment in GitHub Actions CI.

## [0.2.0] - 2026-10-28

### Added
- Rebranded and redesigned from PyECG to Repolaris.
- Universal zero-dependency multi-format ingestion (ISHNE 1.0, PhysioNet WFDB, EDF/EDF+, Excorde 3C).
- High-performance 60fps PyQtGraph GUI workstation with real-time digital calipers.
- Portable Clinical ECG (`.pecg`) container format with Zstandard compression and cryptographic de-identification.
- Clinical Events Triage Diary and immutable AnnotationManager with audit trails.
- Multi-language internationalization (English, Spanish, French, German).
- Automated 31-case verification test suite.

## [0.1.0] - 2018-06-01

### Added
- Foundational PyECG research software (Suárez-León et al., Universidad de Oriente / KU Leuven).
- Rate-corrected QT formulas (Bazett, Fridericia, Framingham, Hodges).
- Berger QT Variability Index (QTVI) and 4 Hz uniform step-integration resampling.

[Unreleased]: https://github.com/numbecho/repolaris/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/numbecho/repolaris/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/numbecho/repolaris/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/numbecho/repolaris/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/numbecho/repolaris/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/numbecho/repolaris/releases/tag/v0.1.0
