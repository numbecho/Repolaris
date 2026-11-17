# Welcome to the Repolaris Wiki

**Repolaris** is an open-source clinical and research software framework for continuous electrocardiogram (ECG) waveform segmentation, automated arrhythmia triage, and high-precision ventricular repolarization (QT interval) analysis.

Originally introduced as **PyECG** (*Suárez-León et al., 2018; Universidad de Oriente / KU Leuven STADIUS*), the modernized **Repolaris** platform eliminates dependency on closed, proprietary Holter processing ecosystems. It provides cardiology departments, clinical research organizations (CROs), and biomedical engineers with an extensible, vendor-neutral suite capable of ingesting diverse clinical Holter and hospital formats (DICOM Waveform, HL7 aECG XML, SCP-ECG, ISHNE, Excorde 3C, EDF, WFDB, `.pecg`), streaming continuous 24h–48h Holters out-of-core (`SignalBuffer` / `analyze_ecg_stream`), calculating rate-corrected QT ($QT_c$), evaluating Berger's QT Variability Index (QTVI), fitting 10 non-linear QT-RR restitution models, quantifying spatial QT dispersion, detecting microvolt T-wave alternans, profiling heart rate turbulence and autonomic HRV, screening Atrial Fibrillation / Flutter burden, generating hourly Holter histograms, classifying beats under ANSI/AAMI EC57 and Patrick Hamilton (2002) OSEA standards, exporting printable 2-page clinical PDF reports, and providing 60fps digital calipers for physician review.

```
+----------------------------------------------------------------------------------------------------+
|                                    REPOLARIS SYSTEM PIPELINE                                       |
+----------------------------------------------------------------------------------------------------+
|  [Ingestion & Streaming] --> [Signal Conditioning]  --> [Delineation & Metrics]  --> [GUI & Reports]  |
|  - DICOM Waveform            - Notch (50/60 Hz Q=30)    - R-Peaks (Energy square)    - PyQtGraph 60fps |
|  - HL7 aECG XML              - Bandpass (0.05-45 Hz)    - Q-Onset Inflection         - Live Calipers   |
|  - SCP-ECG (EN 1064)         - Two-Stage Baseline       - T-End (Hybrid, Zhang SWA)  - Events Diary    |
|  - ISHNE 1.0 (.ecg)          - Stage 1 Absolute SQI     - QTc (5 formulations)       - Holter Triage   |
|  - Excorde 3C (.e3c)         - Stage 2 Pairwise Voting  - 10 Pueyo Restitution       - QT-RR Dynamics  |
|  - EDF / EDF+ (.edf)                                    - Berger QTVI, QTd, TWA      - 2-Page PDF Rpt  |
|  - WFDB (.hea/.dat)                                     - HRT, HRV, Hysteresis       - .pecg Exchange  |
|  - Out-of-Core np.memmap                                - AF Burden & Hourly Trends                    |
+----------------------------------------------------------------------------------------------------+
```

---

## Quick Navigation

| Section | Description |
| :--- | :--- |
| **[Getting Started](Getting-Started)** | Installation via `pip` or `uv`, CLI commands (`demo`, `analyze --stream --pdf`, `export`), and starting the desktop GUI. |
| **[Architecture Overview](Architecture-Overview)** | Decoupled subpackage structure (`repolaris.io`, `detection`, `preprocessing`, `api`, `resources`, `utils`) and streaming pipeline. |
| **[File Formats & I/O](File-Formats-and-IO)** | Specifications for DICOM Waveform, HL7 aECG XML, SCP-ECG, `.pecg` container, ISHNE 1.0, Excorde 3C, EDF, WFDB, and `SignalBuffer`. |
| **[Electrophysiology & Algorithms](Electrophysiology-and-Algorithms)** | Mathematical formulations for $QT_c$, AF burden engine, Berger QTVI, QT dispersion, TWA, HRT, HRV, hysteresis, 10 restitution models, and 2-stage SQI. |
| **[Arrhythmia & AAMI EC57](Arrhythmia-and-AAMI-EC57)** | ANSI/AAMI EC57 beat classification (`N`, `V`, `S`, `F`, `Q`), Patrick Hamilton (2002) OSEA template matching, hourly Holter trends, and audit logging. |
| **[Workstation GUI Guide](Workstation-GUI-Guide)** | Interactive PyQtGraph desktop viewer, draggable calipers, 6 clinical inspector tabs (`🕒 Holter Triage`, `📈 QT-RR Dynamics`), and PDF report export. |
| **[Developer Guide](Developer-Guide)** | Setting up virtual environments with Astral `uv`, linting with `ruff`, running the 90-test suite, and contributing. |
| **[i18n & Translation Guide](Internationalization-and-Translation-Guide)** | Contributor guide for adding UI languages (English, Spanish, French, German, Portuguese) and translating wiki docs. |
| **[Packaging & CI/CD Guide](Packaging-and-CI-CD-Guide)** | Building distribution installers (`.msi`, `.dmg`, `.AppImage`) with Briefcase under PEP 639 metadata. |
| **[FAQ & Troubleshooting](FAQ-and-Troubleshooting)** | Frequently asked questions, hardware requirements, and formal academic citations. |

---

## Primary Highlights of Repolaris 0.8.1

* **Universal Open Format Ingestion:** Zero external proprietary software required to ingest DICOM Waveform (SOP `1.2.840.10008.5.1.4.1.1.9.1.1/9.1.2`), HL7 Annotated ECG XML (FDA TQT standard), SCP-ECG (CEN EN 1064 / ISO 13713), ISHNE 1.0 `.ecg`, Excorde 3C `.e3c`, European Data Format `.edf`, PhysioNet WFDB `.hea`/`.dat`, or delimited `.csv`/`.npy`.
* **Out-of-Core Long-Term Holter Streaming:** `SignalBuffer`, `stream_ecg_chunks()`, and `analyze_ecg_stream()` process continuous 24h–48h recordings via `np.memmap`-backed disk buffers and overlapping windows with boundary R-peak deduplication.
* **Printable 2-Page Clinical PDF Reports:** `generate_clinical_pdf_report()` exports vector PDF summaries with patient demographics, executive KPIs, calibrated 10-second ECG strips ($25\text{ mm/s}$, $10\text{ mm/mV}$), the Events Diary, hourly Holter tables, Poincaré plots, and QT-RR restitution curves.
* **Atrial Fibrillation / Flutter Burden Engine:** Automatic sliding-window Shannon entropy and successive RR median absolute difference irregularity scoring with sustained episode segmentation ($\ge 30\text{ s}$) and 24h burden quantification.
* **Hourly Holter Trend Histograms & Triage Tab:** 1-hour epoch distribution tables tracking minimum, mean, and maximum heart rates, ventricular ectopy (PVCs, Couplets, VT Runs), supraventricular ectopy (PACs), sinus pauses ($\ge 2.0\text{ s}$, $\ge 2.5\text{ s}$), and hourly AF burden in the interactive **`🕒 Holter Triage`** tab.
* **Patrick Hamilton (2002) OSEA Beat Classifier:** Dynamic morphology template clustering with a 12.5% exponential adaptation rate, running median RR prematurity gating, compensatory pause checks, and AF entropy stabilization.
* **Peer-Reviewed Anti-Regression Conditioning:** AHA/ACC/HRS $0.05\text{ Hz}$ zero-phase Butterworth filter paired with cascaded $200\text{ ms} / 600\text{ ms}$ moving median baseline suppression and a narrow $Q=30$ powerline notch filter.
* **Two-Stage Signal Quality Assessment:** Stage 1 absolute spectral/statistical rejection thresholds (Li et al., 2014) gating Stage 2 six-index pairwise lead voting ($VI_k \in [-6, +6]$).
* **Complete 10-Model QT-RR Restitution & Hysteresis:** All 10 Pueyo (2004) biparametric curves with Vandermonde domain guards, state-space exponential (EW) and linear (LW) lag-weighted memory modeling, and interactive PyQtGraph cloud visualization.
* **Spatial Repolarization Heterogeneity & Autonomic Suite:** Synchronous multi-lead QT Dispersion ($QT_d$, $T_{pe,d}$) across qualified diagnostic leads ($\ge 3$ channels), biphasic Heart Rate Turbulence ($TO$, $TS$, Categories 0/1/2), and full HRV (time, Welch PSD, Poincaré/entropy/DFA).
* **Portable Clinical Exchange (`.pecg`):** De-identified single-file container supporting Zstandard (`zstd`) compression, CBOR/JSON metadata, and zero-copy memory mapping (`np.memmap`).
* **Modern Developer Stack:** Python $\ge 3.12$, 100% strict static typing, PEP 639 licensing metadata, Briefcase packaging, Astral `ruff`/`uv` workflows, and 90 passing automated unit tests.
