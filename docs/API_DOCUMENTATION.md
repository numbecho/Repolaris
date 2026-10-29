# Repolaris: Architecture & Complete API Reference

This document provides exhaustive technical documentation for every moduleclassand function call across the modernized Repolaris framework.

---

## 1. System Architecture Overview

PyECG is organized into decoupled layers to ensure that signal conditioning and clinical algorithms run independently from desktop GUI dependencies:

```
src/pyecg/
├── config.py                 # Clinical thresholds and signal processing parameters
├── utils/
│   └── signal.py             # Realistic multi-component synthetic ECG generation
├── preprocessing/
│   ├── filter.py             # Butterworth bandpass and IIR notch filtering
│   └── baseline.py           # Two-stage median baseline wander suppression
├── detection/
│   ├── qrs.py                # Derivative-energy R-peak detector (Pan-Tompkins inspired)
│   ├── q_onset.py            # Backward inflection detection for ventricular depolarization
│   ├── t_end.py              # Tangent / threshold T-wave terminus delineation
│   ├── pulse_metrics.py      # RR intervalsBPMBazettFridericiaFramingham QTc
│   ├── events.py             # Clinical triage: severe QTcpausestachycardiaPVCs
│   └── pipeline.py           # End-to-end headless analysis pipeline
├── io/
│   ├── ecg_loader.py         # Universal multi-format ingestion router
│   ├── pecg_format.py        # Single-file exchange container (CBOR/JSON + Zstd/Deflate)
│   ├── ishne_reader.py       # Official ISHNE 1.0 Holter (.ecg) binary parser & writer
│   ├── wfdb_reader.py        # PhysioNet WFDB (.hea + .dat) Format 16/212 parser
│   ├── edf_reader.py         # European Data Format (EDF / EDF+) parser
│   └── db.py                 # SQLite relational + JSON schema adapter
├── gui/
│   └── (app.py)              # PyQtGraph 60fps viewercalipersand Events Diary
├── cli.py                    # Command-line interface with formatted clinical tables
└── app.py                    # Desktop GUI entry point
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
  - `refractory_period_ms` (*float*): Minimum physiological time between consecutive R-peaks (default: `250.0` msmax 240 BPM).
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

### `repolaris.preprocessing.filter.bandpass_filter(datafscfg=FilterConfig())`
Applies a zero-phase bidirectional Butterworth bandpass filter.
- **Parameters:**
  - `data` (*np.ndarray*): 1D array of digitized raw voltage samples.
  - `fs` (*float*): Sampling frequency in Hz.
  - `cfg` (*FilterConfig*): Filter configuration instance.
- **Returns:**
  - `np.ndarray`: Filtered zero-phase signal with high and low frequency noise attenuated.
- **Notes:** Uses `scipy.signal.filtfilt` to prevent phase distortion and preserve fiducial peak alignment.

### `repolaris.preprocessing.filter.notch_filter(datafsfreq=50.0q=30.0)`
Eliminates sinusoidal 50 Hz or 60 Hz powerline hum.
- **Parameters:**
  - `data` (*np.ndarray*): 1D signal array.
  - `fs` (*float*): Sampling frequency in Hz.
  - `freq` (*float*): Notch center frequency (typically 50.0 or 60.0 Hz).
  - `q` (*float*): Filter quality factor.
- **Returns:**
  - `np.ndarray`: Hum-attenuated signal.

### `repolaris.preprocessing.baseline.remove_baseline_wander(datafs)`
Suppresses respiration and motion baseline wander via cascaded median filtering.
- **Parameters:**
  - `data` (*np.ndarray*): 1D signal array.
  - `fs` (*float*): Sampling rate in Hz.
- **Returns:**
  - `np.ndarray`: Baseline-corrected signal ($s_{\text{clean}} = s - \text{baseline}$).
- **Algorithm:**
  1. First stage: 200 ms median filter suppresses sharp QRS complexes.
  2. Second stage: 600 ms median filter suppresses wider P and T wavesleaving only slow baseline drift.
  3. The estimated drift is subtracted from the original trace.

---

## 4. Detection & Metrics (`repolaris.detection`)

### `repolaris.detection.qrs.detect_r_peaks(filtered_signalfsrefractory_ms=250.0)`
Detects ventricular depolarization R-peaks.
- **Parameters:**
  - `filtered_signal` (*np.ndarray*): Preprocessed 1D ECG array.
  - `fs` (*float*): Sampling frequency in Hz.
  - `refractory_ms` (*float*): Physiological blanking period in ms (default: `250.0`).
- **Returns:**
  - `np.ndarray`: Sorted 1D integer array of R-peak sample indices.
- **Algorithm:** Computes first derivativesquares values to accentuate steep QRS slopesconvolves with a 120 ms moving window integratorand applies adaptive percentile thresholding with local maximum refinement.

### `repolaris.detection.q_onset.detect_q_onset(signalr_peakfssearch_window_ms=100.0)`
Locates the electrical onset of ventricular depolarization prior to the R-peak.
- **Parameters:**
  - `signal` (*np.ndarray*): 1D clean ECG array.
  - `r_peak` (*int*): Sample index of the corresponding R-peak.
  - `fs` (*float*): Sampling frequency in Hz.
  - `search_window_ms` (*float*): Backward search duration in ms.
- **Returns:**
  - `int`: Sample index corresponding to Q-onset.

### `repolaris.detection.t_end.detect_t_end(signalr_peakfssearch_window_ms=450.0threshold_ratio=0.15)`
Delineates the completion of ventricular repolarization (T-wave terminus).
- **Parameters:**
  - `signal` (*np.ndarray*): 1D clean ECG array.
  - `r_peak` (*int*): Sample index of the beat's R-peak.
  - `fs` (*float*): Sampling frequency in Hz.
  - `search_window_ms` (*float*): Maximum window after R-peak to evaluate.
  - `threshold_ratio` (*float*): Cutoff ratio relative to post-T baseline.
- **Returns:**
  - `Tuple[intint]`: `(t_peak_samplet_end_sample)`.

### `repolaris.detection.pulse_metrics.compute_qtc(qt_secrr_sec)`
Calculates rate-corrected QT intervals using clinical formulas.
- **Parameters:**
  - `qt_sec` (*float*): Raw QT duration in seconds.
  - `rr_sec` (*float*): Preceding or current RR interval in seconds.
- **Returns:**
  - `dict`:
    - `"bazett_ms"`: $QT_c = \frac{QT}{\sqrt{RR}}$ (in ms)
    - `"fridericia_ms"`: $QT_c = \frac{QT}{\sqrt[3]{RR}}$ (in ms)
    - `"framingham_ms"`: $QT_c = QT + 154 \times (1 - RR)$ (in ms)

### `repolaris.detection.events.detect_clinical_events(beatsfs=500.0...)`
Scans a beat series and outputs classified clinical alerts.
- **Parameters:**
  - `beats` (*List[dict]*): Array of analyzed cardiac cycles from `analyze_ecg`.
  - `qtc_critical_thresh_ms` (*float*): Threshold for severe QTc alert (default: `500.0` ms).
  - `qtc_warning_thresh_ms` (*float*): Threshold for borderline QTc (default: `480.0` ms).
  - `pause_thresh_sec` (*float*): Duration threshold for sinus pauses (default: `2.0` s).
  - `tachy_thresh_bpm` (*float*): Heart rate for tachycardia (default: `120.0` BPM).
  - `brady_thresh_bpm` (*float*): Heart rate for bradycardia (default: `45.0` BPM).
- **Returns:**
  - `List[ECGEvent]`: Structured event list sorted chronologicallyeach containing `timestamp_sec``event_type``severity` (`CRITICAL``WARNING``INFO`)`metric_value``unit`and `description`.

### `repolaris.detection.pipeline.analyze_ecg(raw_signalfs=500.0config=None)`
High-level master function running complete end-to-end analysis.
- **Parameters:**
  - `raw_signal` (*np.ndarray*): 1D raw ECG lead array.
  - `fs` (*float*): Sampling frequency in Hz.
  - `config` (*Optional[ECGConfig]*): Custom configuration instance.
- **Returns:**
  - `dict`:
    - `"clean_signal"` (*np.ndarray*): Baseline-correctedfiltered voltage array.
    - `"r_peaks"` (*np.ndarray*): Integer indices of detected R-peaks.
    - `"beats"` (*List[dict]*): Detailed beat-by-beat fiducialsintervalsand QTc metrics.
    - `"events"` (*List[dict]*): Triage alerts ready for the GUI Event Diary.
    - `"summary"` (*dict*): Global stats (`mean_hr_bpm``mean_qt_ms``mean_qtc_bazett_ms``total_beats`).

---

## 5. Universal Ingestion & Storage (`repolaris.io`)

### `repolaris.io.ecg_loader.load_ecg_file(filepathlead_name_or_index=0)`
Universal loader that automatically sniffs file extensions and binary headers.
- **Supported Formats:** `.pecg``.ecg` (ISHNE)`.hea`/`.dat` (WFDB)`.edf` (EDF+)`.mat``.csv``.npy``.txt`.
- **Returns:** `np.ndarray`: 1D calibrated physical voltage trace in millivolts (mV).

### `repolaris.io.pecg_format.save_pecg(...)`
Saves an anonymized study package into a portable `.pecg` container.
- **Parameters:**
  - `filepath` (*str | Path*): Destination file path.
  - `signals` (*np.ndarray*): 2D array of lead waveforms `(channelssamples)`.
  - `sampling_rate` (*float*): Sampling frequency in Hz.
  - `lead_names` (*list[str]*): Names of recorded channels.
  - `patient_info` (*dict*): De-identified demographics (`age``race``sex``indication`).
  - `annotations` (*dict*): Caliper overrides and physician feedback comments.
  - `events` (*list*): Clinical events diary.
  - `compression` (*str*): `"zstd"` (Zstandard level 3)`"deflate"` (RFC 1951 / zlib)or `"none"` (uncompressed for zero-copy memory mapping).
- **Returns:** `str`: Path to the written file.

### `repolaris.io.pecg_format.load_pecg(filepathmmap=False)`
Loads a `.pecg` study package.
- **Parameters:**
  - `filepath` (*str | Path*): Path to the `.pecg` file.
  - `mmap` (*bool*): If `True` and the file is uncompressedreturns a zero-copy memory-mapped `np.memmap` array for instant multi-hour seeking with zero RAM consumption.
- **Returns:** `Tuple[dictnp.ndarray]`: `(metadata_dictsignals_matrix)`.

### `repolaris.io.ishne_reader.read_ishne(filepath)`
Parses official ISHNE 1.0 Holter `.ecg` binary files.
- **Parameters:** `filepath` (*str | Path*): Path to `.ecg` file.
- **Returns:** `ISHNERecord` containing patient demographics (with automatic age calculation from birth date)channel namessampling ratedurationand demultiplexed `signals` array calibrated to physical mV.

### `repolaris.io.ishne_reader.write_ishne(...)`
Creates a standards-compliant ISHNE 1.0 binary Holter file.

### `repolaris.io.wfdb_reader.read_wfdb(record_path_or_header)`
Parses PhysioNet WFDB records from `.hea` headers and `.dat` binary files.
- **Features:** Native zero-dependency support for Format 16 and Format 212 bit-packed samples.
- **Returns:** `WFDBRecord` with calibrated physical waveforms in mV.

### `repolaris.io.edf_reader.read_edf(filepath)`
Parses European Data Format (EDF / EDF+) files from wearable patches.
- **Features:** Decodes 256-byte main headersper-channel calibration formulasand data records.
- **Returns:** `EDFRecord` with unified physical voltage matrices in mV.

---

## 6. Graphical User Interface (`repolaris.gui`)

### `repolaris.gui.widgets.ECGPlotWidget`
PyQtGraph canvas optimized for long continuous recordings.
- **Components:**
  - `signal_curve`: Vectorized trace rendering.
  - `r_peak_scatter`: `pg.ScatterPlotItem` marking R-peaks.
  - `q_line` & `t_line`: Draggable dashed `pg.InfiniteLine` calipers for Q-onset and T-end.
  - `qt_region`: `pg.LinearRegionItem` highlighting the caliper interval window.
- **Key Methods:**
  - `display_signal(time_secvoltager_peak_indices)`: Updates plot data and resets viewport.
  - `set_calipers(q_time_sect_time_sec)`: Positions calipers on a specific beat.

### `repolaris.gui.main_window.MainWindow`
Main application window coordinating UI interactions.
- **Panels:**
  - **Main Canvas:** Center PyQtGraph waveform display.
  - **Control Box:** Open recordingrun demoexport `.pecg`.
  - **Live Caliper Readout:** Dynamic display of caliper QTBazett QTcand Fridericia QTc.
  - **Navigation Tabs:**
    - `🚨 Events Diary`: Lists triage alerts with click-to-seek functionality.
    - `📋 All Beats`: Cycle-by-cycle metrics table.
- **Key Methods:**
  - `_open_file_dialog()`: Prompts file picker supporting all formats.
  - `_export_pecg_dialog()`: Prompts for ageraceand notesand writes a de-identified `.pecg` package.
  - `_select_event(row)`: Pans viewport and positions calipers directly on the flagged episode.

---

## 7. Command Line Interface (`repolaris.cli`)

### `repolaris.cli.main()`
Dispatches command-line arguments:
- `pyecg demo --duration <sec> --fs <hz> --hr <bpm>`: Generates synthetic rhythmruns the full analysisand prints a formatted clinical report.
- `pyecg analyze <file> [--fs <hz>] [--lead <name_or_index>]`: Analyzes any supported file and outputs total beatsmean HRmean QTand rate-corrected QTc values.

---

## 8. Advanced Repolarization Lability & Quality Indices

### `repolaris.detection.qtvi.resample_berger(rr_cum_timesfs_resample=4.0)`
Resamples an unevenly spaced RR event sequence onto a uniform time grid using Berger's step-integration algorithm.
- **Reference:** Berger et al.IEEE TBME 33(9):900-9041986.
- **Parameters:**
  - `rr_cum_times` (*np.ndarray*): Cumulative occurrence times of R-peaks in seconds.
  - `fs_resample` (*float*): Target uniform sampling frequency in Hz (default: 4.0 Hz).
- **Returns:** `Tuple[np.ndarraynp.ndarray]`: Uniform time grid and instantaneous RR tachogram.

### `repolaris.detection.qtvi.compute_qtvi(rr_intervalsqt_intervals)`
Calculates Berger's classical QT Variability Index (QTVI).
- **Mathematical Formula:**
  $$\text{QTVI} = \log_{10} \left( \frac{\sigma^2_{QT}}{\sigma^2_{RR}} \cdot \left(\frac{\mu_{RR}}{\mu_{QT}}\right)^2 \right)$$
- **Clinical Interpretation:**
  - Normal range: $-1.6$ to $-1.0$.
  - Elevated ($> -0.5$): Suggests severe repolarization instability and elevated arrhythmogenic risk.
- **Parameters:**
  - `rr_intervals` (*np.ndarray*): 1D array of RR intervals.
  - `qt_intervals` (*np.ndarray*): 1D array of QT intervals.
- **Returns:** `float`: Logarithmic QTVI score.

### `repolaris.detection.qtvi.optimize_alpha(signaltarget_rref_rsegment_lensearch_steps=21)`
Computes optimal stretch scaling factor $\alpha$ for Berger template-matching QT estimation via iterative mean square error minimization.

### `repolaris.detection.qtrr.fit_qtrr_model(rr_intervalsqt_intervalsmodel='linear')`
Fits empirical QT-RR restitution curves across paired beat measurements.
- **Supported Models:** `'linear'``'hyperbolic'``'parabolic_log'``'logarithmic'``'exponential'``'arctan'`.
- **Returns:** Dictionary containing estimated `slope``intercept``pearson_r``p_value`and callable `predict_fn`.

### `repolaris.detection.sqi.evaluate_lead_quality(signalfs)`
Evaluates multi-metric signal quality indicators for an ECG lead channel.
- **Metrics Computed:**
  - `psqi`: QRS relative power index ($5\text{--}15\text{ Hz} / 5\text{--}40\text{ Hz}$).
  - `bassqi`: Baseline wander stability index ($1.0 - \text{Power}_{0-1\text{Hz}} / \text{Power}_{0-40\text{Hz}}$).
  - `snr_db`: Signal-to-noise ratio in decibels.
  - `verdict`: Diagnostic usability category (`'EXCELLENT'``'ACCEPTABLE'``'POOR'`).

---

## 9. Hardware & Format Ingestion Modules

### `repolaris.io.e3c_reader.read_e3c(filepathdefault_fs=250.0gain_scale=2.65e-3channels=2)`
Directly decompresses and parses proprietary Excorde 3C Holter archives (`.e3c`).
- **Data Extracted:**
  - `current.ECG`: 16-bit signed integer interleaved multi-channel waveforms.
  - `current.QRS`: 25-byte fixed-width beat annotation records (`qrson``qrsend``pattern``rpeak``rrprev``rrmean``bclass`).
- **Returns:** Dictionary containing calibrated signalssampling ratedurationand beat annotation arrays.

### `repolaris.io.ecg_loader.load_ecg_dataset(filepath)`
Universal dataset loader returning all channelssampling frequencyand clinical metadata dictionary regardless of source file format (`.pecg``.ecg``.e3c``.edf``.hea``.mat``.npy``.csv``.txt`).

---

## 10. Abnormal Beat Classification & Annotation Engine

### `repolaris.detection.classifier.BeatClass` (Enum)
Standard ANSI/AAMI EC57 diagnostic heartbeat category codes:
- `NORMAL` (`'N'`): Normal sinus rhythm and bundle branch block beats.
- `PVC` (`'V'`): Premature Ventricular Contractions (ventricular ectopic beats).
- `PAC` (`'S'`): Premature Atrial Contractions (supraventricular ectopic beats).
- `FUSION` (`'F'`): Fusion of normal and ventricular depolarization.
- `UNKNOWN` (`'Q'`): Pacedunclassifiableor severely distorted artifact beats.

### `repolaris.detection.classifier.RhythmPattern` (Enum)
Sequential ectopic rhythm coupling patterns:
- `BIGEMINY`: Alternating Normal - PVC sequences ($N - V - N - V$).
- `TRIGEMINY`: Alternating Normal - Normal - PVC sequences ($N - N - V - N - N - V$).
- `COUPLET`: Consecutive PVC pair ($V - V$).
- `VT_RUN`: Non-sustained Ventricular Tachycardia ($\ge 3$ consecutive PVCs).
- `NORMAL_SINUS`: Standard sinus rhythm sequence.
- `ISOLATED_ECTOPIC`: Standalone ectopic beat without repetitive coupling.

### `repolaris.detection.classifier.extract_beat_features(...)`
Extracts quantitative electrophysiological and dynamic timing metrics:
- Pre-RR ratio ($RR_i / RR_{\text{median}}$) to measure prematurity.
- Post-RR ratio ($RR_{i+1} / RR_{\text{median}}$) to detect compensatory pauses.
- Compensatory pause index ($(RR_i + RR_{i+1}) / (2 \cdot RR_{\text{median}})$).
- QRS complex duration in ms.
- Cross-correlation coefficient with the patient's dominant normal median template.
- Peak-to-peak voltage and signal energy.

### `repolaris.detection.classifier.classify_heartbeat(features...)`
Evaluates beat features against clinical AAMI EC57 decision boundariesreturning the `BeatClass`diagnostic confidence scoreand text rationale.

### `repolaris.detection.classifier.detect_rhythm_patterns(classified_beats)`
Scans a chronologically ordered series of beats to detect BigeminyTrigeminyCoupletsand Ventricular Tachycardia runs.

### `repolaris.detection.annotations.ECGAnnotation` (dataclass)
Single diagnostic event or beat annotation with review tracking:
- `sample` (*int*): Sample index on timeline.
- `timestamp_sec` (*float*): Timestamp in seconds.
- `label` (*str*): Primary AAMI code (`'N'``'V'``'S'``'F'``'Q'`).
- `sublabel` (*str*): Secondary clinical subtype (`'PVC'``'Bigeminy'``'Pause'`).
- `author` (*str*): `'AI_DETECTOR'` or reviewer name (e.g.`'Dr. Mercantete'`).
- `is_manual_override` (*bool*): `True` if manually modified or verified by a physician.
- `notes` (*str*): Free-form clinical observations or caliper justification.

### `repolaris.detection.annotations.AnnotationManager`
Central registry coordinating study annotations:
- `add_annotation(...)`: Inserts a new annotation.
- `override_beat_label(samplenew_labelreviewernotes)`: Updates an existing beat annotation with physician review metadata and audit history.
- `get_by_label(label)`: Filters annotations by AAMI class.
- `get_in_time_range(start_secend_sec)`: Queries annotations within a temporal viewport.
- `get_manual_overrides()`: Retrieves all physician-modified annotations.
- `summary()`: Computes total countsdistribution per AAMI categoryand override rates.
- `to_physionet_table()`: Exports annotations to standard tabular text compatible with PhysioNet `rdann`/`wrann`.
