# Architecture Overview

Repolaris adopts a modular, decoupled architecture where signal conditioning, electrophysiological delineation, autonomic profiling, beat classification, and data storage operate completely independently from the graphical user interface.

---

## 1. Package Decomposition

All source code resides in `src/repolaris/`:

```
src/repolaris/
├── __init__.py               # Package metadata (__version__ = "0.8.1") and public API exports
├── __main__.py               # Module execution entry point (python -m repolaris)
├── config.py                 # FilterConfig, DetectionConfig, and top-level ECGConfig dataclasses
├── i18n.py                   # Multi-language localization dictionary (en, es, fr, de, pt)
├── cli.py                    # Command-line interface dispatcher (demo, analyze, export, --stream, --pdf)
├── app.py                    # Desktop GUI workstation with conditional channel-sensing logic
│
├── api/                      # In-Process MVC Service Controllers
│   ├── __init__.py           # Controller exports (StudyAPI, AnalysisAPI, ExportAPI)
│   ├── study.py              # StudyAPI: dataset loading, SignalBuffer, and chunk streaming
│   ├── analysis.py           # AnalysisAPI: in-memory & streaming pipeline, QTc, AF, trends, autonomic suite
│   └── export.py             # ExportAPI: de-identified .pecg export and 2-page clinical PDF generation
│
├── preprocessing/            # Signal Conditioning
│   ├── filter.py             # Butterworth bandpass (0.05-45 Hz) and IIR Q=30 notch filters
│   └── baseline.py           # Two-stage moving median baseline wander suppression (200ms / 600ms)
│
├── io/                       # Universal Multi-Format Ingestion, Streaming & Reporting
│   ├── ecg_loader.py         # Format sniffer, unified loader, SignalBuffer, and stream_ecg_chunks
│   ├── pdf_report.py         # Printable 2-page vector clinical PDF report generator
│   ├── pecg_format.py        # Native .pecg container (CBOR/JSON + Zstd/Deflate + np.memmap)
│   ├── ishne_reader.py       # ISHNE 1.0 (.ecg) binary parser and writer
│   ├── e3c_reader.py         # Excorde 3C (.e3c) in-memory zip & binary parser
│   ├── wfdb_reader.py        # PhysioNet WFDB (.hea/.dat) Format 16/212 parser
│   ├── edf_reader.py         # European Data Format (.edf / .edf+) parser
│   ├── dicom_reader.py       # DICOM Waveform (SOP 1.2.840.10008.5.1.4.1.1.9.1.1/9.1.2)
│   ├── hl7_reader.py         # HL7 Annotated ECG XML (ANSI/HL7 aECG)
│   └── scp_reader.py         # SCP-ECG (CEN EN 1064 / ISO 13713)
│
├── detection/                # Electrophysiological Algorithms & Classification
│   ├── qrs.py                # Derivative-energy R-peak detector (Pan-Tompkins inspired)
│   ├── q_onset.py            # Backward inflection detector for ventricular depolarization
│   ├── t_end.py              # 4-mode T-end delineation (hybrid, tangent, zhang_area, threshold)
│   ├── pulse_metrics.py      # RR intervals, heart rate, Bazett, Fridericia, Framingham, Hodges QTc
│   ├── qtvi.py               # Berger QT Variability Index & 4 Hz step-integration
│   ├── qtrr.py               # 10 domain-guarded QT-RR dynamic restitution models (Pueyo 2004)
│   ├── sqi.py                # Two-Stage SQI (Li 2014 absolute gates + 6-index pairwise voting)
│   ├── dispersion.py         # Multi-lead QT Dispersion (QTd) & transmural Tpe dispersion
│   ├── twa.py                # Microvolt T-Wave Alternans (Spectral FFT & continuous MMA)
│   ├── hrt.py                # Heart Rate Turbulence (Turbulence Onset & Turbulence Slope)
│   ├── hrv.py                # Comprehensive HRV suite (time, Welch PSD frequency, non-linear)
│   ├── hysteresis.py         # Multi-beat QT-RR memory modeling (EW and LW lag kernels)
│   ├── classifier.py         # ANSI/AAMI EC57 beat classifier (N, V, S, F, Q) & sequences
│   ├── hamilton_classifier.py # Patrick Hamilton (2002) OSEA template matching with AF stabilizer
│   ├── af_detector.py        # Atrial Fibrillation/Flutter burden & Shannon entropy
│   ├── trends.py             # Hourly arrhythmia trend histograms & Holter summary
│   ├── annotations.py        # AnnotationManager with immutable audit logging
│   ├── events.py             # Automated clinical triage alert detector
│   └── pipeline.py           # In-memory (analyze_ecg) & chunked streaming (analyze_ecg_stream) pipelines
│
├── resources/                # Declarative Qt 6 Presentation Assets
│   ├── app.ui                # Qt 6 Designer XML workstation layout
│   ├── compile_ui.py         # Automated UI precompiler engine
│   └── ui_app.py             # Precompiled Ui_MainWindow layout class
│
└── utils/                    # Shared Utilities
    └── signal.py             # Realistic localized-Gaussian synthetic ECG generator
```

---

## 2. Decoupled Pipeline Dataflow

The processing pipeline operates in distinct, composable stages across both in-memory (`analyze_ecg`) and out-of-core chunked streaming (`analyze_ecg_stream`) modes:

```
[Raw Physical Voltage (mV) or Out-of-Core SignalBuffer (np.memmap)]
         |
         v
+-----------------------+
| Preprocessing Stage   |  --> Narrow IIR Notch Filter (50/60 Hz, Q=30)
|                       |  --> Zero-Phase Butterworth Bandpass (0.05 - 45 Hz, AHA/ACC/HRS)
|                       |  --> Cascaded Median Baseline Wander Removal (200ms / 600ms)
+-----------------------+
         |
         v
+-----------------------+
| Two-Stage SQI Gate    |  --> Stage 1 Absolute Gates (pSQI, basSQI on raw signal, kSQI, sSQI,
|                       |      raw SNR_dB, non-flatline ratio; EXCELLENT / ACCEPTABLE / POOR)
|                       |  --> Stage 2 Six-Index Pairwise Lead Voting (VI_k in [-6, +6])
+-----------------------+
         |
         v
+-----------------------+
| Waveform Delineation  |  --> Detect R-Peaks (derivative + moving-average energy)
|                       |  --> Backward search for Q-Onset inflection
|                       |  --> 4-Mode T-End (hybrid, ICH E14 tangent, Zhang 2006 SWA, threshold)
+-----------------------+
         |
         v
+-----------------------+
| Metric Calculation    |  --> RR intervals & Heart Rate (BPM)
| & Dynamic Modeling    |  --> QTc Correction (Bazett, Fridericia, Framingham, Hodges, QTc,ind)
|                       |  --> Berger QTVI & 4 Hz step-integration resampling
|                       |  --> 10 Pueyo (2004) QT-RR restitution models with domain guards
|                       |  --> Multi-beat QT-RR memory hysteresis (EW/LW profiles, lambda*, t90)
+-----------------------+
         |
         v
+-----------------------+
| Beat Classification   |  --> ANSI/AAMI EC57 Beat Labeling (N, V, S, F, Q) & Hamilton OSEA
| & Holter Triage       |  --> Sequence detection (Bigeminy, Trigeminy, Couplets, VT runs)
|                       |  --> AF/Flutter Shannon entropy & MAD irregularity burden engine
|                       |  --> 1-Hour Holter trend histograms (HR extrema, PVCs, PACs, Pauses, AF)
+-----------------------+
         |
         v
+-----------------------+
| Autonomic & Spatial   |  --> Microvolt T-Wave Alternans (Spectral FFT & MMA)
| Advanced Analysis     |  --> Heart Rate Turbulence (TO & TS post-solitary PVCs)
|                       |  --> Comprehensive HRV (Time, Frequency, Non-Linear Poincaré/DFA)
|                       |  --> Spatial QT Dispersion (Gated: requires >= 3 valid leads)
+-----------------------+
         |
         v
+-----------------------+
| Clinical Triage &     |  --> Severe QTc (>=500 ms), Borderline (>=480 ms), Short (<=340 ms),
| Printable Reporting   |      Sinus Pauses (>=2.0 s), Brady/Tachy, PVCs
|                       |  --> Interactive GUI Tabs & 2-Page Vector Clinical PDF Report
+-----------------------+
```

---

## 3. Dynamic Channel-Sensing & Multi-Lead Gating

Repolaris features an automated channel-sensing engine (`MainWindow._evaluate_channel_capabilities()` and `calculate_qt_dispersion()`) that inspects the physical channel count of the active recording and modulates analytical passes and GUI presentation:

1. **Lead Quorum Verification**: The ingestion router (`ecg_loader.py`) determines total channel count $N_\text{leads}$ and evaluates per-lead signal quality via `rank_leads_two_stage()`.
2. **Conditional Path Routing**:
   * **Single-Lead Wearable Mode ($N_\text{leads} < 3$)**: Dispatches single-lead delineations, rate corrections, QTVI, 10-model restitution, HRV, HRT, TWA, hysteresis, AF burden, and hourly trends. Bypasses spatial QT dispersion ($QT_d$) to prevent degenerate zero-dispersion values and marks the $QT_d$ card as `N/A — Single Lead`.
   * **Multi-Lead Holter / 12-Lead Mode ($N_\text{leads} \ge 3$)**: Executes parallel multi-channel delineation, evaluates inter-lead $QT_d$, Fridericia-corrected $QTc_d$, and precordial transmural dispersion ($T_{pe,d}$), and displays the active multi-lead quorum status in the Clinical Overview.
