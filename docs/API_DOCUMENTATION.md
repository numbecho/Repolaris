# Repolaris: Architecture & Complete API Reference (v0.8.0)

This document provides technical documentation for every module, class, and function call across the modernized Repolaris framework.

---

## 1. System Architecture Overview

Repolaris is organized into decoupled layers so that signal conditioning, electrophysiological delineation, and autonomic risk algorithms run independently from desktop GUI dependencies:

```
src/repolaris/
├── __init__.py               # Package metadata (__version__ = "0.8.0") and public exports
├── config.py                 # Clinical thresholds and signal processing parameters
├── i18n.py                   # Multi-language localization (EN, ES, FR, DE, PT)
├── api/
│   ├── __init__.py           # Unified in-process MVC service controllers
│   ├── study.py              # StudyAPI: dataset loading and synthetic rhythm generation
│   ├── analysis.py           # AnalysisAPI: pipeline, QTc, QTd, TWA, HRT, HRV, Hysteresis, AF, Trends
│   └── export.py             # ExportAPI: de-identified .pecg study packaging
├── utils/
│   └── signal.py             # Realistic multi-component synthetic ECG generation
├── preprocessing/
│   ├── filter.py             # Butterworth bandpass (0.05-45 Hz) and IIR notch filtering (Q=30)
│   └── baseline.py           # Two-stage median baseline wander suppression (200ms / 600ms)
├── detection/
│   ├── qrs.py                # Derivative-energy R-peak detector (Pan-Tompkins inspired)
│   ├── q_onset.py            # Backward inflection detection for ventricular depolarization
│   ├── t_end.py              # 4 modes: hybrid tangent, ICH E14 tangent, Zhang SWA, threshold
│   ├── pulse_metrics.py      # RR intervals, BPM, Bazett, Fridericia, Framingham, Hodges QTc
│   ├── qtvi.py               # Berger QT Variability Index & 4 Hz step-integration resampling
│   ├── qtrr.py               # 10 domain-guarded non-linear dynamic QT-RR restitution models
│   ├── sqi.py                # Two-stage SQI: Stage 1 absolute gates + Stage 2 pairwise 6-index voting
│   ├── dispersion.py         # Multi-lead QT dispersion (QTd) & precordial Tpe dispersion
│   ├── twa.py                # Microvolt T-Wave Alternans (Spectral FFT & continuous MMA)
│   ├── hrt.py                # Heart Rate Turbulence (Turbulence Onset & Turbulence Slope)
│   ├── hrv.py                # Comprehensive HRV (Time, Welch PSD, Poincaré, SampEn, DFA)
│   ├── hysteresis.py         # Multi-beat QT-RR memory modeling (EW & LW lag kernels)
│   ├── classifier.py         # ANSI/AAMI EC57 beat classifier (N, V, S, F, Q) & sequences
│   ├── hamilton_classifier.py # Patrick Hamilton (2002) OSEA template matching with AF stabilizer
│   ├── af_detector.py        # Atrial Fibrillation/Flutter burden & Shannon entropy segmentation
│   ├── trends.py             # Hourly arrhythmia trend histograms (Min/Mean/Max HR, ectopics, pauses, AF)
│   ├── annotations.py        # AnnotationManager with immutable ISO 8601 audit logging
│   ├── events.py             # Clinical triage: severe QTc, pauses, tachycardia, PVCs
│   └── pipeline.py           # End-to-end master analysis pipeline
├── io/
│   ├── ecg_loader.py         # Universal multi-format ingestion router & sniff_ecg_format
│   ├── dicom_reader.py       # DICOM Waveform (SOP Class 1.2.840.10008.5.1.4.1.1.9.1.1/9.1.2)
│   ├── hl7_reader.py         # HL7 Annotated ECG XML (ANSI/HL7 aECG) with European decimal normalization
│   ├── scp_reader.py         # SCP-ECG (CEN EN 1064 / ISO 13713) with Section 2/5 safety guards
│   ├── pecg_format.py        # Single-file exchange container (CBOR/JSON + Zstd/Deflate)
│   ├── ishne_reader.py       # Official ISHNE 1.0 Holter (.ecg) binary parser & writer
│   ├── e3c_reader.py         # Excorde 3C (.e3c) Holter archive parser
│   ├── wfdb_reader.py        # PhysioNet WFDB (.hea + .dat) Format 16/212 parser
│   └── edf_reader.py         # European Data Format (EDF / EDF+) parser
├── resources/
│   ├── app.ui                # Declarative Qt 6 Designer XML workstation layout
│   ├── compile_ui.py         # Automated UI precompiler engine
│   └── ui_app.py             # Precompiled Ui_MainWindow class
├── cli.py                    # Command-line interface with formatted clinical tables
└── app.py                    # 60fps PyQtGraph desktop workstation GUI
```

---

## 2. Configuration (`repolaris.config`)

### `FilterConfig` (dataclass)
Holds digital filter parameters.
- **Attributes:**
  - `lowcut` (*float*): Highpass cutoff frequency in Hz (default: `0.05`). Preserves ST-T repolarization morphology per AHA/ACC/HRS guidelines.
  - `highcut` (*float*): Lowpass cutoff frequency in Hz (default: `45.0`). Eliminates electromyographic (EMG) noise.
  - `filter_order` (*int*): Butterworth filter order (default: `3`).
  - `notch_freq` (*float*): Powerline hum interference frequency in Hz (default: `50.0`).
  - `notch_quality` (*float*): Quality factor $Q$ for the notch filter (default: `30.0`).

### `DetectionConfig` (dataclass)
Holds clinical detection windows, refractory constraints, and algorithm selectors.
- **Attributes:**
  - `refractory_period_ms` (*float*): Minimum physiological time between consecutive R-peaks (default: `250.0` ms, max 240 BPM).
  - `qrs_integration_window_ms` (*float*): Moving average integration window width (default: `120.0` ms).
  - `q_search_window_ms` (*float*): Search window preceding R-peak for Q-onset (default: `100.0` ms).
  - `t_search_window_ms` (*float*): Search window following R-peak for T-wave end (default: `450.0` ms).
  - `t_end_method` (*str*): T-end delineation mode: `"hybrid"` (default), `"tangent"` (ICH E14), `"zhang_area"` (Zhang 2006 SWA), or `"threshold"`.
  - `t_end_threshold_ratio` (*float*): Voltage threshold ratio along descending T slope (default: `0.15`).
  - `qtrr_model` (*str*): Active Pueyo 2004 restitution formulation (default: `"linear"`).
  - `enable_hysteresis` (*bool*): Enables multi-beat hysteresis correction (default: `True`).
  - `hysteresis_kernel` (*str*): Memory lag weighting kernel: `"exponential"` (default) or `"linear"`.

### `ECGConfig` (dataclass)
Top-level configuration orchestrating sampling rate, filter, and detection sub-configs.
- **Attributes:**
  - `sampling_rate` (*float*): Lead sampling frequency in Hz (default: `500.0`).
  - `filter_cfg` (*FilterConfig*): Preprocessing configuration.
  - `detection_cfg` (*DetectionConfig*): Waveform detection thresholds.

---

## 3. Preprocessing (`repolaris.preprocessing`)

### `repolaris.preprocessing.filter.bandpass_filter(data, fs, cfg=FilterConfig())`
Applies a zero-phase bidirectional Butterworth bandpass filter (`scipy.signal.filtfilt`).

### `repolaris.preprocessing.filter.notch_filter(data, fs, freq=50.0, q=30.0)`
Eliminates sinusoidal 50 Hz or 60 Hz powerline hum via narrow zero-phase IIR notch filtering.

### `repolaris.preprocessing.baseline.remove_baseline_wander(data, fs)`
Suppresses respiration and motion baseline wander via two-stage moving median filtering (200 ms QRS suppression followed by 600 ms P/T wave suppression).

---

## 4. Detection & Electrophysiology (`repolaris.detection`)

### `repolaris.detection.qrs.detect_r_peaks(filtered_signal, fs, refractory_ms=250.0)`
Detects ventricular depolarization R-peaks using derivative squaring, moving-window integration, and local maximum refinement.

### `repolaris.detection.q_onset.detect_q_onset(signal, r_peak, fs, search_window_ms=100.0)`
Locates the electrical onset of ventricular depolarization prior to the R-peak.

### `repolaris.detection.t_end.detect_t_end(signal, r_peak, fs, search_window_ms=450.0, threshold_ratio=0.15, method="hybrid")`
Delineates ventricular repolarization offset (T-wave terminus).
- **Methods:** `"hybrid"`, `"tangent"`, `"zhang_area"` (sliding-window area), and `"threshold"`.
- **Returns:** `tuple[int, int]`: `(t_peak_sample, t_end_sample)`.

### `repolaris.detection.pulse_metrics.compute_qtc(qt_sec, rr_sec)`
Calculates rate-corrected QT intervals:
- `"bazett_ms"`: $QT_c = \frac{QT}{\sqrt{RR}}$
- `"fridericia_ms"`: $QT_c = \frac{QT}{\sqrt[3]{RR}}$
- `"framingham_ms"`: $QT_c = QT + 154 \times (1 - RR)$
- `"hodges_ms"`: $QT_c = QT + 1.75 \times (\text{HR} - 60)$

### `repolaris.detection.hamilton_classifier.HamiltonBeatClassifier`
Patrick Hamilton (2002) Open Source ECG Analysis dynamic template-matching beat classifier.
- **Methods:**
  - `classify_recording(signal, r_peaks, q_onsets=None, t_ends=None)`: Groups beats into morphology clusters with 12.5% exponential adaptation, running median RR prematurity checks (<0.82), compensatory pause detection, and dynamic Shannon entropy gating to suppress false-positive PVCs under chaotic AF rhythms.
- **Returns:** `tuple[List[ClassifiedBeat], Dict[str, Any]]`.

### `repolaris.detection.af_detector.detect_atrial_fibrillation(r_peaks, fs=500.0, window_beats=32, min_episode_duration_sec=30.0, entropy_threshold=0.68, irregularity_threshold=0.12)`
Detects sustained Atrial Fibrillation / Flutter episodes and calculates 24h burden percentage.
- **Helper functions:** `compute_rr_entropy(rr_intervals)`, `compute_rr_irregularity(rr_intervals)`.
- **Returns:** `AFBurdenReport` dataclass containing `total_duration_sec`, `af_total_duration_sec`, `af_burden_pct`, `num_episodes`, `longest_episode_sec`, `mean_episode_duration_sec`, `episodes` (`List[AFEpisode]`), and `entropy_score`.

### `repolaris.detection.trends.generate_hourly_trends(classified_beats, events=None, total_duration_sec=None, bin_size_sec=3600.0, af_episodes=None)`
Aggregates beat classifications, clinical events, and AF episodes into 1-hour Holter monitoring epochs.
- **Returns:** `HolterTrendReport` containing `total_duration_hours`, `overall_mean_hr`, `overall_min_hr`, `overall_max_hr`, `total_pvcs`, `total_pacs`, `total_couplets`, `total_vt_runs`, `total_pauses`, `max_pause_sec`, `total_af_sec`, `overall_af_burden_pct`, and `hourly_bins` (`List[HourlyTrendBin]`).

### `repolaris.detection.pipeline.analyze_ecg(raw_signal, fs=500.0, config=None, progress_callback=None, multi_lead_signals=None, lead_names=None)`
Master diagnostic pipeline orchestrating preprocessing, two-stage SQI, fiducials, AAMI classification, events diary, restitution, autonomic suite, AF burden, and hourly Holter trends.

---

## 5. Universal Ingestion Layer (`repolaris.io`)

### Format Sniffing & Loader Dispatcher (`ecg_loader.py`)
- `sniff_ecg_format(filepath)`: Inspects binary magic bytes (`DICM`, SCP Section 0, XML namespace, ISHNE tags) and extensions, returning one of `'dicom'`, `'hl7'`, `'scp'`, `'pecg'`, `'ishne'`, `'edf'`, `'wfdb'`, `'e3c'`, `'npy'`, or `'csv'`.
- `load_ecg_file(filepath, lead_name_or_index=0, progress_callback=None)`: Loads single calibrated mV lead.
- `load_ecg_dataset(filepath, progress_callback=None)`: Loads all synchronous channels, sampling frequency, and metadata dictionary.

### DICOM Waveform (`dicom_reader.py`)
- `read_dicom_waveform(filepath)`: Ingests 12-Lead (SOP `1.2.840.10008.5.1.4.1.1.9.1.1`) and Ambulatory (SOP `1.2.840.10008.5.1.4.1.1.9.1.2`) objects, converting Tag `(5400, 1010)` multiplexed 16-bit/8-bit integers to calibrated mV via sensitivity and baseline tags.
- `is_dicom_file(filepath)`: Verifies `b"DICM"` magic at offset 128.

### HL7 Annotated ECG XML (`hl7_reader.py`)
- `read_hl7_aecg(filepath)`: Parses FDA cardiotoxicity TQT XML trial files, mapping MDC_ECG codes, extracting increment sampling rates, and sanitizing European comma decimals (`0,005 mV`).
- `is_hl7_xml(filepath)`: Checks root XML tags and urn:hl7-org:v3 namespace.

### SCP-ECG Standard (`scp_reader.py`)
- `read_scp_ecg(filepath)`: Decodes CEN EN 1064 / ISO 13713 Section 0 pointer tables, Section 3 lead definitions, and Section 6 rhythm data. Raises `NotImplementedError` if Section 2 (Huffman) or Section 5 (Reference beat residual subtraction) is required.
- `is_scp_file(filepath)`: Inspects binary Section 0 header signatures.

### Legacy & Existing Readers
- `pecg_format.py`: `save_pecg` and `load_pecg` supporting Zstandard, Deflate, and raw `np.memmap`.
- `ishne_reader.py`: `read_ishne` and `write_ishne` for 1998 ISHNE 1.0 standard files.
- `wfdb_reader.py`: `read_wfdb` for PhysioNet Format 16 and Format 212 bit-packed records.
- `edf_reader.py`: `read_edf` for European Data Format (EDF / EDF+) files.
- `e3c_reader.py`: `read_e3c` for Fukuda Denshi Excorde 3C archives.

---

## 6. Advanced Repolarization & Autonomic Suite

- **Spatial Dispersion (`repolaris.detection.dispersion`)**: `calculate_qt_dispersion()` for inter-lead $QT_d$, $QTc_d$, and precordial $T_{pe,d}$ with dynamic lead quorum gating.
- **T-Wave Alternans (`repolaris.detection.twa`)**: `compute_spectral_twa()` (0.5 cpb FFT) and `compute_mma_twa()` (Modified Moving Average).
- **Heart Rate Turbulence (`repolaris.detection.hrt`)**: `compute_heart_rate_turbulence()` for Turbulence Onset ($TO$), Turbulence Slope ($TS$), and ISHNE risk categories (0, 1, 2).
- **Heart Rate Variability (`repolaris.detection.hrv`)**: `compute_comprehensive_hrv()`, `compute_time_domain_hrv()`, `compute_frequency_domain_hrv()`, and `compute_nonlinear_hrv()`.
- **QT-RR Hysteresis (`repolaris.detection.hysteresis`)**: `compute_effective_rr_exponential()`, `compute_effective_rr_linear()`, and `optimize_hysteresis_parameter()`.
- **10 Restitution Models (`repolaris.detection.qtrr`)**: `fit_all_qtrr_models()` evaluating linear, hyperbolic, parabolic-log, logarithmic, shifted-log, exponential, arctan, tanh, arcsinh, and arccosh curves with domain-positivity guards.
