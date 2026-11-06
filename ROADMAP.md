# Repolaris Development Roadmap

This document tracks architectural milestones, clinical electrophysiology modules, and future development targets for the **Repolaris** framework.

---

## Completed Milestones

### v0.7.1 — EGM-Hardened Release & Holter Arrhythmia Suite (Current Release)
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

### v0.3.0 — Python 3.14 Core & Cross-Platform Packaging
- Upgraded runtime to Python $\ge 3.14$ with strict PEP 484/585/604 static type annotations.
- BeeWare Briefcase installers (`.msi`, `.dmg`, `.deb`, `.AppImage`) and removal of legacy MATLAB/Nuitka dependencies.

### v0.2.0 — Repolaris Rebranding & Universal Format Ingestion
- Zero-dependency pure-Python readers for ISHNE 1.0, PhysioNet WFDB (Format 16/212), EDF/EDF+, Excorde 3C, and `.pecg`.
- 60fps PyQtGraph desktop workstation, ANSI/AAMI EC57 beat classifier, and immutable `AnnotationManager` audit logs.

### v0.1.0 — Foundational PyECG Research Platform (2018)
- Initial clinical research software (Suárez-León et al., Universidad de Oriente & KU Leuven STADIUS).

---

## Upcoming Milestones

### v0.8.0 — Long-Term Holter Streaming, Cohort DB & PDF Clinical Reports
- Chunked lazy-loading generator stream and `np.memmap` buffer management for continuous 24h–48h telemetry.
- Optional normalized SQLite cohort indexing for multi-patient longitudinal clinical trials.
- Automated printable clinical PDF report generator with embedded waveform strips, hourly trend tables, and Poincaré/restitution plots.

### v1.0.0 — Regulatory Validation & Benchmark Certification
- Full validation report against PhysioNet QT Database (QTDB), MIT-BIH Arrhythmia Database, and Telemetric Holter E-HOL-03-0202-003 (THEW).
- Frozen long-term support (LTS) public API and plugin registry for custom research algorithms.
