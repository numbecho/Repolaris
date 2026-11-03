# Repolaris: Architecture & Complete API Reference (v0.6.1)

This document provides technical documentation for every module, class, and function call across the modernized Repolaris framework.

---

## 1. System Architecture Overview

Repolaris is organized into decoupled layers so that signal conditioning, electrophysiological delineation, and autonomic risk algorithms run independently from desktop GUI dependencies:

```
src/repolaris/
├── __init__.py               # Package metadata (__version__ = "0.6.1") and public exports
├── config.py                 # Clinical thresholds and signal processing parameters
├── i18n.py                   # Multi-language localization (EN, ES, FR, DE, PT)
├── api/
│   ├── __init__.py           # Unified in-process MVC service controllers
│   ├── study.py              # StudyAPI: dataset loading and synthetic rhythm generation
│   ├── analysis.py           # AnalysisAPI: pipeline, QTc, QTd, TWA, HRT, HRV, Hysteresis
│   └── export.py             # ExportAPI: de-identified .pecg study packaging
├── utils/
│   └── signal.py             # Realistic multi-component synthetic ECG generation
├── preprocessing/
│   ├── filter.py             # Butterworth bandpass and IIR notch filtering
│   └── baseline.py           # Two-stage median baseline wander suppression
├── detection/
│   ├── qrs.py                # Derivative-energy R-peak detector (Pan-Tompkins inspired)
│   ├── q_onset.py            # Backward inflection detection for ventricular depolarization
│   ├── t_end.py              # Hybrid steepest-descent tangent & threshold T-wave terminus
│   ├── pulse_metrics.py      # RR intervals, BPM, Bazett, Fridericia, Framingham, Hodges QTc
│   ├── qtvi.py               # Berger QT Variability Index & 4 Hz step-integration resampling
│   ├── qtrr.py               # 6 non-linear dynamic QT-RR restitution models
│   ├── sqi.py                # Spectral Signal Quality Indices (pSQI, basSQI, SNR)
│   ├── dispersion.py         # Multi-lead QT dispersion (QTd) & precordial Tpe dispersion
│   ├── twa.py                # Microvolt T-Wave Alternans (Spectral FFT & continuous MMA)
│   ├── hrt.py                # Heart Rate Turbulence (Turbulence Onset & Turbulence Slope)
│   ├── hrv.py                # Comprehensive HRV (Time, Welch PSD, Poincaré, SampEn, DFA)
│   ├── hysteresis.py         # Multi-beat QT-RR memory modeling (EW & LW lag kernels)
│   ├── classifier.py         # ANSI/AAMI EC57 beat classifier (N, V, S, F, Q) & sequences
│   ├── annotations.py        # AnnotationManager with immutable ISO 8601 audit logging
│   ├── events.py             # Clinical triage: severe QTc, pauses, tachycardia, PVCs
│   └── pipeline.py           # End-to-end headless analysis pipeline
├── io/
│   ├── ecg_loader.py         # Universal multi-format ingestion router
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
  - `lowcut` (*float*): Highpass cutoff frequency in Hz (default: `0.5`). Suppresses respiration wander.
  - `highcut` (*float*): Lowpass cutoff frequency in Hz (default: `45.0`). Eliminates electromyographic (EMG) noise.
  - `filter_order` (*int*): Butterworth filter order (default: `3`).
  - `notch_freq` (*float*): Powerline hum interference frequency in Hz (default: `50.0`).
  - `notch_quality` (*float*): Quality factor $Q$ for the notch filter (default: `30.0`).

### `DetectionConfig` (dataclass)
Holds clinical detection windows and refractory constraints.
- **Attributes:**
  - `refractory_period_ms` (*float*): Minimum physiological time between consecutive R-peaks (default: `250.0` ms, max 240 BPM).
  - `qrs_integration_window_ms` (*float*): Moving average integration window width (default: `120.0` ms).
  - `q_search_window_ms` (*float*): Search window preceding R-peak for Q-onset (default: `100.0` ms).
  - `t_search_window_ms` (*float*): Search window following R-peak for T-wave end (default: `450.0` ms).
  - `t_end_threshold_ratio` (*float*): Voltage threshold ratio along descending T slope (default: `0.15`).

### `ECGConfig` (dataclass)
Top-level configuration orchestrating sampling rate and sub-configs.
- **Attributes:**
  - `sampling_rate` (*float*): Lead sampling frequency in Hz (default: `500.0`).
  - `filter_cfg` (*FilterConfig*): Preprocessing configuration.
  - `detection_cfg` (*DetectionConfig*): Waveform detection thresholds.

---

## 3. Preprocessing (`repolaris.preprocessing`)

### `repolaris.preprocessing.filter.bandpass_filter(data, fs, cfg=FilterConfig())`
Applies a zero-phase bidirectional Butterworth bandpass filter (`scipy.signal.filtfilt`).

### `repolaris.preprocessing.filter.notch_filter(data, fs, freq=50.0, q=30.0)`
Eliminates sinusoidal 50 Hz or 60 Hz powerline hum via zero-phase IIR notch filtering.

### `repolaris.preprocessing.baseline.remove_baseline_wander(data, fs)`
Suppresses respiration and motion baseline wander via two-stage median filtering (200 ms QRS suppression window followed by 600 ms P/T wave suppression window).

---

## 4. Detection & Metrics (`repolaris.detection`)

### `repolaris.detection.qrs.detect_r_peaks(filtered_signal, fs, refractory_ms=250.0)`
Detects ventricular depolarization R-peaks using derivative squaring, moving-window integration, and local maximum refinement.

### `repolaris.detection.q_onset.detect_q_onset(signal, r_peak, fs, search_window_ms=100.0)`
Locates the electrical onset of ventricular depolarization prior to the R-peak.

### `repolaris.detection.t_end.detect_t_end(signal, r_peak, fs, search_window_ms=450.0, threshold_ratio=0.15, method="hybrid")`
Delineates the completion of ventricular repolarization (T-wave terminus) using hybrid steepest-descent tangent intersection with the isoelectric baseline and amplitude-threshold fallback.
- **Returns:** `tuple[int, int]`: `(t_peak_sample, t_end_sample)`.

### `repolaris.detection.pulse_metrics.compute_qtc(qt_sec, rr_sec)`
Calculates rate-corrected QT intervals using clinical formulas:
- `"bazett_ms"`: $QT_c = \frac{QT}{\sqrt{RR}}$ (in ms)
- `"fridericia_ms"`: $QT_c = \frac{QT}{\sqrt[3]{RR}}$ (in ms)
- `"framingham_ms"`: $QT_c = QT + 154 \times (1 - RR)$ (in ms)
- `"hodges_ms"`: $QT_c = QT + 1.75 \times (\text{HR} - 60)$ (in ms)

### `repolaris.detection.pipeline.analyze_ecg(raw_signal, fs=500.0, config=None, progress_callback=None, multi_lead_signals=None, lead_names=None)`
High-level master function running complete end-to-end analysis, returning `clean_signal`, `r_peaks`, `beats`, `classified_beats`, `ectopic_summary`, `annotations`, `events`, `summary`, `qtvi`, `qtrr`, `sqi`, `hrv`, `hrt`, `twa`, `hysteresis`, and `dispersion`.

---

## 5. Universal Ingestion & Storage (`repolaris.io`)

- `repolaris.io.ecg_loader.load_ecg_file(filepath, lead_name_or_index=0, progress_callback=None)`
- `repolaris.io.ecg_loader.load_ecg_dataset(filepath, progress_callback=None)`
- `repolaris.io.pecg_format.save_pecg(...)` & `load_pecg(filepath, mmap=False)`
- `repolaris.io.ishne_reader.read_ishne(filepath)` & `write_ishne(...)`
- `repolaris.io.e3c_reader.read_e3c(filepath)`
- `repolaris.io.wfdb_reader.read_wfdb(record_path_or_header)`
- `repolaris.io.edf_reader.read_edf(filepath)`

---

## 6. Advanced Repolarization & Autonomic Modules (v0.6.1)

### `repolaris.detection.dispersion.calculate_qt_dispersion(lead_signals, fs=500.0, lead_names=None, config=None, min_quorum=None)`
Quantifies spatial repolarization heterogeneity across synchronous multi-lead recordings.
- **Returns:** Dictionary containing `qt_dispersion_ms` ($QT_d$), `qtc_dispersion_ms` ($QTc_d$), `tpe_dispersion_ms` ($T_{pe,d}$), `precordial_tpe_dispersion_ms` (V1–V6 $T_{pe,d}$), `global_q_onsets`, `valid_leads`, `rejected_leads`, `quorum_met`, and `summary`. Returns `None` when channel quorum is not met.

### `repolaris.detection.twa.compute_spectral_twa(lead_signal, fs, r_peaks, beat_classes=None, window_beats=128)`
Quantifies microvolt T-wave alternans using sub-sample aligned FFT periodograms at $0.5\text{ cycles/beat}$.
- **Returns:** `v_alt_uv`, `k_score`, `is_positive` ($V_\text{alt} \ge 1.9\ \mu\text{V}$ and $k \ge 3.0$), `power_05_cpb`, `noise_mean`, `noise_std`, `ectopic_fraction`, and `beats_analyzed`.

### `repolaris.detection.twa.compute_mma_twa(lead_signal, fs, r_peaks, update_fraction=8)`
Continuously tracks T-wave alternans using recursive Modified Moving Average odd/even templates, returning `v_mma_series_uv`, `timestamps_sec`, `max_v_mma_uv`, `mean_v_mma_uv`, `odd_template_uv`, `even_template_uv`, and `risk_level`.

### `repolaris.detection.hrt.compute_heart_rate_turbulence(classified_beats, r_peaks, fs=500.0)`
Evaluates baroreflex-mediated autonomic response following solitary PVCs, returning `turbulence_onset` ($TO$), `turbulence_slope` ($TS$), ISHNE `category` (`0`, `1`, `2`), `valid_pvc_count`, `ensemble_tachogram_ms`, and `episodes`.

### `repolaris.detection.hrv`
- `compute_time_domain_hrv(nn_intervals_ms)`: `sdnn`, `rmssd`, `pnn50`, `mean_nn`, `median_nn`, `cv_percent`, `sdann`, `sdnn_index`.
- `compute_frequency_domain_hrv(nn_intervals_ms, fs_resample=4.0)`: `ulf_power`, `vlf_power`, `lf_power`, `hf_power`, `total_power`, `lf_hf_ratio`, `lf_nu`, `hf_nu`.
- `compute_nonlinear_hrv(nn_intervals_ms)`: Poincaré geometry (`sd1`, `sd2`, `sd1_sd2_ratio`, `ellipse_area_ms2`), Sample Entropy (`sampen`), and DFA exponents (`alpha_1`, `alpha_2`).
- `compute_comprehensive_hrv(nn_intervals_ms, fs_resample=4.0)`: Combined time, frequency, and non-linear dictionary.

### `repolaris.detection.hysteresis`
- `compute_effective_rr_exponential(rr_intervals_sec, lambda_param=0.04, window_beats=180)`
- `compute_effective_rr_linear(rr_intervals_sec, memory_beats=60)`
- `optimize_hysteresis_parameter(qt_intervals_sec, rr_intervals_sec, model_type="linear")`: Optimizes $\lambda^*$, $t_{90}$, $t_{1/2}$, and computes hysteresis-corrected Fridericia $QTc_\text{hyst}$.

---

## 7. Workstation Multi-Lead Sensing & Conditional Gating (`repolaris.app`)

### `repolaris.app.MainWindow._evaluate_channel_capabilities()`
Dynamic channel-sensing state machine in the workstation GUI:
- Evaluates `len(self.multi_lead_signals)` and per-channel signal quality.
- **Single-Lead Wearable Mode ($< 3$ channels):** Badges and disables `card_qtd` (`N/A`) while keeping single-lead autonomic metrics active.
- **Multi-Lead Holter Mode ($\ge 3$ channels):** Unlocks `card_qtd` and computes spatial $QT_d$ and $T_{pe,d}$ across all valid synchronous leads.
