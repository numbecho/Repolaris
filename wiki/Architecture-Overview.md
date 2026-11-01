# Architecture Overview

Repolaris adopts a modular, decoupled architecture where signal conditioning, electrophysiological delineation, autonomic profiling, beat classification, and data storage operate completely independently from the graphical user interface.

---

## 1. Package Decomposition

All modern source code resides in `src/repolaris/`, accompanied by a 100% backward compatibility shim in `src/pyecg/`:

```
src/repolaris/
├── __init__.py               # Package metadata and top-level public API exports
├── config.py                 # FilterConfig, DetectionConfig, and top-level ECGConfig dataclasses
├── cli.py                    # Command-line interface dispatcher
├── app.py                    # Desktop GUI entry point with conditional channel-sensing logic
│
├── io/                       # Universal Multi-Format Ingestion & Serialization
│   ├── ecg_loader.py         # Unified multi-format sniffer and loader router
│   ├── pecg_format.py        # Native .pecg container (CBOR/JSON + Zstd/Deflate)
│   ├── ishne_reader.py       # ISHNE 1.0 (.ecg) binary parser and writer
│   ├── e3c_reader.py         # Excorde 3C (.e3c) in-memory zip & binary parser
│   ├── wfdb_reader.py        # PhysioNet WFDB (.hea/.dat) Format 16/212 parser
│   ├── edf_reader.py         # European Data Format (.edf / .edf+) parser
│   └── db.py                 # SQLite relational + JSON document persistence adapter
│
├── detection/                # Electrophysiological Algorithms & Classification
│   ├── qrs.py                # Derivative-energy R-peak detector (Pan-Tompkins)
│   ├── q_onset.py            # Backward inflection detector for ventricular depolarization
│   ├── t_end.py              # Tangent / threshold T-wave terminus delineation
│   ├── pulse_metrics.py      # RR intervals, heart rate, Bazett, Fridericia, Framingham QTc
│   ├── qtvi.py               # Berger QT Variability Index & 4 Hz step-integration
│   ├── qtrr.py               # 6 non-linear QT-RR dynamic restitution models
│   ├── sqi.py                # Spectral Signal Quality Indices (pSQI, basSQI, SNR)
│   ├── dispersion.py         # Multi-lead QT Dispersion (QTd) & transmural Tpe dispersion
│   ├── twa.py                # Microvolt T-Wave Alternans (Spectral FFT & continuous MMA)
│   ├── hrt.py                # Heart Rate Turbulence (Turbulence Onset & Turbulence Slope)
│   ├── hrv.py                # Comprehensive HRV suite (time, Welch PSD frequency, non-linear)
│   ├── hysteresis.py         # Multi-beat QT-RR memory modeling (EW and LW lag kernels)
│   ├── classifier.py         # ANSI/AAMI EC57 beat classifier (N, V, S, F, Q) & sequences
│   ├── annotations.py        # AnnotationManager with immutable audit logging
│   ├── events.py             # Automated clinical triage alert detector
│   └── pipeline.py           # End-to-end master headless processing pipeline
│
├── gui/                      # PyQtGraph Hardware-Accelerated Workstation
│   ├── widgets.py            # ECGPlotWidget with draggable calipers and OpenGL rendering
│   └── main_window.py        # MainWindow with Events Diary, HUD, and diagnostic docks
│
└── utils/                    # Shared Utilities
    └── signal.py             # Realistic multi-component synthetic ECG generator
```

---

## 2. Decoupled Pipeline Dataflow

The processing pipeline operates in distinct stages:

```
[Raw Physical Voltage (mV)]
         |
         v
+-----------------------+
| Preprocessing Stage   |  --> Notch Filter (50/60 Hz IIR)
|                       |  --> Butterworth Bandpass (0.5 - 45 Hz)
|                       |  --> Cascaded Median Baseline Wander Removal (200ms / 600ms)
+-----------------------+
         |
         v
+-----------------------+
| Signal Quality (SQI)  |  --> Computes pSQI (5-15 Hz power ratio)
|                       |  --> Computes basSQI (0-1 Hz wander ratio)
|                       |  --> Rejects corrupted leads (SNR < 12 dB)
+-----------------------+
         |
         v
+-----------------------+
| Waveform Delineation  |  --> Detect R-Peaks (derivative + moving-average energy)
|                       |  --> Backward search for Q-Onset inflection
|                       |  --> Downslope tangent & threshold for T-End
+-----------------------+
         |
         v
+-----------------------+
| Metric Calculation    |  --> RR intervals & Heart Rate (BPM)
| & Dynamic Modeling    |  --> QTc Correction (Bazett, Fridericia, Framingham, Hodges)
|                       |  --> Berger QTVI & 4 Hz step-integration resampling
|                       |  --> Non-linear QT-RR restitution model optimization
|                       |  --> Multi-beat QT-RR memory hysteresis (EW/LW profiles)
+-----------------------+
         |
         v
+-----------------------+
| Beat Classification   |  --> ANSI/AAMI EC57 Beat Labeling (N, V, S, F, Q)
| & Rhythm Sequences    |  --> Sequence detection (Bigeminy, Trigeminy, Couplets, VT)
+-----------------------+
         |
         v
+-----------------------+
| Autonomic & Spatial   |  --> Microvolt T-Wave Alternans (Spectral FFT & MMA)
| Advanced Analysis     |  --> Heart Rate Turbulence (TO & TS post-solitary PVCs)
|                       |  --> Comprehensive HRV (Time, Frequency, Non-Linear Poincaré)
|                       |  --> Spatial QT Dispersion (Gated: requires >= 3 valid leads)
+-----------------------+
         |
         v
+-----------------------+
| Clinical Triage Alert |  --> Severe QTc (>500 ms), Pauses (>2.0 s), Brady/Tachy
|                       |  --> Indexes events into Clinical Events Diary
+-----------------------+
```

---

## 3. Dynamic Channel-Sensing & Multi-Lead Gating

Repolaris features an automated channel-sensing engine that detects the physical channel count of the active recording and modulates analytical passes and GUI presentation:

1. **Lead Quorum Verification**: The ingestion router (`ecg_loader.py`) determines total channel count $N_\text{leads}$ and evaluates per-lead signal quality.
2. **Conditional Path Routing**:
   * **Single-Lead Wearable Mode ($N_\text{leads} < 3$)**: Dispatches single-lead delineations, rate corrections, QTVI, restitution, HRV, HRT, TWA, and hysteresis. Bypasses the spatial dispersion module to prevent degenerate zero-dispersion artifacts.
   * **Multi-Lead Holter Mode ($N_\text{leads} \ge 3$)**: Executes parallel multi-channel delineation, aligns global $Q_\text{onset}$, calculates spatial $QT_d$ and $T_{pe,d}$, and unlocks multi-lead butterfly and radar views in the workstation interface.
