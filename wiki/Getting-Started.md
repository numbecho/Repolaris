# Getting Started with Repolaris

This guide walks you through installing Repolaris, setting up your environment, running automated checks, and analyzing your first electrocardiogram recording.

---

## 1. System Requirements

* **Operating System:** Linux (Ubuntu 20.04+, Debian 11+, Fedora 38+, Arch), macOS (12.0+ Monterey, Apple Silicon & Intel), Windows 10/11 (64-bit).
* **Python Runtime:** Python `>= 3.14`.
* **Hardware Acceleration:** OpenGL-compatible graphics card recommended for desktop GUI 60fps rendering.

---

## 2. Installation

### Option A: Using Astral `uv` (Recommended — Fastest)
[Astral `uv`](https://astral.sh/uv) provides instant virtual environment creation and deterministic dependency resolution:

```bash
# Clone the repository
git clone https://github.com/numbecho/repolaris.git
cd repolaris

# Provision Python 3.14 and sync all extras & dev groups
uv python install 3.14
uv sync --all-extras --dev

# Or create a virtual environment manually with uv pip
uv venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
uv pip install -e ".[gui,dev]"
```

### Option B: Using Standard Python `pip`
```bash
# Clone the repository
git clone https://github.com/numbecho/repolaris.git
cd repolaris

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# Install core signal processing and I/O engine
pip install -e .

# Install with PyQtGraph desktop GUI support
pip install -e ".[gui]"

# Install development and testing tools
pip install -e ".[dev]"
```

---

## 3. Verify Installation

Run the 130-test automated verification suite to confirm that all signal decoders, QTc formulas, autonomic modules, streaming buffers, and PDF report generators function properly:

```bash
# Option A: Standard Python unittest discovery (130 tests)
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m unittest discover tests -v

# Option B: Using Astral uv & Ruff (Python 3.14)
uv run ruff check src tests
QT_QPA_PLATFORM=offscreen uv run pytest -v
```

Expected output:
```text
Ran 130 tests in 9.850s

OK
```

---

## 4. Command Line Interface (CLI)

Repolaris provides two console entry points defined in `pyproject.toml`: `repolaris` (for headless analysis, streaming, and PDF/container export) and `repolaris-gui` (for the interactive desktop workstation).

### Run a Synthetic Demo
Generate a realistic 10-second synthetic ECG, execute the full analysis pipeline, and optionally export both a `.pecg` study bundle and a 2-page printable clinical PDF report:

```bash
repolaris demo --duration 10 --fs 500 --hr 72 --export demo_study.pecg --pdf demo_report.pdf
```

Console Output:
```text
========================================
    Repolaris Repolarization Report     
========================================
Heart Rate:          72.0 BPM
Total Beats:         12
Mean QT:             418.8 ms
Mean QTc Bazett:     457.9 ms
Mean QTc Fridericia: 444.2 ms
Mean QTc Framingham: 443.7 ms
Mean QTc Hodges:     439.0 ms
PVC Count:           0 (0.0%)
PAC Count:           0
QTVI:                -1.71
QT-RR Slope (Beta):  -0.0121
Hysteresis Lambda*:  0.0050 (t90: 351.8s)
HRV (SDNN / RMSSD):  1.0 ms / 1.7 ms
Peak MMA TWA:        36.9 uV (NORMAL)
SQI (pSQI/basSQI):   0.99 / 0.96
Quality Status:      EXCELLENT
AF Burden:           0.00% (0 episodes)
Holter Pauses:       0 (max 0.00s)
Clinical Events:     5 detected
========================================
```

### Analyze a Clinical Recording File (In-Memory or Streamed)
Analyze any clinical recording format from your terminal:

```bash
# Analyze an ISHNE Holter file in memory
repolaris analyze patient_record.ecg --fs 200 --lead 0

# Stream a 24h-48h Holter recording out-of-core and generate a 2-page PDF report
repolaris analyze long_holter.ecg --lead 0 --stream --chunk-sec 300 --pdf holter_report.pdf

# Analyze a DICOM 12-Lead Waveform, HL7 aECG XML, or SCP-ECG file
repolaris analyze clinical_12lead.dcm --lead "Lead II" --pdf dicom_report.pdf

# Export and de-identify a recording into a portable .pecg container
repolaris export patient_record.ecg anonymized_case.pecg --compression zstd

# Batch-analyze a cohort folder of mixed ECG/Holter files to CSV/JSON
repolaris batch ./cohort_records --csv cohort.csv --json cohort.json

# Run ANSI/AAMI EC57 beat-by-beat benchmarking on a real record + .atr/.ann file
repolaris benchmark --input 100.hea --reference 100.atr
```

---

## 5. Launching the Interactive GUI Workstation

Start the hardware-accelerated desktop viewer:

```bash
repolaris-gui
```

### Quick GUI Workflow
1. Click **`⚡ Demo Rhythm`** to generate an immediate synthetic benchmark, or click **`📂 Open Recording`** to load any clinical recording (`.dcm`, `.xml`, `.scp`, `.pecg`, `.ecg`, `.e3c`, `.edf`, `.hea`, `.csv`, `.npy`).
2. Observe the continuous waveform with detected R-peaks (red markers), Q-onset (gold caliper), and T-end (purple caliper).
3. Drag the calipers along any beat to recalculate $QT$ and $QT_c$ in real time.
4. Review the **`🚨 Events Diary`** and **`🕒 Holter Triage`** tabs on the right: click any flagged episode, hourly epoch, or AF episode to center the viewport directly on that timestamp.
5. Click **`📤 Export Case (.pecg)`** to package the de-identified study for colleague consultation, or **`📄 PDF Report`** (`Ctrl+P`) to generate a 2-page printable clinical PDF report.
