# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-11-01

### Added
- **QT Dispersion (`repolaris.detection.dispersion`) & Transmural Dispersion ($T_{pe,d}$)**:
  - Multi-lead spatial repolarization heterogeneity quantification across synchronous recording channels (`calculate_qt_dispersion`, `resolve_lead_quorum`).
  - Formulations for absolute QT dispersion ($QT_d = \max QT - \min QT$), Fridericia rate-corrected dispersion ($QTc_d$), and T-peak to T-end transmural dispersion ($T_{pe,d}$ and precordial V1–V6 $T_{pe,d}$).
  - Lead-masking filters enforcing signal quality screening ($\text{pSQI}$, $\text{basSQI}$, $\text{SNR}$) and minimum T-wave amplitude ($\ge 50\ \mu\text{V}$) across dynamic lead quorums ($\ge 8$ leads for 12-lead ECG, $\ge 3$ leads for Holter).
- **Microvolt T-Wave Alternans (`repolaris.detection.twa`)**:
  - Dual analytical pathways: 128-beat Spectral FFT analysis (`compute_spectral_twa`, $0.5\text{ cycles/beat}$ alternans power with $k \ge 3.0$ and $V_{\text{alt}} \ge 1.9\ \mu\text{V}$ significance) with sub-sample parabolic R-peak alignment, and continuous Modified Moving Average (`compute_mma_twa`) tracking for ambulatory Holter monitoring.
- **Heart Rate Turbulence (`repolaris.detection.hrt`)**:
  - Biphasic baroreflex responsiveness modeling following solitary Premature Ventricular Contractions (`compute_heart_rate_turbulence`).
  - Algorithmic formulation of Turbulence Onset ($TO$) and ensemble Turbulence Slope ($TS$) across post-extrasystolic sinus windows with strict sinus purity filtering and ISHNE three-tier risk stratification (Category 0, 1, and 2).
- **Comprehensive Heart Rate Variability Suite (`repolaris.detection.hrv`)**:
  - Time-Domain (`compute_time_domain_hrv`): $SDNN$, $RMSSD$, $pNN50$, $CV\%$, and 5-minute circadian metrics ($SDANN$, $SDNN_\text{index}$) over validated Normal-to-Normal ($NN$) sequences.
  - Frequency-Domain (`compute_frequency_domain_hrv`): Welch power spectral density estimation (ULF, VLF, LF, HF, $LF/HF$ ratio, and normalized units $LF_\text{nu}$ / $HF_\text{nu}$) resampled onto a uniform 4 Hz grid via Berger step-integration.
  - Non-Linear Dynamics (`compute_nonlinear_hrv`): Poincaré plot ellipse geometry ($SD1$, $SD2$, $SD1/SD2$ ratio, ellipse area), Sample Entropy ($SampEn(m=2, r=0.2)$), and Detrended Fluctuation Analysis (short-term $\alpha_1$ and long-term $\alpha_2$ scaling exponents).
- **Multi-Beat QT-RR Hysteresis & Lag-Weighted Profiles (`repolaris.detection.hysteresis`)**:
  - Cardiac repolarization memory compensation replacing instantaneous $RR$ intervals with memory-weighted effective cycle length ($RR_\text{eff}$).
  - Exponential Weighting (`compute_effective_rr_exponential`) state-space recursive realization and Linear Weighting (`compute_effective_rr_linear`) historical decay profiles.
  - Patient-specific optimization routine (`optimize_hysteresis_parameter`) for lag decay constant ($\lambda^*$), 90% adaptation latency ($t_{90}$), half-life ($t_{1/2}$), and hysteresis-corrected Fridericia $QTc_\text{hyst}$.
- **Conditional Multi-Lead Workstation Gating & API Expansion**:
  - Implemented `MainWindow._evaluate_channel_capabilities()` and `card_qtd` in `src/repolaris/app.py` to automatically badge and disable spatial dispersion during single-lead wearable patch analysis ($< 3$ channels) while unlocking multi-lead dispersion when $\ge 3$ leads are present.
  - Exposed `analyze_dispersion`, `analyze_twa`, `analyze_hrt`, `analyze_hrv`, and `analyze_hysteresis` on `AnalysisAPI`.
  - Added `ROADMAP.md` and expanded automated verification suite to 65 unit tests (`tests/test_v060_autonomic_repolarization.py`).

### Fixed
- Added Hodges linear rate-correction formula ($QT_c = QT + 1.75 \cdot (\text{HR} - 60)$) to `compute_qtc()` and `summarize_beats()` in `src/repolaris/detection/pulse_metrics.py`.
- Upgraded `detect_t_end()` in `src/repolaris/detection/t_end.py` to implement the hybrid steepest-descent tangent intersection with the isoelectric baseline alongside the 15% amplitude-threshold fallback.
- Activated zero-phase IIR powerline notch filtering (`notch_filter`) in `src/repolaris/detection/pipeline.py`.
- Fixed CLI report dictionary key lookups in `src/repolaris/cli.py` (`slope`, `verdict`, and `timestamp_sec`) and updated CLI report headers to `Repolaris`.
- Removed stray scratch files (`src/repolaris/api/foo.py`, `src/repolaris/api/test.txt`, `update_changelog_canvas.py`) and repaired formatting in `docs/API_DOCUMENTATION.md`.

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

## [0.4.0] - 2026-10-30

### Added
- **In-Process Model-View-Controller (MVC) Architecture**:
  - Established unified in-process controller service layer in `src/repolaris/api/` (`StudyAPI`, `AnalysisAPI`, `ExportAPI`) providing high-level, zero-copy orchestration over domain models.
  - Refactored CLI (`cli.py`) and Desktop GUI (`app.py`) into pure View clients consuming `repolaris.api` exclusively, removing analytical duplication and enabling the CLI to execute headlessly without Qt dependencies.
  - Relocated declarative UI presentation assets to `src/repolaris/resources/` (`app.ui`), keeping `src/repolaris/utils/` (`signal.py`) strictly isolated for numerical signal synthesis and pure mathematical algorithms.
  - Configured `[tool.setuptools.package-data]` in `pyproject.toml` to automatically bundle `repolaris.resources` assets.
- **Application Menu Bar & Import/Export Workflow**:
  - Replaced legacy "Open file" button with standardized **"Import"** (`📂 Import`) across the workstation header and all 5 localization dictionaries (`en`, `es`, `fr`, `de`, `pt`).
  - Added full desktop Application Menu Bar (`QMenuBar`) structured into File, Preferences, and Help.
- **Portuguese (Português) Internationalization**:
  - Full native Portuguese translation dictionary across all UI labels, KPI cards, caliper metrics, diagnostic overrides, and triage alerts.
  - Added Portuguese locale toggle (`pt`) to the workstation language selector dropdown.
- **Security & Ingestion Hardening (Anti-DoS & Decompression Bomb Mitigations)**:
  - Applied defensive boundaries across `.pecg`, ISHNE `.ecg`, EDF/EDF+, PhysioNet WFDB, Excorde 3C `.e3c`, and delimited files.
  - Neutralized decompression bombs in Zstandard (`max_output_size`), Deflate (`zlib.decompressobj` bounded stream), and Excorde 3C ZIP archives (`ZipInfo.file_size <= 2 GB`).
  - Enforced 2 GB global file ceiling, 250 MB text ingestion ceiling, 10 MB metadata block ceilings, and bounded channel ($1\le N\le 64$) and sample counts ($1\le N\le 100\text{M}$).
  - Enforced `allow_pickle=False` on `.npy` matrix ingestion and sanitized path traversal risks in WFDB headers.
- **Workstation UI/UX Theme Engine, Clinical Grid, Calipers & Zoom**:
  - Moved interface language selection from the top navigation bar into a dedicated modal `SettingsDialog` (`⚙️ Settings`).
  - Added comprehensive Color Scheme (Theme) engine supporting **Clinical Dark (Default)**, **Clinical Light (Paper)**, and **High Contrast / Color Blind Safe (Okabe-Ito / Tol)**.
  - Independent canvas color scheme selector supporting 5 high-contrast palettes: Dark, Clinical Light, Classic ECG Paper, Color Blind Safe, and Emerald Phosphor.
  - Step-wise clinical ECG zoom engine providing standardized paper sweep speeds ($12.5$, $25$, $50$, $100\text{ mm/s}$) and voltage sensitivity gains ($2.5$, $5$, $10$, $20\text{ mm/mV}$).
  - Segmented toggle buttons for clinical ECG grid (`⊞ Lines`, `⁚ Dots`, `⊘ Off`), grid-linked scale indicator badge (`📐 Scale: {speed} mm/s | {gain} mm/mV`), and `TimeAxisItem` millisecond timestamp formatting (`hh:mm:ss:xxx`).
  - Exported complete Qt 6 Designer XML UI definition (`src/repolaris/resources/app.ui`).

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

[Unreleased]: https://github.com/numbecho/repolaris/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/numbecho/repolaris/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/numbecho/repolaris/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/numbecho/repolaris/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/numbecho/repolaris/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/numbecho/repolaris/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/numbecho/repolaris/releases/tag/v0.1.0
