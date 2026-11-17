# Repolaris

**Modernized ECG Analysis, Ventricular Repolarization & Universal Holter Framework**

[![Version](https://img.shields.io/badge/Version-v0.8.1-cyan.svg)](CHANGELOG.md)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.14%2B-brightgreen.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/Tests-99%20Passed-success.svg)](tests/)
[![Coverage](https://img.shields.io/badge/Coverage-85%25%20Engine%20%7C%2074%25%20Total-indigo.svg)](tests/)
[![GUI](https://img.shields.io/badge/GUI-PyQt6%20%2B%20PyQtGraph-purple.svg)](src/repolaris/app.py)
[![Wiki](https://img.shields.io/badge/Documentation-Wiki-orange.svg)](wiki/Home.md)

Repolaris is a modernized clinical and research framework for continuous Electrocardiogram (ECG) waveform segmentation, ventricular repolarization dynamics, and universal Holter analysis. It serves as the next-generation evolution of the foundational PyECG research project (Suárez-León et al., Universidad de Oriente & KU Leuven STADIUS).

The software empowers physicians and researchers to inspect long-term recordings from virtually any recording device—traditional multi-day Holter monitors, modern adhesive wearable patches, hospital PACS archives, or open research databases.

---

## Documentation & Wiki

Exhaustive guides, algorithmic specifications, format references, and GUI tutorials are organized in the [**Repolaris Wiki**](wiki/Home.md):
- [**Getting Started & CLI**](wiki/Getting-Started.md): Installation via `uv` or `pip`, CLI commands (`demo`, `analyze --stream --pdf`, `export`), and running demos.
- [**Architecture & Dataflow**](wiki/Architecture-Overview.md): Decoupled subpackages, MVC service controllers, streaming pipeline stages, and channel-sensing gating.
- [**Universal File Formats & I/O**](wiki/File-Formats-and-IO.md): Detailed specs for DICOM Waveform, HL7 aECG XML, SCP-ECG, `.pecg`, ISHNE 1.0 `.ecg`, Excorde 3C `.e3c`, EDF, and WFDB.
- [**Electrophysiological Algorithms & QTc**](wiki/Electrophysiology-and-Algorithms.md): Mathematical formulations for QTc, AF burden, Berger QTVI, QT dispersion, TWA, HRT, HRV, hysteresis, and two-stage SQI.
- [**Arrhythmia & AAMI EC57 Classification**](wiki/Arrhythmia-and-AAMI-EC57.md): Beat taxonomy (`N`, `V`, `S`, `F`, `Q`), Patrick Hamilton (2002) OSEA template matching, hourly Holter trends, and audit logging.
- [**Workstation GUI & Draggable Calipers**](wiki/Workstation-GUI-Guide.md): 60fps viewer, live recalculation HUD, Holter Triage tab, and printable PDF export.
- [**Developer & Contributing Guide**](wiki/Developer-Guide.md): Astral `uv`/`ruff` workflows, type checking, and test suites.
- [**Packaging & CI/CD Guide**](wiki/Packaging-and-CI-CD-Guide.md): Native desktop packaging (MSI, DMG, DEB, AppImage) via BeeWare Briefcase and GitHub Actions.
- [**FAQ & Troubleshooting**](wiki/FAQ-and-Troubleshooting.md): Common questions, troubleshooting tips, and academic citations.
- [**i18n & Translation Guide**](wiki/Internationalization-and-Translation-Guide.md): Multi-language UI support (English, Spanish, French, German, Portuguese) and contributor localization guide.

---

## Key Features

- **Universal Multi-Format Ingestion:** Opens hospital PACS waveforms (DICOM Waveform SOP Class `1.2.840.10008.5.1.4.1.1.9.1.1` and `9.1.2`), FDA clinical trial files (HL7 Annotated ECG XML), European standards (SCP-ECG CEN EN 1064 / ISO 13713), commercial digital Holters (ISHNE `.ecg` and Excorde 3C `.e3c`), wearable telemetry patches (EDF/EDF+ `.edf`), research databases (PhysioNet WFDB `.hea`/`.dat`), and delimited text (`.csv`/`.txt`/`.npy`) with zero proprietary external dependencies.
- **Out-of-Core Long-Term Holter Streaming (`SignalBuffer` & `analyze_ecg_stream`):** Processes continuous 24h–48h multi-lead recordings via `np.memmap`-backed disk buffers and overlapping windows, eliminating filter edge transients, deduplicating boundary R-peaks, and preventing RAM exhaustion.
- **Automated Printable Clinical PDF Reports (`pdf_report.py`):** Generates publication-grade, 2-page vector PDF reports featuring patient demographics, executive repolarization and arrhythmia KPI tables, calibrated 10-second ECG rhythm strips ($25\text{ mm/s}$, $10\text{ mm/mV}$), the Clinical Events Diary, hourly Holter trend tables, Poincaré Lorentz plots, and QT-RR restitution curves.
- **Patrick Hamilton (2002) OSEA Template Matching:** Dynamic template clustering with a 12.5% adaptation rate on dominant normal complexes, dual prematurity gating (<0.82 running median RR), compensatory pause detection, and AF entropy stabilization.
- **Atrial Fibrillation / Flutter Burden & Hourly Holter Trends:** Automated Shannon entropy and successive RR irregularity scoring with sustained episode segmentation ($\ge 30\text{ s}$) and 1-hour epoch distribution tables for Holter triage.
- **Advanced Repolarization Dynamics & Autonomic Suite:** Implements Berger's classical QT Variability Index (QTVI), multi-beat QT-RR memory hysteresis (EW/LW profiles), 10 domain-guarded Pueyo (2004) restitution models, full Heart Rate Variability (time, Welch frequency, Poincaré non-linear), Heart Rate Turbulence (TO/TS baroreflex post-PVC), microvolt T-Wave Alternans (spectral FFT and MMA), and multi-lead QT dispersion (QTd) with conditional multi-lead gating.
- **AAMI EC57 Beat Classifier & Rhythm Patterns:** Classifies individual heartbeats into diagnostic categories (Normal, PVC, PAC, Fusion, Unknown) and detects ectopic sequences (Bigeminy, Trigeminy, Couplets, VT runs) with audit-tracked physician annotation overrides.
- **Automated Lead Signal Quality Index (SQI):** Stage 1 absolute spectral/statistical rejection thresholds (Li et al., 2014) gating Stage 2 six-index pairwise lead voting ($VI_k \in [-6, +6]$; Suárez-León et al., 2018).
- **Automated Clinical Events Triage:** Automatically scans multi-hour recordings and indexes critical episodes: severe QTc prolongation ($QT_c \ge 500\text{ ms}$), borderline prolongation ($QT_c \ge 480\text{ ms}$), short QT ($QT_c \le 340\text{ ms}$), sinus pauses ($RR \ge 2.0\text{ s}$), rate extremes (max/min HR, tachycardia, bradycardia), and ventricular ectopics (PVCs).
- **Interactive 60fps GUI (`pyqtgraph`):** Hardware-accelerated desktop viewer providing smooth panning across 24-hour recordings, draggable Q-onset and T-end calipers with live Bazett/Fridericia recalculation, a one-click click-to-seek Events Diary, a dedicated **`🕒 Holter Triage`** tab, and conditional channel-sensing gating that automatically adapts between single-lead patches and 12-lead Holters.
- **De-Identified Colleague Study Exchange (`.pecg`):** A custom single-file container bundling continuous waveforms with clinical review notes and caliper overrides. Automatically strips direct patient identifiers while strictly preserving **Age**, **Race/Ethnicity**, **Sex**, **Pacemaker Status**, and **Clinical Indication** for accurate diagnostic review. Supports **Zstandard (`zstd`)**, **Deflate**, and raw zero-copy `np.memmap` storage.
- **Type-Safe & Decoupled:** Strict type annotations (PEP 484/585/604) across all modules, allowing the signal engine to run headlessly in scripts, automated pipelines, or Docker containers without GUI overhead.

---

## Supported File Formats

| Format | Extension | Hardware / Clinical Origin | Processing Capabilities |
| :--- | :--- | :--- | :--- |
| **DICOM Waveform** | `.dcm`, `.dicom` | Hospital PACS / ECG Carts | SOP Classes 1.2.840.10008.5.1.4.1.1.9.1.1/9.1.2, 12-lead & rhythm scaling to physical mV. |
| **HL7 Annotated ECG** | `.xml`, `.aecg` | FDA Clinical Trials (TQT) | ANSI/HL7 aECG XML standard, MDC_ECG lead mappings, and comma/period decimal normalization. |
| **SCP-ECG Standard** | `.scp` | Hospital & Holter Devices | CEN EN 1064 / ISO 13713 Sections 0, 3, and 6 uncompressed rhythm decoding with safety guards. |
| **Repolaris Study Bundle** | `.pecg` | Colleague Exchange | De-identified demographics (Age, Race, Sex), annotations, Zstd/Deflate/Raw `np.memmap` storage. |
| **ISHNE Holter Standard** | `.ecg` | Commercial Holters (Mortara, GE, Rozinn) | Full ISHNE 1.0 specification (522-byte header, nV resolution scaling, demographics, notes). |
| **Excorde 3C Holter** | `.e3c` | Fukuda Denshi Holter Monitors | In-memory ZIP archive reader decoding 2-channel int16 streams and 25-byte QRS records. |
| **PhysioNet WFDB** | `.hea`, `.dat` | Clinical Research (MIT-BIH, QT Database, PTB-XL) | Native pure-Python reader supporting Format 16 and Format 212 bit-packed signals. |
| **European Data Format** | `.edf`, `.edf+` | Wearable Patches & Telemetry (Bittium Faros, SOMNOtouch) | Official EDF / EDF+ standard, epoch reconstruction, uV/mV calibration. |
| **Delimited Text / NumPy** | `.csv`, `.txt`, `.npy` | Community Clinics & Raw Sensors | Direct matrix loading and memory-mapped streaming of raw voltage tracks. |

---

## Installation

### Prerequisites
- Python `>= 3.14` (managed via [Astral `uv`](https://docs.astral.sh/uv/) and `.python-version`)

### Setup

```bash
# Clone the repository
git clone https://github.com/numbecho/repolaris.git
cd repolaris

# Option A: Using Astral uv (Python 3.14 — https://astral.sh/uv)
uv python install 3.14
uv sync --all-extras --dev

# Option B: Using standard Python venv & pip
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
pip install -e ".[dev,gui]"
```

---

## Quick Start & CLI Usage

```bash
# 1. Run a synthetic demo and generate both a .pecg study and a 2-page clinical PDF report
repolaris demo --duration 15 --fs 500 --hr 72 --export demo_study.pecg --pdf demo_report.pdf

# 2. Analyze any clinical ECG / Holter file (add --stream for 24h-48h out-of-core streaming)
repolaris analyze patient_holter.ecg --lead 0 --stream --pdf holter_report.pdf

# 3. Export and de-identify a recording into a compressed .pecg container
repolaris export patient_holter.ecg case_01.pecg --compression zstd

# 4. Launch the 60fps desktop workstation GUI
repolaris-gui
```

---

## Code Quality & Testing

```bash
# Option A: Run the 99-test automated verification suite with standard Python unittest
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m unittest discover tests -v

# Option B: Lint, format, and test with Astral uv & Ruff (Python 3.14)
uv run ruff check src tests
uv run ruff format --check src tests
QT_QPA_PLATFORM=offscreen uv run pytest -v
QT_QPA_PLATFORM=offscreen uv run python -m unittest discover tests.test_tooling_uv_ruff -v
```

---

## License

This project is licensed under the **Apache License, Version 2.0**. See the [LICENSE](LICENSE) file for details.

---

## Citation & Academic Heritage

If you use this software in academic or clinical research, please cite the original foundational paper from Universidad de Oriente and KU Leuven:

> **Suárez-León, A. A., Varon, C., Willems, R., Van Huffel, S., & Vázquez-Seisdedos, C. R. (2018).**  
> *PyECG: A software tool for the analysis of the QT interval in the electrocardiogram.*  
> Revista Ingeniería Electrónica, Automática y Comunicaciones (RIELAC), 39(2), 54-69.  
> [https://rielac.cujae.edu.cu/index.php/rie/article/view/498](https://rielac.cujae.edu.cu/index.php/rie/article/view/498)

```bibtex
@article{suarez2018herramienta,
  title = {PyECG: A software tool for the analysis of the QT interval in the electrocardiogram},
  author = {Suárez-León, Alexander A. and Varon, Carolina and Willems, Rik and Van Huffel, Sabine and Vázquez-Seisdedos, Carlos R.},
  journal = {Revista Ingeniería Electrónica, Automática y Comunicaciones (RIELAC)},
  volume = {39},
  number = {2},
  pages = {54--69},
  year = {2018},
  url = {https://rielac.cujae.edu.cu/index.php/rie/article/view/498}
}
```
