# Repolaris Development Roadmap

This document tracks architectural milestones, clinical electrophysiology modules, and future development targets for the **Repolaris** framework.

---

## Completed Milestones

### v0.9.9 — SCP-ECG Huffman 19999, Phasor Delineator, Derived 12-Lead & Native EC57 CLI (Current Release)
- **[IMPLEMENTED] CEN EN 1064 Default Huffman Table `19999` & Section 5 Decoder (`io/scp_reader.py`)**: Decodes compressed SCP-ECG rhythm files, Section 5 reference-beat residuals, and standard CEN EN 1064 Table 8 lead IDs (`61–64`).
- **[IMPLEMENTED] Derived 12-Lead Reconstruction (`io/ecg_loader.py`)**: Computes `III`, `aVR`, `aVL`, and `aVF` from independent leads `I` and `II` for 8-lead clinical resting ECGs.
- **[IMPLEMENTED] Martínez et al. (2010) Phasor Transform Delineator (`detection/t_end.py`, `plugins.py`)**: Selectable via `method="phasor"` and registered as a built-in `GLOBAL_PLUGIN_REGISTRY` delineator (`"phasor"`).
- **[IMPLEMENTED] Native `.atr`/`.ann` Benchmarking & Contract Audit (`cli.py`, `pipeline.py`, `tests/test_v099_upgrades_and_contract.py`)**: Direct `repolaris benchmark --input <record> --reference <atr|ann>`, unified `ectopic_summary` schema between `analyze_ecg()` and `analyze_ecg_stream()`, 100% 5-language `i18n` parity, and **130 passing unit tests** (`100%` Ruff `py314` clean).

### v0.9.7 – v0.9.8 — Pathological Edge-Case Hardening & Streaming Equivalence Audit
- **[IMPLEMENTED] Hostile Signal Sanitization (`detection/pipeline.py`, `tests/test_v097_v098_stress_audit.py`)**: Flatline/lead-off `0`-beat gating, mid-stream `NaN`/`Inf` linear interpolation (`0` warnings), and stress verification across `30–220 BPM`, AF, `6 s` pauses, inverted morphology, and `125–2000 Hz`.
- **[IMPLEMENTED] Streaming Parity & Multi-Format Batch Stress**: Verified `0` beat drops/duplicates (`720/720` beats) between `analyze_ecg()` and `analyze_ecg_stream()`, plus mixed-format `BatchAPI` and `ExportAPI.export_clinical_pdf()` cohort stress tests.

### v0.9.6 — Pre-1.0 Regulatory Validation, Circadian Stratification, Cohort Batch Runner & Plugin Registry
- **[IMPLEMENTED] ANSI/AAMI EC57 & CSE Fiducial Benchmark Certification Engine (`benchmarks/ec57.py`, `repolaris benchmark` CLI)**: 1-to-1 monotonic `bxb` beat matching ($\pm 150\text{ ms}$), $5 \times 5$ AAMI confusion matrix, `epi` episode overlap, and CSE Working Party / PhysioNet QTDB fiducial boundary standard deviation verification.
- **[IMPLEMENTED] Circadian Day/Night (Diurnal vs. Nocturnal) Repolarization & Autonomic Stratification (`detection/circadian.py`)**: Nocturnal HR dipping ($\%$), diurnal vs. nocturnal $QTcF / J\text{–}T_{\text{peak}}c / T_{pe} / STV_{QT}$, nocturnal $\Delta QTcF$ lengthening (LQT2/LQT3 vs. LQT1), and diurnal vs. nocturnal $QT\text{–}RR$ slope stratification.
- **[IMPLEMENTED] Headless Multi-File Cohort Batch Runner (`api/batch.py`, `repolaris batch` CLI)**: Fault-isolated multi-file cohort processor exporting 51-column `CSV` and `JSON` biomarker tables without any database dependency.
- **[IMPLEMENTED] Extensible Research Algorithm & Biomarker Plugin Registry (`plugins.py`)**: Thread-safe, fault-isolated `@register_qrs_detector`, `@register_t_end_delineator`, and `@register_biomarker` hooks (**116 passing unit tests**).

### v0.9.0 — Clinical Repolarization Sub-Intervals, T-Wave Morphology & Ambulatory Holter Suite
- **FDA CiPA & Repolarization Core (`pulse_metrics.py`, `qtvi.py`, `t_morphology.py`, `app.py`)**: Beat-to-beat $J\text{–}T_{\text{peak}}c$, $T_{pe}$, $T_{pe}/QT$, Poincaré $STV_{QT}/LTV_{QT}$, 3D SVD T-wave morphology ($T_2/T_1$, $TCRT$), and interactive `🦋 Butterfly & T-PCA` median-beat tab.
- **Ambulatory Holter Suite (`prsa.py`, `st_segment.py`, `p_wave.py`, `edr.py`)**: PRSA Deceleration/Acceleration Capacity ($DC/AC$), rate-adaptive $J+60/80\text{ ms}$ ST-segment ischemia episodes, AF-gated P-wave/AV block screening, ECG-Derived Respiration (EDR/CVHR), and strict `fs >= 1000 Hz` pacemaker spike guard.

### v0.8.1 — Clinical UX Hotkeys, Ectopic Canvas Overlays, Python 3.14 Modernization & Hostile Audit Hardening
- **Workstation UX & Documentation Parity (`app.py`, `i18n.py`, `app.ui`, `ui_app.py`)**:
  - Keyboard beat-by-beat navigation (`Left`/`Right` arrows & `◀`/`▶`), single-key AAMI reclassification hotkeys (`N`, `V`, `S`, `F`, `Q`), color-coded ectopic R-peak markers with on-canvas text tags, persistent manual caliper drag calibration, live `RR` HUD readout, 8-column clinical tables, and 100% 5-language (`en`, `es`, `fr`, `de`, `pt`) translation parity.
- **Python 3.14 Refactoring & Additive `uv` / `ruff` Suite (`pyproject.toml`, `tests/test_tooling_uv_ruff.py`)**:
  - Modernized all modules to native `X | Y` unions, built-in generics, `StrEnum`, `match`/`case`, and `contextlib.suppress`, and added `uv` + `ruff` (`target-version = "py314"`) tests alongside the standard `unittest` suite (116 passing unit tests).
- **Signal Engine & I/O Hardening (`ecg_loader.py`, `pipeline.py`, `sqi.py`, `hysteresis.py`, `qtrr.py`)**:
  - `SignalBuffer` context-manager cleanup, raw-signal `basSQI`/`snr_db` evaluation with Stage 1 `kSQI`/`snr_db` gating, `HamiltonBeatClassifier` pipeline integration, and Tikhonov ridge stabilization for constant-rate QT-RR regression.

### v0.8.0 — Long-Term Holter Streaming, Printable Clinical PDF Reports & Holter Triage Workstation
- **Out-of-Core Streaming & `np.memmap` Buffering (`ecg_loader.py`, `pipeline.py`)**:
  - Added `SignalBuffer`, `open_ecg_buffer()`, `stream_ecg_chunks()`, and `analyze_ecg_stream()` to process continuous 24h–48h Holters in overlapping windows with boundary R-peak deduplication and bounded RAM usage.
- **Automated Printable Clinical PDF Report Generator (`pdf_report.py`, `ExportAPI.export_clinical_pdf`)**:
  - Multi-page clinical PDF reports featuring patient demographics, executive KPI summary, calibrated 10-second waveform strips with fiducial markers, clinical events diary, hourly Holter trend tables, Poincaré plots, and QT-RR restitution curves.
- **Holter Triage Desktop Tab & CLI Streaming (`app.py`, `cli.py`, `i18n.py`)**:
  - Added the `🕒 Holter Triage` tab displaying interactive click-to-seek hourly trend tables and AF episode tables, plus `📄 PDF Report` export and CLI `--pdf` / `--stream` flags (90 automated unit tests passing).

### v0.7.1 — EGM-Hardened Release & Holter Arrhythmia Suite
- **Atrial Fibrillation & Flutter Burden Engine (`af_detector.py`)**:
  - Sliding-window Shannon entropy analysis on local RR distributions coupled with successive RR median absolute difference (MAD) irregularity scoring.
  - Automatic segmentation of sustained AF episodes ($\ge 30\text{ s}$), calculating episode duration, mean/min/max HR, irregularity indices, and overall recording AF burden percentage conforming to clinical Holter standards.
- **Hourly Arrhythmia Trend Histograms (`trends.py`)**:
  - 1-hour binned epoch analysis tracking hourly heart rate extrema (Min, Mean, Max HR), ventricular ectopy counts (PVCs, Couplets, VT Runs), supraventricular ectopy (PACs), sinus pauses ($\ge 2.0\text{ s}$, $\ge 2.5\text{ s}$), and hourly AF burden.
- **EGM Review Hardening & Input Sanitization**:
  - **Hamilton OSEA AF Stabilizer**: Dynamic Shannon entropy gating suppressing isolated prematurity false-positives under chaotic atrial rhythms.
  - **SCP-ECG Compression Guards**: Explicit Section 2 (Huffman tables) and Section 5 (Reference beat subtraction) detection raising clean `NotImplementedError` rather than decoding corrupted streams.
  - **HL7 aECG European Locale Sanitizer**: Automated normalization of comma decimals (`0,005 mV`) to IEEE floating point.
  - **Pulse Metrics & Events Type Safety**: Hardened `summarize_beats()` and `detect_clinical_events()` against `TypeError` on unassigned or NaN cycle metrics.
- **85 Passing Unit Tests** spanning format sniffing, binary parsers, autonomic repolarization, and clinical event detection.

### v0.7.0 — Open International Format Ingestion Layer & Hamilton OSEA Classifier
- **Open Standards Ingestion (`io/`)**: Native zero-dependency parsers for DICOM Waveform (SOP Class 1.2.840.10008.5.1.4.1.1.9.1.1/9.1.2), HL7 Annotated ECG XML (ANSI/HL7 aECG), and SCP-ECG (CEN EN 1064 / ISO 13713).
- **Patrick Hamilton (2002) OSEA Classifier (`hamilton_classifier.py`)**: Dynamic morphology template library with 12.5% exponential adaptation, running median RR prematurity gating (<0.82), and compensatory pause detection.
- **PEP 639 License Standardization**: Full compliance with PEP 639 license configuration resolving Briefcase multi-platform CI package builds.

### v0.6.1 — Peer-Reviewed Anti-Regression Conditioning, Two-Stage SQI Voting & Interactive 10-Model QT-RR Workstation
- **Non-Regressive Conditioning (`config.py`, `baseline.py`)**: Paired AHA/ACC/HRS $0.05\text{ Hz}$ zero-phase Butterworth passband (`notch_quality = 30.0`) with cascaded $200\text{ ms}/600\text{ ms}$ moving median baseline suppression (de Chazal et al., 2004).
- **Two-Stage SQA Gate (`sqi.py`)**: Stage 1 absolute spectral/statistical rejection thresholds (Li et al., 2014) gating Stage 2 six-index pairwise lead voting (VI_k in [-6, +6]; Suárez-León et al., 2018).
- **Four-Mode T-End Delineation (`t_end.py`)**: Added Zhang et al. (2006) sliding-window area (`zhang_area`) alongside `hybrid`, `tangent` (ICH E14), and `threshold`.
- **10 Domain-Guarded QT-RR Models & Interactive GUI (`qtrr.py`, `app.py`)**: All 10 Pueyo et al. (2004) restitution formulations with conditioning guards, `SettingsDialog` selectors, and the `📈 QT-RR Dynamics` PyQtGraph cloud & 10-model leaderboard.

### v0.6.0 — Advanced Autonomic & Spatial Repolarization Suite
- **`repolaris.detection.dispersion`**: Inter-lead spatial QT dispersion ($QT_d = QT_{\max} - QT_{\min}$), Fridericia rate-corrected dispersion ($QTc_d$), precordial transmural dispersion ($T_{\text{peak}}\text{–}T_{\text{end}}$ dispersion: $T_{pe,d}$), and dynamic lead quorum gating ($\ge 8$ valid leads for 12-lead, $\ge 3$ for Holter).
- **`repolaris.detection.twa`**: Microvolt T-Wave Alternans via sub-sample aligned 128-beat Spectral FFT analysis ($0.5\text{ cycles/beat}$, $V_{\text{alt}} \ge 1.9\ \mu\text{V}$, $k \ge 3.0$) and continuous Modified Moving Average (MMA) template tracking.
- **`repolaris.detection.hrt`**: Heart Rate Turbulence ($TO$ and $TS$) following solitary PVCs with strict sinus rhythm purity filtering and ISHNE Category 0/1/2 mortality risk stratification.
- **`repolaris.detection.hrv`**: Task Force ESC/NASPE time-domain metrics ($SDNN$, $RMSSD$, $pNN50$, $SDANN$, $SDNN_{\text{index}}$), Welch periodogram frequency bands ($ULF$, $VLF$, $LF$, $HF$, $LF/HF$, $LF_{\text{nu}}$, $HF_{\text{nu}}$) over 4 Hz Berger-resampled series, and non-linear dynamics (Poincaré $SD_1/SD_2$, Sample Entropy, DFA $\alpha_1/\alpha_2$).
- **`repolaris.detection.hysteresis`**: Multi-beat $QT-RR$ memory lag modeling using state-space Exponential Weighting (EW) and Linear Weighting (LW) kernels, patient-specific $\lambda^*$ optimization, and 90% adaptation latency ($t_{90}$).
- **Core Delineation & Rate-Correction Enhancements**: Hybrid steepest-descent tangent + threshold T-end delineation (`t_end.py`), Hodges linear $QT_c$ formula (`pulse_metrics.py`), active IIR powerline notch filtering in `pipeline.py`, and conditional multi-lead UI gating (`MainWindow._evaluate_channel_capabilities()`).

### v0.5.0 — Multi-Threaded I/O, Asynchronous Workers & UI Precompiler
- Parallelized multi-lead signal decoupling (`ThreadPoolExecutor`) and multi-threaded Zstandard `.pecg` compression.
- Non-blocking `BackgroundTaskWorker(QThread)` and real-time `QStatusBar` progress reporting across GUI and CLI.
- Declarative Qt 6 Designer layout (`src/repolaris/resources/app.ui`) and automated `compile_ui.py` precompiler engine.

### v0.4.0 — In-Process MVC Service Layer, Security Hardening & Clinical Canvas
- Decoupled in-process controller API (`StudyAPI`, `AnalysisAPI`, `ExportAPI`).
- Anti-DoS and decompression bomb mitigations across `.pecg`, ISHNE `.ecg`, EDF/EDF+, WFDB, and Excorde 3C `.e3c`.
- 5 canvas color palettes, clinical paper sweep speeds ($12.5\text{–}100\text{ mm/s}$), voltage gains ($2.5\text{–}20\text{ mm/mV}$), and Portuguese (`pt`) localization.

### v0.3.0 — Python 3.12+ Core & Cross-Platform Packaging
- Upgraded runtime to Python $\ge 3.12$ with strict PEP 484/585/604 static type annotations.
- BeeWare Briefcase installers (`.msi`, `.dmg`, `.deb`, `.AppImage`) and removal of legacy MATLAB/Nuitka dependencies.

### v0.2.0 — Repolaris Rebranding & Universal Format Ingestion
- Zero-dependency pure-Python readers for ISHNE 1.0, PhysioNet WFDB (Format 16/212), EDF/EDF+, Excorde 3C, and `.pecg`.
- 60fps PyQtGraph desktop workstation, ANSI/AAMI EC57 beat classifier, and immutable `AnnotationManager` audit logs.

### v0.1.0 — Foundational PyECG Research Platform (2018)
- Initial clinical research software (Suárez-León et al., Universidad de Oriente & KU Leuven STADIUS).

---

## Upcoming Milestones

### v1.0.0 — Physician-in-the-Loop Clinical Pilot, Regulatory Validation & Production LTS Freeze
- **Physician-in-the-Loop Real-World Pilot**: Clinical workstation review with physician input on real de-identified patient recordings (`.pecg` audit logs, manual caliper overrides, arrhythmia reclassification, and printable PDF report evaluation).
- **Multi-Database Validation Report**: Full ANSI/AAMI EC57 and CSE fiducial certification report across MIT-BIH Arrhythmia, PhysioNet QT Database (QTDB), MIT-BIH Noise Stress Test, and ISHNE Holter cohorts.
- **Production LTS API Freeze**: Frozen long-term support public API (`StudyAPI`, `AnalysisAPI`, `ExportAPI`, `BatchAPI`, `PluginRegistry`) and finalized v1.0.0 release documentation.
