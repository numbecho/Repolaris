# Repolaris

**Modernized ECG Analysis, Ventricular Repolarization & Universal Holter Framework**

[![Version](https://img.shields.io/badge/Version-v0.5.0-cyan.svg)](CHANGELOG.md)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.14%2B-brightgreen.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/Tests-51%20Passed-success.svg)](tests/)
[![GUI](https://img.shields.io/badge/GUI-PyQt6%20%2B%20PyQtGraph-purple.svg)](src/repolaris/app.py)
[![Wiki](https://img.shields.io/badge/Documentation-Wiki-orange.svg)](wiki/Home.md)

Repolaris is a modernized clinical and research framework for continuous Electrocardiogram (ECG) waveform segmentation, ventricular repolarization dynamics, and universal Holter analysis. It serves as the next-generation evolution of the foundational PyECG research project (Suárez-León et al., Universidad de Oriente & KU Leuven STADIUS).

The software empowers physicians and researchers to inspect long-term recordings from virtually any recording device—traditional multi-day Holter monitors, modern adhesive wearable patches, hospital PACS archives, or open research databases.

---

## Documentation & Wiki

Exhaustive guides, algorithmic specifications, format references, and GUI tutorials are organized in the [**Repolaris Wiki**](wiki/Home.md):
- [**Getting Started & CLI**](wiki/Getting-Started.md): Installation via `uv` or `pip`, CLI commands, and running demos.
- [**Architecture & Dataflow**](wiki/Architecture-Overview.md): Decoupled subpackages, pipeline stages, and backward compatibility.
- [**Universal File Formats & I/O**](wiki/File-Formats-and-IO.md): Detailed specs for `.pecg`, ISHNE 1.0 `.ecg`, Excorde 3C `.e3c`, EDF, and WFDB.
- [**Electrophysiological Algorithms & QTc**](wiki/Electrophysiology-and-Algorithms.md): Mathematical formulations for QTc, Berger QTVI, QT dispersion, TWA, HRT, HRV, hysteresis, and SQI.
- [**Arrhythmia & AAMI EC57 Classification**](wiki/Arrhythmia-and-AAMI-EC57.md): Beat taxonomy (`N`, `V`, `S`, `F`, `Q`), coupled sequences, and audit logging.
- [**Workstation GUI & Draggable Calipers**](wiki/Workstation-GUI-Guide.md): 60fps viewer, live recalculation HUD, and clinical triage diary.
- [**Developer & Contributing Guide**](wiki/Developer-Guide.md): Astral `uv`/`ruff` workflows, type checking, and test suites.
- [**Packaging & CI/CD Guide**](wiki/Packaging-and-CI-CD-Guide.md): Native desktop packaging (MSI, DMG, DEB, AppImage) via BeeWare Briefcase and GitHub Actions.
- [**FAQ & Troubleshooting**](wiki/FAQ-and-Troubleshooting.md): Common questions, troubleshooting tips, and academic citations.
- [**i18n & Translation Guide**](wiki/Internationalization-and-Translation-Guide.md): Multi-language UI support (English, Spanish, French, German, Portuguese) and contributor localization guide.

---

## Key Features

- **Universal Multi-Format Ingestion:** Opens commercial digital Holters (ISHNE `.ecg`), wearable telemetry patches (EDF/EDF+ `.edf`), research databases (PhysioNet WFDB `.hea`/`.dat`), and delimited text (`.csv`/`.txt`) with zero proprietary external dependencies.
- **Advanced Repolarization Dynamics & Autonomic Suite:** Implements Berger's classical QT Variability Index (QTVI), multi-beat QT-RR memory hysteresis (EW/LW profiles), full Heart Rate Variability (time, Welch frequency, Poincaré non-linear), Heart Rate Turbulence (TO/TS baroreflex post-PVC), microvolt T-Wave Alternans (spectral FFT and MMA), and multi-lead QT dispersion (QTd) with conditional multi-lead gating.
- **AAMI EC57 Beat Classifier & Rhythm Patterns:** Classifies individual heartbeats into diagnostic categories (Normal, PVC, PAC, Fusion, Unknown) and detects ectopic sequences (Bigeminy, Trigeminy, Couplets, VT runs) with audit-tracked physician annotation overrides.
- **Automated Lead Signal Quality Index (SQI):** Computes QRS relative power (pSQI), baseline drift stability (basSQI), and SNR to screen and rank leads before running diagnostic measurements.
- **Automated Clinical Events Triage:** Automatically scans multi-hour recordings and indexes critical episodes: severe QTc prolongation (QTc >= 500 ms), borderline prolongation (QTc >= 480 ms), short QT (QTc <= 340 ms), sinus pauses (RR >= 2.0 s), rate extremes (max/min HR, tachycardia, bradycardia), and ventricular ectopics (PVCs).
- **Interactive 60fps GUI (`pyqtgraph`):** Hardware-accelerated desktop viewer providing smooth panning across 24-hour recordings, draggable Q-onset and T-end calipers with live Bazett/Fridericia recalculation, a one-click click-to-seek Events Diary, and conditional channel-sensing gating that automatically adapts between single-lead patches and 12-lead Holters.
- **De-Identified Colleague Study Exchange (`.pecg`):** A custom single-file container bundling continuous waveforms with clinical review notes and caliper overrides. Automatically strips direct patient identifiers while strictly preserving **Age**, **Race/Ethnicity**, **Sex**, **Pacemaker Status**, and **Clinical Indication** for accurate diagnostic review. Supports **Zstandard (`zstd`)**, **Deflate**, and raw zero-copy `np.memmap` storage.
- **Relational SQLite Store:** Normalized schema (`patients`, `recordings`, `recording_channels`, `recording_events`) paired with lossless JSON document archiving for sub-millisecond cohort queries.
- **Type-Safe & Decoupled:** Strict type annotations (PEP 484/585/604) across all modules, allowing the signal engine to run headlessly in scripts, automated pipelines, or Docker containers without GUI overhead.

---

## Supported File Formats

| Format | Extension | Hardware / Clinical Origin | Processing Capabilities |
| :--- | :--- | :--- | :--- |
| **Repolaris / PECG Study Bundle** | `.pecg` | Colleague Exchange | De-identified demographics (Age, Race, Sex), annotations, Zstd/Deflate/Raw storage. |
| **ISHNE Holter Standard** | `.ecg` | Commercial Holters (Mortara, GE, Rozinn, E3C) | Full ISHNE 1.0 specification (522-byte header, nV resolution scaling, demographics, notes). |
| **PhysioNet WFDB** | `.hea`, `.dat` | Clinical Research (MIT-BIH, QT Database, PTB-XL) | Native pure-Python reader supporting Format 16 and Format 212 bit-packed signals. |
| **European Data Format** | `.edf` | Wearable Patches & Telemetry (Bittium Faros, SOMNOtouch) | Official EDF / EDF+ standard, epoch reconstruction, uV/mV calibration. |
| **Delimited Text / NumPy** | `.csv`, `.txt`, `.npy` | Community Clinics & Raw Sensors | Direct matrix loading of raw voltage tracks. |

---

## Installation

### Prerequisites
- Python `>= 3.14`

### Setup

```bash
# Clone the repository
git clone https://github.com/numbecho/repolaris.git
cd repolaris

# Option A: Using Astral uv (recommended - https://astral.sh/uv)
uv venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev,gui]"

# Option B: Using standard Python venv & pip
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
pip install -e ".[dev,gui]"
```

### Code Quality (Astral Ruff)

```bash
# Fast linting with Ruff
ruff check .

# Fast code formatting with Ruff
ruff format .
```

### UI Precompilation (`app.ui`)

Repolaris bundles a declarative Qt 6 Designer layout at `src/repolaris/resources/app.ui` along with a precompiled Python module `src/repolaris/resources/ui_app.py`. When modifying UI layouts in Qt Designer, recompile the interface with either:

```bash
# Option A: Built-in precompiler engine (auto-detects pyuic6 or uses standalone generator)
python -m repolaris.resources.compile_ui

# Option B: Standard pyuic6 CLI
pyuic6 src/repolaris/resources/app.ui -o src/repolaris/resources/ui_app.py
```


---

## Quick Start Guide

### 1. Python API

Load any clinical recording, run the analysis pipeline, and inspect detected clinical alerts:

```python
from repolaris.io.ecg_loader import load_ecg_file
from repolaris.detection.pipeline import analyze_ecg

# 1. Ingest any supported format (ISHNE, WFDB, EDF, E3C, or PECG)
lead_signal = load_ecg_file("holter_study.ecg", lead_name_or_index=0)

# 2. Run the end-to-end analysis pipeline (500 Hz)
results = analyze_ecg(lead_signal, fs=500.0)

# 3. Inspect global clinical metrics
summary = results["summary"]
print(f"Total Beats:          {summary['total_beats']}")
print(f"Mean Heart Rate:      {summary['mean_hr_bpm']:.1f} BPM")
print(f"Mean QT Interval:     {summary['mean_qt_ms']:.1f} ms")
print(f"Mean QTc (Bazett):    {summary['mean_qtc_bazett_ms']:.1f} ms")
print(f"Mean QTc (Fridericia):{summary['mean_qtc_fridericia_ms']:.1f} ms")

# 4. Triage flagged clinical events
print("\n--- CLINICAL EVENTS DIARY ---")
for ev in results["events"]:
    print(f"[{ev['severity']}] at {ev['timestamp_sec']:.2f}s: {ev['description']}")
```

### 2. Desktop GUI Application

Launch the hardware-accelerated interactive viewer:

```bash
repolaris-gui
```

- **Open File:** Click `📂 Open Any Recording` to load any supported format (`.pecg`, `.ecg`, `.edf`, `.hea`, `.e3c`, `.csv`).
- **Interactive Calipers:** Click and drag the gold (Q-onset) or purple (T-end) calipers along any beat to recalculate QT and QTc in real time.
- **Events Diary:** Click any row in the `🚨 Events Diary` table to immediately pan and center the viewport over that exact episode with calipers pre-aligned.
- **Export Study:** Click `📤 Export Anonymized Study (.pecg)` to prompt for Age, Race/Ethnicity, and consultation notes, bundling the case into a compressed single file for colleague peer review.

### 3. Command Line Interface (CLI)

```bash
# Run a synthetic 10-second benchmark demonstration
repolaris demo --duration 10 --fs 500 --hr 72

# Analyze any clinical recording from terminal
repolaris analyze path/to/recording.edf --fs 250 --lead 0
```

---

## Colleague Study Exchange (`.pecg`)

When sharing a study for a second opinion, patient confidentiality is paramount. The `.pecg` format automatically de-identifies the record while strictly preserving variables required for QT interpretation:

```python
from repolaris.io.pecg_format import save_pecg, load_pecg

# Export an anonymized study package
save_pecg(
    filepath="consult_study_7F9B2A.pecg",
    signals=lead_signals,
    sampling_rate=500.0,
    lead_names=["Lead I", "Lead II", "V5"],
    patient_info={
        "age": 64,
        "race": "Hispanic / Latino",
        "sex": "M",
        "indication": "Syncope; evaluate for drug-induced QT prolongation",
        "pacemaker": "NO"
    },
    annotations={
        "physician_notes": [
            {"author": "Dr. Clinical Reviewer", "comment": "Check T-end caliper position on beat #142"}
        ]
    },
    compression="zstd"  # Options: "zstd" (fastest), "deflate" (zero-dependency), or "none" (mmap)
)

# Colleague opens the file instantly with zero RAM overhead
metadata, signals = load_pecg("consult_study_7F9B2A.pecg", mmap=True)
print("Patient Age:", metadata["patient"]["age"])
print("Patient Race:", metadata["patient"]["race"])
```

---

## Testing

Run the automated test suite covering all signal processing, peak detectors, event classifiers, and file format readers:

```bash
# Using pytest
pytest

# Or using unittest
python3 -m unittest discover tests
```

---

## License

This project is licensed under the **Apache License, Version 2.0**. See the [LICENSE](LICENSE) file for details.

---

## Citation & Academic Heritage

If you use this software in academic or clinical research, please cite the original foundational paper from Universidad de Oriente and KU Leuven:

> **Suárez-León, A. A., Varon, C., Willems, R., Van Huffel, S., & Vázquez-Seisdedos, C. R. (2018).**  
> *Herramienta para el análisis de la repolarización ventricular en el electrocardiograma.*  
> Revista Ingeniería Electrónica, Automática y Comunicaciones (RIELAC), 39(1), 1-13.  
> [https://rielac.cujae.edu.cu/index.php/rie/article/view/498](https://rielac.cujae.edu.cu/index.php/rie/article/view/498)

```bibtex
@article{suarez2018herramienta,
  title = {Herramienta para el análisis de la repolarización ventricular en el electrocardiograma},
  author = {Suárez-León, Alexander A. and Varon, Carolina and Willems, Rik and Van Huffel, Sabine and Vázquez-Seisdedos, Carlos R.},
  journal = {Revista Ingeniería Electrónica, Automática y Comunicaciones (RIELAC)},
  volume = {39},
  number = {1},
  pages = {1-13},
  year = {2018},
  url = {https://rielac.cujae.edu.cu/index.php/rie/article/view/498}
}
```
