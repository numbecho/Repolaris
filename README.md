# Repolaris

**Modernized ECG Analysis, Ventricular Repolarization & Universal Holter Framework**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.14%2B-brightgreen.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/Tests-31%20Passed-success.svg)](tests/)
[![GUI](https://img.shields.io/badge/GUI-PyQt6%20%2B%20PyQtGraph-purple.svg)](src/repolaris/app.py)
[![Wiki](https://img.shields.io/badge/Documentation-Wiki-orange.svg)](wiki/Home.md)

Repolaris is a modernized clinical and research framework for continuous Electrocardiogram (ECG) waveform segmentation, ventricular repolarization dynamics, and universal Holter analysis[span_0](start_span)[span_0](end_span). It serves as the next-generation evolution of the foundational PyECG research project (Suárez-León et al., Universidad de Oriente & KU Leuven STADIUS).

---

## Overview & Documentation

Repolaris eliminates traditional vendor lock-in by providing zero-dependency multi-format ingestion[span_1](start_span)[span_1](end_span), strict Python static typing[span_2](start_span)[span_2](end_span), and a high-performance desktop workstation interface[span_3](start_span)[span_3](end_span). 

Comprehensive guides, algorithmic specifications, and developer instructions—including detailed GUI workflows, file format specifications (such as `.pecg`), and complete Python API references—are organized in the [**Repolaris Wiki**](wiki/Home.md):
- [Getting Started & CLI](wiki/Getting-Started.md) | [Architecture & Dataflow](wiki/Architecture-Overview.md) | [File Formats & I/O](wiki/File-Formats-and-IO.md)[span_4](start_span)[span_4](end_span)
- [Electrophysiology & QTc](wiki/Electrophysiology-and-Algorithms.md) | [Arrhythmia & AAMI EC57](wiki/Arrhythmia-and-AAMI-EC57.md) | [Workstation GUI Guide](wiki/Workstation-GUI-Guide.md)[span_5](start_span)[span_5](end_span)

---

## Key Features

- **Universal Multi-Format Ingestion:** Seamlessly opens commercial digital Holters, wearable telemetry patches, research databases, custom study containers, and delimited text with zero proprietary external dependencies[span_6](start_span)[span_6](end_span).
- **Advanced Repolarization & HRV:** Implements Berger's classical QT Variability Index (QTVI, Berger 1997)[span_7](start_span)[span_7](end_span)[span_8](start_span)[span_8](end_span), uniform spectral resampling (Berger 1986), and multi-model QT-RR restitution curve fitting[span_9](start_span)[span_9](end_span).
- **AAMI EC57 Beat Classification:** Automatically categorizes heartbeats and identifies ectopic rhythm sequences (Bigeminy, Trigeminy, Couplets, VT runs) with immutable physician audit logs[span_10](start_span)[span_10](end_span).
- **Automated Clinical Events Triage:** Scans recordings to index critical episodes: severe QTc prolongation ($QT_c \ge 500\text{ ms}$), short QT ($QT_c \le 340\text{ ms}$), sinus pauses, and rate extremes[span_11](start_span)[span_11](end_span).

---

## Supported File Formats & Compatibility

| Format | Extension | Origin | Capabilities |
| :--- | :--- | :--- | :--- |
| **Repolaris Study Bundle** | `.pecg` | Colleague Exchange | De-identified demographics, annotations, Zstd/Deflate/Raw storage[span_12](start_span)[span_12](end_span). |
| **ISHNE Holter Standard** | `.ecg` | Commercial Holters (Mortara, GE, Rozinn) | Full ISHNE 1.0 specification (522-byte header, nV resolution scaling)[span_13](start_span)[span_13](end_span). |
| **PhysioNet WFDB** | `.hea`, `.dat` | Clinical Research (MIT-BIH, QT Database) | Pure-Python reader supporting Format 16 and Format 212 bit-packed signals[span_14](start_span)[span_14](end_span). |
| **European Data Format** | `.edf` | Wearable Patches (Bittium Faros, SOMNOtouch) | Official EDF / EDF+ standard, epoch reconstruction, $\mu\text{V}/\text{mV}$ calibration[span_15](start_span)[span_15](end_span). |
| **Delimited Text / NumPy** | `.csv`, `.txt`, `.npy` | Community Clinics & Raw Sensors | Direct matrix loading of raw voltage tracks. |

---

## Installation

```bash
# Clone and setup with uv (recommended)
git clone [https://github.com/numbecho/repolaris.git](https://github.com/numbecho/repolaris.git)
cd repolaris
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,gui]"

## Citation
If you use this software in research, please cite the foundational PyECG paper:

@article{suarez2018pyecg,
  title={PyECG: A software tool for the analysis of the QT interval in the electrocardiogram},
  author={Su{\'a}rez-Le{\'o}n, Alexander A. and Varon, Carolina and Willems, Rik and Van Huffel, Sabine and V{\'a}zquez-Seisdedos, Carlos R.},
  journal={Revista de Ingenier{\'i}a Electr{\'o}nica, Autom{\'a}tica y Comunicaciones (RIELAC)},
  volume={39},
  number={2},
  pages={54--69},
  year={2018},
  url={[http://rielac.cujae.edu.cu/index.php/rieac/article/view/663](http://rielac.cujae.edu.cu/index.php/rieac/article/view/663)}
}
