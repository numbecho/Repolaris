# Repolaris Development Roadmap

This document tracks architectural milestones, clinical electrophysiology modules, and future development targets for the **Repolaris** framework.

---

## Completed Milestones

### v0.6.0 — Advanced Autonomic & Spatial Repolarization Suite (Current Release)
- **`repolaris.detection.dispersion`**: Inter-lead spatial QT dispersion ($QT_d = QT_{\max} - QT_{\min}$), Fridericia rate-corrected dispersion ($QTc_d$), precordial transmural dispersion ($T_{\text{peak}}\text{–}T_{\text{end}}$ dispersion: $T_{pe,d}$), and dynamic lead quorum gating ($\ge 8$ valid leads for 12-lead, $\ge 3$ for Holter).
- **`repolaris.detection.twa`**: Microvolt T-Wave Alternans via sub-sample aligned 128-beat Spectral FFT analysis ($0.5\text{ cycles/beat}$, $V_{\text{alt}} \ge 1.9\ \mu\text{V}$, $k \ge 3.0$) and continuous Modified Moving Average (MMA) template tracking.
- **`repolaris.detection.hrt`**: Heart Rate Turbulence ($TO$ and $TS$) following solitary PVCs with strict sinus rhythm purity filtering and ISHNE Category 0/1/2 mortality risk stratification.
- **`repolaris.detection.hrv`**: Task Force ESC/NASPE time-domain metrics ($SDNN$, $RMSSD$, $pNN50$, $SDANN$, $SDNN_{\text{index}}$), Welch periodogram frequency bands ($ULF$, $VLF$, $LF$, $HF$, $LF/HF$, $LF_{\text{nu}}$, $HF_{\text{nu}}$) over 4 Hz Berger-resampled series, and non-linear dynamics (Poincaré $SD_1/SD_2$, Sample Entropy, DFA $\alpha_1/\alpha_2$).
- **`repolaris.detection.hysteresis`**: Multi-beat $\mathrm{QT}\text{–}\mathrm{RR}$ memory lag modeling using state-space Exponential Weighting (EW) and Linear Weighting (LW) kernels, patient-specific $\lambda^*$ optimization, and 90% adaptation latency ($t_{90}$).
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

### v0.7.0 — Cohort Persistence, HL7 aECG & PDF Clinical Reporting
- Optional normalized SQLite cohort indexing for multi-patient longitudinal trials.
- FDA HL7 Annotated ECG (aECG XML) and DICOM Waveform SOP export adapters.
- Automated printable clinical PDF report generator with embedded waveform strips and Poincaré/restitution plots.

### v1.0.0 — Regulatory Validation & Benchmark Certification
- Full validation report against PhysioNet QT Database (QTDB), MIT-BIH Arrhythmia Database, and Telemetric Holter E-HOL-03-0202-003 (THEW).
- Frozen long-term support (LTS) public API and plugin registry for custom research algorithms.
