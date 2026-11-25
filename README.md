# Repolaris

**Clinical ECG Analysis, Ventricular Repolarization, and Ambulatory Holter Workstation**

[![CI/CD](https://github.com/numbecho/Repolaris/actions/workflows/build-artifacts.yml/badge.svg)](https://github.com/numbecho/Repolaris/actions/workflows/build-artifacts.yml)
[![Version](https://img.shields.io/badge/Version-v0.9.11-0f766e?style=flat-square)](CHANGELOG.md)
[![License](https://img.shields.io/badge/License-Apache%202.0-334155?style=flat-square)](LICENSE)
[![Documentation](https://img.shields.io/badge/Docs-Wiki-1d4ed8?style=flat-square)](wiki/Home.md)

## Motivation

Evaluating ventricular repolarization, QT interval dynamics, and arrhythmia burden across modern cardiology practices is often fragmented by proprietary vendor formats, black-box automated measurements, and software restricted to a single recorder brand. Repolaris was created to provide physicians and clinical researchers with a transparent, vendor-neutral workstation for inspecting both standard resting 12-lead ECGs and continuous multi-day Holter recordings.

Evolving from the PyECG research platform (Suárez-León et al., Universidad de Oriente and KU Leuven STADIUS, 2018), Repolaris combines automated rhythm and repolarization triage with interactive manual verification, audit-logged beat reclassification, and printable clinical reporting.

## Clinical Capabilities and Biomarker References

### Ventricular Repolarization and Proarrhythmic Risk
- **QT and Rate-Corrected QTc Assessment:** Automated Q-onset, J-point, T-peak, and T-wave end delineation with Bazett, Fridericia, Framingham, and Hodges rate corrections, supporting multiple peer-reviewed T-wave end methods (Lepeschkin and Surawicz, 1952; Zhang et al., 2006; Martínez et al., 2010).
- **Early vs. Late Repolarization Sub-Intervals (FDA CiPA):** Separation of early repolarization (J-Tpeakc) from late transmural repolarization (Tpeak-Tend and Tpeak-Tend/QT ratio) to support drug-induced proarrhythmic risk evaluation and sudden cardiac death stratification (Gupta et al., 2008; Panikkath et al., 2011; Johannesen et al., 2016).
- **Beat-to-Beat Repolarization Lability:** Short-term and long-term QT variability (STV-QT and LTV-QT) for Torsades de Pointes risk assessment (Thomsen et al., 2004) alongside the QT Variability Index (Berger, 2003).
- **QT-RR Adaptation, Hysteresis, and Circadian Stratification:** Individualized QT-RR restitution modeling and adaptation lag (Pueyo et al., 2004), together with diurnal versus nocturnal heart rate dipping and nocturnal QTc lengthening profiles.
- **Spatial Repolarization and T-Wave Morphology:** Multi-lead QT dispersion (Day et al., 1990), T-wave asymmetry, flatness, and notch detection, 3D T-wave loop descriptors including Total Cosine R-to-T (Vicente et al., 2015), and a superimposed multi-lead butterfly median beat view with synchronized global calipers.
- **Microvolt T-Wave Alternans:** Spectral and Modified Moving Average T-wave alternans assessment (Nearing and Verrier, 2002).

### Ambulatory Holter, Arrhythmia, and Autonomic Assessment
- **Beat Classification and Rhythm Triage:** ANSI/AAMI EC57 beat classification (Normal, Ventricular, Supraventricular, Fusion, Unknown) with template matching (Hamilton, 2002), automatic detection of bigeminy, trigeminy, couplets, ventricular tachycardia runs, sinus pauses, and bradycardia/tachycardia extrema.
- **Atrial Fibrillation Burden and Hourly Trends:** Sustained atrial fibrillation episode segmentation, overall burden quantification, and hourly Holter distribution summaries.
- **ST-Segment and Conduction Screening:** Rate-adaptive ST-segment elevation/depression tracking, transient ischemic episode detection, atrial-fibrillation-gated P-wave and PR interval measurement for first- and second-degree AV block screening, and high-rate pacemaker spike detection.
- **Autonomic Tone and Respiration:** Standard time-domain, frequency-domain, and non-linear Heart Rate Variability (ESC/NASPE Task Force, 1996), Heart Rate Turbulence (Schmidt et al., 1999), Phase-Rectified Signal Averaging Deceleration and Acceleration Capacity (Bauer et al., 2006), and ECG-Derived Respiration for overnight respiratory rate and sleep-apnea screening (Moody and Mark, 1985).
- **Automated Signal Quality Assessment:** Two-stage lead quality screening and multi-lead ranking to flag noisy channels and guide lead selection (Li et al., 2014; Suárez-León et al., 2018).

### Physician Workstation Workflow
- **Interactive Waveform Review:** Smooth review of resting and 24-to-48-hour recordings with draggable Q-onset and T-end calipers, live interval recalculation, beat-by-beat keyboard navigation, and single-key beat reclassification with an immutable audit log.
- **Printable Clinical Reports:** Generates multi-page clinical PDF reports containing demographics, summary metrics, calibrated rhythm strips, a clinical events diary, hourly Holter tables, Poincaré plots, and QT-RR trends.
- **De-Identified Colleague Exchange:** Packages recordings, caliper overrides, and clinical notes into a single de-identified study file that removes direct patient identifiers while retaining age, sex, race/ethnicity, pacemaker status, and clinical indication for peer review.
- **Multi-Language Interface:** Available in English, Spanish, French, German, and Portuguese.

## Supported File Formats

| Format | Extension | Clinical / Device Origin | Notes |
| :--- | :--- | :--- | :--- |
| **DICOM Waveform** | `.dcm`, `.dicom` | Hospital PACS and 12-Lead ECG Carts | Standard 12-lead and ambulatory ECG waveforms calibrated to millivolts. |
| **HL7 Annotated ECG** | `.xml`, `.aecg` | Clinical Trials (FDA Thorough QT Studies) | Standard HL7 aECG rhythm strips and lead mappings. |
| **SCP-ECG** | `.scp` | Hospital ECGs and European Holter Systems | Uncompressed and standard Huffman-compressed 12-lead ECGs with derived limb leads. |
| **ISHNE Holter** | `.ecg`, `.ann` | Commercial Digital Holter Recorders | Standard ISHNE 1.0 multi-hour Holter recordings and reference beat annotations. |
| **EXCORDE 3C** | `.e3c` | ICID Ambulatory Holter Monitors | Multi-channel ambulatory Holter archives. |
| **European Data Format** | `.edf`, `.edf+` | Wearable Patches and Telemetry Devices | Continuous ambulatory ECG telemetry recordings. |
| **PhysioNet WFDB** | `.hea`, `.dat`, `.mat`, `.atr` | Clinical Research Databases (MIT-BIH, QTDB, PTB-XL) | Multi-lead reference recordings and beat annotation files. |
| **Repolaris Study Bundle** | `.pecg` | Physician-to-Physician Exchange | De-identified waveforms, clinical notes, and manual caliper overrides. |
| **Delimited Text** | `.csv`, `.txt` | Wearable Sensors and Clinic Exports | Standard tabular and timestamped wearable ECG exports. |

## Clinical Disclaimer

Repolaris is intended for clinical research and physician-supervised review. Automated fiducial placements, arrhythmia classifications, and risk metrics should always be verified by a qualified clinician prior to diagnostic or therapeutic decision-making.

## Documentation

Detailed user guides, workstation tutorials, and clinical documentation are available in the [Repolaris Wiki](wiki/Home.md).

## For Developers and Researchers

* **Stack:** Python 3.12+ (tested through 3.15), PySide6 + PyQtGraph workstation GUI, NumPy/SciPy DSP engine, Apache-2.0 licensed.
* **Quick Setup (`uv` or `pip`):**

```bash
uv sync --all-extras --dev          # or: pip install -e ".[dev]"
uv run repolaris                    # launch desktop workstation
uv run pytest -q && uv run ruff check src tests
```

* **Technical Guides:** [Architecture Overview](wiki/Architecture-Overview.md) · [Algorithms & EC57](wiki/Electrophysiology-and-Algorithms.md) · [Developer Guide](wiki/Developer-Guide.md) · [Packaging & CI/CD](wiki/Packaging-and-CI-CD-Guide.md)

## License and Academic Citation

Repolaris is released under the Apache License, Version 2.0 (see [LICENSE](LICENSE)).

If you use Repolaris in clinical research or publications, please cite the foundational work:

> Suárez-León, A. A., Varon, C., Willems, R., Van Huffel, S., and Vázquez-Seisdedos, C. R. (2018). *PyECG: A software tool for the analysis of the QT interval in the electrocardiogram.* Revista Ingeniería Electrónica, Automática y Comunicaciones (RIELAC), 39(2), 54–69.
