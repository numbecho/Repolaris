# Welcome to the Repolaris Wiki

**Repolaris** is an open-source clinical and research software framework for continuous electrocardiogram (ECG) waveform segmentation, automated arrhythmia triage, and high-precision ventricular repolarization (QT interval) analysis.

Originally introduced as **PyECG** (*Suárez-León et al., 2018; Universidad de Oriente / KU Leuven STADIUS*), the modernized **Repolaris** platform eliminates dependency on closed, proprietary Holter processing ecosystems. It provides cardiology departments, clinical research organizations (CROs), and biomedical engineers with an extensible, vendor-neutral suite capable of ingesting diverse clinical Holter and wearable formats, calculating rate-corrected QT ($QT_c$), evaluating Berger's QT Variability Index (QTVI), fitting non-linear QT-RR restitution dynamics, quantifying spatial QT dispersion, detecting microvolt T-wave alternans, profiling heart rate turbulence and autonomic HRV, classifying beats under ANSI/AAMI EC57 standards, and providing 60fps digital calipers for physician review.

```
+----------------------------------------------------------------------------------------------------+
|                                    REPOLARIS SYSTEM PIPELINE                                       |
+----------------------------------------------------------------------------------------------------+
|  [Ingestion Engine]    -->  [Signal Conditioning]  -->  [Delineation & Metrics]  -->  [GUI & Calipers] |
|  - ISHNE 1.0 (.ecg)         - Notch (50/60 Hz)          - R-Peaks (Pan-Tompkins)      - PyQtGraph 60fps    |
|  - Excorde 3C (.e3c)        - Bandpass (0.5-45 Hz)      - Q-Onset Inflection          - Live Calipers      |
|  - EDF / EDF+ (.edf)        - Median Drift Removal      - T-End Tangent/Threshold     - Events Diary       |
|  - PhysioNet (.hea/.dat)    - Spectral SQI Check        - QTc (Bazett, Fridericia)    - AAMI Beat Override |
|  - Portable (.pecg)                                     - Berger QTVI & Restitution   - Multi-Lead Gating  |
|                                                         - QTd, TWA, HRT, HRV, Hyst    - .pecg Study Export |
+----------------------------------------------------------------------------------------------------+
```

---

## Quick Navigation

| Section | Description |
| :--- | :--- |
| **[Getting Started](Getting-Started)** | Installation via `pip` or `uv`, CLI commands, running synthetic demos, and starting the desktop GUI. |
| **[Architecture Overview](Architecture-Overview)** | Decoupled subpackage structure (`repolaris.io`, `detection`, `gui`, `pipeline`, `utils`) and backward compatibility. |
| **[File Formats & I/O](File-Formats-and-IO)** | Specification of the `.pecg` container format, ISHNE 1.0 demultiplexer, Excorde 3C reader, and WFDB Format 16/212. |
| **[Electrophysiology & Algorithms](Electrophysiology-and-Algorithms)** | Mathematical formulations for $QT_c$, Berger QTVI, QT dispersion, TWA, HRT, comprehensive HRV, QT-RR hysteresis, restitution, and SQI. |
| **[Arrhythmia & AAMI EC57](Arrhythmia-and-AAMI-EC57)** | ANSI/AAMI EC57 beat classification (`N`, `V`, `S`, `F`, `Q`), coupled rhythm detection (Bigeminy, Couplets, VT), and audit logging. |
| **[Workstation GUI Guide](Workstation-GUI-Guide)** | Interactive PyQtGraph desktop viewer, draggable calipers, conditional multi-lead gating, and clinical triage docks. |
| **[Developer Guide](Developer-Guide)** | Setting up virtual environments with Astral `uv`, linting with `ruff`, running the test suite, and contributing. |
| **[i18n & Translation Guide](Internationalization-and-Translation-Guide)** | Contributor guide for adding UI languages (English, Spanish, French, German, Portuguese) and translating wiki docs. |
| **[Packaging & CI/CD Guide](Packaging-and-CI-CD-Guide)** | Building distribution installers (`.msi`, `.dmg`, `.AppImage`) with Briefcase. |
| **[FAQ & Troubleshooting](FAQ-and-Troubleshooting)** | Frequently asked questions, hardware requirements, and formal academic citations. |

---

## Primary Highlights of Repolaris 0.6.0

* **Universal Format Ingestion:** Zero external proprietary software required to ingest ISHNE 1.0 `.ecg`, Excorde 3C `.e3c`, European Data Format `.edf`, PhysioNet WFDB `.hea`/`.dat`, or delimited `.csv`.
* **Spatial Repolarization Heterogeneity:** Synchronous multi-lead QT Dispersion ($QT_d$) and transmural repolarization dispersion ($T_{pe,d}$) across qualified diagnostic leads ($\ge 3$ channels).
* **Microvolt T-Wave Alternans (TWA):** Dual spectral FFT ($f = 0.5\text{ cpb}$) and continuous Modified Moving Average (MMA) tracking for ambulatory ventricular fibrillation risk stratification.
* **Autonomic Cardiovascular Evaluation:** Biphasic Heart Rate Turbulence ($TO$, $TS$, Categories 0/1/2) following solitary PVCs alongside a complete Heart Rate Variability suite (time, frequency Welch PSD, and non-linear Poincaré/entropy).
* **Multi-Beat QT-RR Hysteresis:** State-space exponential (EW) and linear (LW) lag-weighted memory modeling to collapse restitution loops and prevent false-positive drug-induced QT warnings.
* **Conditional Multi-Lead UI/UX Gating:** Dynamic interface state machine that automatically badges and disables spatial dispersion views during single-lead patch analysis while unlocking multi-lead butterfly and radar views for 12-lead Holters.
* **Portable Clinical Exchange (`.pecg`):** A custom de-identified single-file container supporting Zstandard (`zstd`) compression, CBOR/JSON metadata, and zero-copy memory mapping (`np.memmap`) for instant multi-hour seeking with zero RAM overhead.
* **Clinical Governance:** Full ANSI/AAMI EC57 beat classification, rhythm pattern grouping, and an `AnnotationManager` that preserves immutable physician review audit logs with ISO 8601 timestamps.
* **Hardware-Accelerated GUI:** 60fps continuous waveform scrolling via PyQtGraph, interactive calipers with real-time recalculation, and a click-to-seek Clinical Events Diary.
* **Modern Developer Stack:** Python $\ge 3.14$, 100% strict PEP 484/585/604 static typing, PEP 517/621 `pyproject.toml`, Astral `ruff`/`uv` ergonomics, and an automated multi-platform CI/CD packaging matrix.
