# Welcome to the Repolaris Wiki

**Repolaris** is an open-source clinical and research software framework for continuous electrocardiogram (ECG) waveform segmentation, automated arrhythmia triage, and high-precision ventricular repolarization (QT interval) analysis.

Originally introduced as **PyECG** (*Suárez-León et al., 2018; Universidad de Oriente / KU Leuven STADIUS*), the modernized **Repolaris** platform eliminates dependency on closed, proprietary Holter processing ecosystems. It provides cardiology departments, clinical research organizations (CROs), and biomedical engineers with an extensible, vendor-neutral suite capable of ingesting diverse clinical Holter and hospital formats (DICOM Waveform, HL7 aECG XML, SCP-ECG, ISHNE, EDF, WFDB), calculating rate-corrected QT ($QT_c$), evaluating Berger's QT Variability Index (QTVI), fitting 10 non-linear QT-RR restitution models, quantifying spatial QT dispersion, detecting microvolt T-wave alternans, profiling heart rate turbulence and autonomic HRV, screening Atrial Fibrillation / Flutter burden, generating hourly Holter histograms, classifying beats under ANSI/AAMI EC57 and Patrick Hamilton (2002) OSEA standards, and providing 60fps digital calipers for physician review.

```
+----------------------------------------------------------------------------------------------------+
|                                    REPOLARIS SYSTEM PIPELINE                                       |
+----------------------------------------------------------------------------------------------------+
|  [Ingestion Engine]    -->  [Signal Conditioning]  -->  [Delineation & Metrics]  -->  [GUI & Calipers] |
|  - DICOM Waveform           - Notch (50/60 Hz Q=30)     - R-Peaks (Energy square)     - PyQtGraph 60fps    |
|  - HL7 aECG XML             - Bandpass (0.05-45 Hz)     - Q-Onset Inflection          - Live Calipers      |
|  - SCP-ECG (EN 1064)        - Two-Stage Baseline        - T-End (Hybrid, Zhang SWA)   - Events Diary       |
|  - ISHNE 1.0 (.ecg)         - Stage 1 Absolute SQI      - QTc (4 formulations)        - AAMI / Hamilton    |
|  - Excorde 3C (.e3c)        - Stage 2 Pairwise Voting   - 10 Pueyo Restitution Models - AF & Trend Docks   |
|  - EDF / EDF+ (.edf)                                    - Berger QTVI, QTd, TWA       - Multi-Lead Gating  |
|  - WFDB (.hea/.dat)                                     - HRT, HRV, Hysteresis        - .pecg Study Export |
|  - Portable (.pecg)                                     - AF Burden & Hourly Trends                        |
+----------------------------------------------------------------------------------------------------+
```

---

## Quick Navigation

| Section | Description |
| :--- | :--- |
| **[Getting Started](Getting-Started)** | Installation via `pip` or `uv`, CLI commands, running synthetic demos, and starting the desktop GUI. |
| **[Architecture Overview](Architecture-Overview)** | Decoupled subpackage structure (`repolaris.io`, `detection`, `gui`, `pipeline`, `utils`) and backward compatibility. |
| **[File Formats & I/O](File-Formats-and-IO)** | Specifications for DICOM Waveform, HL7 aECG XML, SCP-ECG, `.pecg` container, ISHNE 1.0, Excorde 3C, and WFDB. |
| **[Electrophysiology & Algorithms](Electrophysiology-and-Algorithms)** | Mathematical formulations for $QT_c$, AF burden engine, Berger QTVI, QT dispersion, TWA, HRT, HRV, hysteresis, 10 restitution models, and 2-stage SQI. |
| **[Arrhythmia & AAMI EC57](Arrhythmia-and-AAMI-EC57)** | ANSI/AAMI EC57 beat classification (`N`, `V`, `S`, `F`, `Q`), Patrick Hamilton (2002) OSEA template matching, hourly Holter trends, and audit logging. |
| **[Workstation GUI Guide](Workstation-GUI-Guide)** | Interactive PyQtGraph desktop viewer, draggable calipers, conditional multi-lead gating, and clinical triage docks. |
| **[Developer Guide](Developer-Guide)** | Setting up virtual environments with Astral `uv`, linting with `ruff`, running the 90-test suite, and contributing. |
| **[i18n & Translation Guide](Internationalization-and-Translation-Guide)** | Contributor guide for adding UI languages (English, Spanish, French, German, Portuguese) and translating wiki docs. |
| **[Packaging & CI/CD Guide](Packaging-and-CI-CD-Guide)** | Building distribution installers (`.msi`, `.dmg`, `.AppImage`) with Briefcase under PEP 639 metadata. |
| **[FAQ & Troubleshooting](FAQ-and-Troubleshooting)** | Frequently asked questions, hardware requirements, and formal academic citations. |

---

## Primary Highlights of Repolaris 0.8.0

* **Universal Open Format Ingestion:** Zero external proprietary software required to ingest DICOM Waveform (SOP `1.2.840.10008.5.1.4.1.1.9.1.1/9.1.2`), HL7 Annotated ECG XML (FDA TQT standard), SCP-ECG (CEN EN 1064 / ISO 13713), ISHNE 1.0 `.ecg`, Excorde 3C `.e3c`, European Data Format `.edf`, PhysioNet WFDB `.hea`/`.dat`, or delimited `.csv`.
* **Atrial Fibrillation / Flutter Burden Engine:** Automatic sliding-window Shannon entropy and successive RR median absolute difference irregularity scoring with sustained episode segmentation ($\ge 30\text{ s}$) and 24h burden quantification.
* **Hourly Holter Trend Histograms:** 1-hour epoch distribution tables tracking minimum, mean, and maximum heart rates, ventricular ectopy (PVCs, Couplets, VT Runs), supraventricular ectopy (PACs), sinus pauses ($\ge 2.0\text{ s}$, $\ge 2.5\text{ s}$), and hourly AF burden.
* **Patrick Hamilton (2002) OSEA Beat Classifier:** Dynamic morphology template clustering with a 12.5% exponential adaptation rate, running median RR prematurity gating, compensatory pause checks, and AF entropy stabilization.
* **Peer-Reviewed Anti-Regression Conditioning:** AHA/ACC/HRS $0.05\text{ Hz}$ zero-phase Butterworth filter paired with cascaded $200\text{ ms} / 600\text{ ms}$ moving median baseline suppression and a narrow $Q=30$ powerline notch filter.
* **Two-Stage Signal Quality Assessment:** Stage 1 absolute spectral/statistical rejection thresholds (Li et al., 2014) gating Stage 2 six-index pairwise lead voting ($VI_k \in [-6, +6]$).
* **Complete 10-Model QT-RR Restitution:** All 10 Pueyo (2004) biparametric curves with Vandermonde domain guards and interactive PyQtGraph cloud visualization.
* **Multi-Beat QT-RR Hysteresis:** State-space exponential (EW) and linear (LW) lag-weighted memory modeling to collapse restitution loops and prevent false-positive drug-induced QT warnings.
* **Spatial Repolarization Heterogeneity:** Synchronous multi-lead QT Dispersion ($QT_d$) and transmural repolarization dispersion ($T_{pe,d}$) across qualified diagnostic leads ($\ge 3$ channels).
* **Autonomic Cardiovascular Evaluation:** Biphasic Heart Rate Turbulence ($TO$, $TS$, Categories 0/1/2) following solitary PVCs alongside a complete Heart Rate Variability suite (time, frequency Welch PSD, and non-linear Poincaré/entropy).
* **Portable Clinical Exchange (`.pecg`):** A custom de-identified single-file container supporting Zstandard (`zstd`) compression, CBOR/JSON metadata, and zero-copy memory mapping (`np.memmap`).
* **Modern Developer Stack:** Python $\ge 3.12$, 100% strict static typing, PEP 639 licensing metadata, Briefcase packaging, Astral `ruff`/`uv` workflows, and 90 passing automated unit tests.
