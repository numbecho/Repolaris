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

# Create a virtual environment with uv
uv venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# Install core library, GUI dependencies, and development tools
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

Run the 25-case automated test suite to verify that all signal decoders, QTc formulas, and event classifiers function properly:

```bash
python3 -m unittest discover tests
```

Expected output:
```text
Ran 25 tests in 0.482s

OK
```

---

## 4. Command Line Interface (CLI)

Repolaris provides two binary entry points: `repolaris` (and the legacy alias `pyecg`).

### Run a Synthetic Demo
Generate a realistic 10-second synthetic ECG, execute the full analysis pipeline, and view a formatted clinical report:

```bash
repolaris demo --duration 10 --fs 500 --hr 72
```

Console Output:
```text
Generating synthetic ECG (10.0s, 72.0 BPM, 500.0 Hz)...
=============================================
           REPOLARIS ANALYSIS REPORT
=============================================
Total Beats Analyzed : 12
Mean Heart Rate      : 72.0 BPM
Mean QT Interval     : 382.4 ms
Mean QTc (Bazett)    : 418.9 ms
Mean QTc (Fridericia): 406.3 ms
=============================================
```

### Analyze a Clinical Recording File
Analyze any clinical recording format from your terminal:

```bash
# Analyze an ISHNE Holter file
repolaris analyze patient_record.ecg --fs 200 --lead 0

# Analyze a PhysioNet WFDB record
repolaris analyze mitdb/100.hea --fs 360 --lead 0

# Analyze an EDF wearable telemetry patch
repolaris analyze telemetry_patch.edf --fs 250 --lead 0
```

---

## 5. Launching the Interactive GUI Workstation

Start the hardware-accelerated desktop viewer:

```bash
repolaris-gui
```
*(Alternative alias: `pyecg-gui`)*

### Quick GUI Workflow
1. Click **`⚡ Load Demo Signal`** to generate an immediate synthetic benchmark, or click **`📂 Open ECG File`** to load any clinical recording.
2. Observe the continuous waveform with detected R-peaks (red markers), Q-onset (gold caliper), and T-end (purple caliper).
3. Drag the calipers along any beat to recalculate $QT$ and $QT_c$ in real time.
4. Review the **`🚨 Events Diary`** table on the right: click any flagged episode (e.g., severe QTc, pause, tachycardia) to center the viewport directly on the beat with calipers pre-aligned.
5. Click **`📤 Export Anonymized Study (.pecg)`** to package the waveform and review notes for colleague consultation.
