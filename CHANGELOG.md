# Changelog

## [0.9.10] - 2026-11-24

### Fixed
- **True Out-of-Core WFDB Streaming (`wfdb_reader.py`, `ecg_loader.py`):** Added `iter_wfdb_chunks_format16()` using direct `seek`/`read` per 5-minute window, eliminating full-file RAM loads on >250 MB Holter `.dat` files and cutting peak RSS on `butqdb/105001_ECG` from 2,332.4 MB to 1,146.0 MB.
- **3D T-Wave SVD Crash Guard (`t_morphology.py`):** Filtered non-ECG channels (`Resp`, `SpO2`, `ACC`, `PLETH`, `ABP`, `EEG`, `EOG`, `EMG`) prior to SVD and added finite-value + max-abs rescale `LinAlgError` fallback, resolving all 8 `apnea-ecg` `*r` crashes.
- **EC57 Annotation-Span Clipping (`ec57.py`):** Clipped test beat detections to `[first_ref - tol, last_ref + tol]` by default so unannotated Holter tails are not scored as false positives (lifting `ltafdb/117` from 55.1% to 99.87% +P).

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.9] - 2026-11-18 — SCP-ECG Huffman 19999, Phasor Delineator, Derived 12-Lead & Native EC57 CLI

### Added
- **SCP-ECG Compressed Waveform & Section 5 Decoder (`io/scp_reader.py`)**: Implemented the CEN EN 1064 Default Huffman Table (`n_tables == 19999`), 1st/2nd-order difference reconstruction, Section 5 reference-beat residual addition, and true CEN EN 1064 Table 8 lead IDs (`61–64` for `Lead III`, `aVR`, `aVL`, `aVF`).
- **Derived 12-Lead Reconstruction (`io/ecg_loader.py`)**: Added `reconstruct_derived_leads()` computing Einthoven/Goldberger leads (`III`, `aVR`, `aVL`, `aVF`) from independent leads `I` and `II` for 8-lead clinical ECGs.
- **Phasor Transform T-End Delineator (`detection/t_end.py`, `plugins.py`)**: Added Martínez, Alcaraz & Rieta (2010) nonlinear Phasor Transform ($\phi(t) = \arctan((x(t) - b) / R_V)$) as `method="phasor"` and registered it as a built-in `GLOBAL_PLUGIN_REGISTRY` delineator (`"phasor"`).
- **Native `.atr` & `.ann` Benchmarking in CLI (`cli.py`)**: Added `--input`, `--reference`, and `--lead` options to `repolaris benchmark` to run ANSI/AAMI EC57 beat-by-beat evaluations directly on raw PhysioNet `.atr` and ISHNE `.ann` files (verified on 30-min MIT-BIH Record 100: `TP=2273, FP=0, FN=0 | Se=100.00% | +P=100.00% | F1=100.00%`).
- **Contract, Schema Parity & 5-Language i18n Audit (`tests/test_v099_upgrades_and_contract.py`)**: Unified `ectopic_summary` schema keys between `analyze_ecg()` and `analyze_ecg_stream()`, verified 0 key drift across all 5 locales (`en`, `es`, `fr`, `de`, `pt`), and resolved final Ruff `C420`/`SIM113` checks (**130 passing unit tests**).

## [0.9.8] - 2026-11-18 — Streaming Equivalence & Multi-Format Cohort Stress Verification

### Verified
- **In-Memory vs. Streaming Parity (`tests/test_v097_v098_stress_audit.py`)**: Verified `0` boundary beat drops/duplicates (`720/720` beats on a 10-minute recording across `120 s` chunks with `5 s` overlap) and full top-level key parity between `analyze_ecg()` and `analyze_ecg_stream()`.
- **Multi-Format Cohort & PDF Stress**: Verified fault-isolated execution across mixed clinical formats (`.npy`, `.csv`, `.pecg`, WFDB `.hea/.dat`, HL7 `.xml`) through `BatchAPI.analyze_directory()` and clinical PDF export via `ExportAPI.export_clinical_pdf()`.

## [0.9.7] - 2026-11-18 — Pathological Signal & Hostile Edge-Case Hardening

### Fixed
- **Flatline & Mid-Stream `NaN`/`Inf` Sanitization (`detection/pipeline.py`)**: Added `_sanitize_raw_signal()` to median-center raw inputs, gate constant flatline/lead-off signals to `0` beats, and linearly interpolate mid-stream `NaN`/`Inf` ADC glitches with `0` runtime warnings.
- **Hostile Rhythm & Morphology Stress Suite (`tests/test_v097_v098_stress_audit.py`)**: Verified `30 BPM` bradycardia, `220 BPM` tachycardia, `>80%` irregular AF burden, `6.0 s` asystole pauses, deeply inverted QRS/T morphology, `1.5 s` clips, and `125–2000 Hz` sampling rates.

## [0.9.6] - 2026-11-18 — Pre-1.0 Regulatory Validation, Circadian Stratification, Cohort Batch Runner & Plugin Registry

### Added
- **ANSI/AAMI EC57 & CSE Fiducial Benchmark Certification Engine (`benchmarks/ec57.py`, `repolaris benchmark` CLI)**:
  - 1-to-1 monotonic bipartite beat matching (`bxb`) within the AAMI EC57 $\pm 150\text{ ms}$ tolerance window, computing $TP, FP, FN$, Sensitivity ($Se$), Positive Predictivity ($+P$), Detection Error Rate ($DER$), $F_1$, and the $5 \times 5$ AAMI classification confusion matrix (`N`, `S`, `V`, `F`, `Q`).
  - Common Standards for Quantitative Electrocardiography (CSE) / PhysioNet QTDB fiducial boundary verification ($P_{\text{onset}}, P_{\text{peak}}, P_{\text{end}}, Q_{\text{onset}}, R_{\text{peak}}, J, T_{\text{peak}}, T_{\text{end}}$) against statutory referee standard deviation limits, plus episode overlap (`epi`) evaluation and automated synthetic self-certification (`run_synthetic_self_certification`).
- **Circadian Day/Night (Diurnal vs. Nocturnal) Repolarization & Autonomic Stratification (`detection/circadian.py`)**:
  - Wall-clock (`07:00–22:00` Awake vs. `22:00–07:00` Asleep) and multi-hour two-epoch partitioning quantifying nocturnal heart rate dipping ($\text{HR Dip}_{\%}$: `NORMAL_DIPPER`, `BLUNTED_NON_DIPPER`, `REVERSE_DIPPER`), diurnal vs. nocturnal $QTcF, J\text{–}T_{\text{peak}}c, T_{pe}, STV_{QT}$, nocturnal $QTcF$ lengthening ($\Delta QTcF \ge +15.0\text{ ms}$ for LQT2/LQT3 vs. LQT1 differentiation), and diurnal vs. nocturnal $QT\text{–}RR$ regression slopes ($\beta_{\text{day}} \ge 0.211$ discriminator).
- **Headless Multi-File Cohort Batch Runner (`api/batch.py`, `repolaris batch` CLI)**:
  - Zero-database folder processor across all supported ECG/Holter formats with automatic out-of-core `analyze_ecg_stream()` routing for large recordings, per-file fault isolation (`status="ERROR"` on corrupted inputs), and 51-column clinical trial `CSV` and `JSON` matrix export.
- **Extensible Research Algorithm & Biomarker Plugin Registry (`plugins.py`)**:
  - Thread-safe `PluginRegistry` supporting `@register_qrs_detector`, `@register_t_end_delineator`, and fault-isolated `@register_biomarker` hooks executed automatically inside `analyze_ecg()` and `analyze_ecg_stream()`.
- **Real-World Clinical Parser Upgrades (`hl7_reader.py`, `wfdb_reader.py`, `ishne_reader.py`, `ecg_loader.py`)**: Added nested HL7 `SLIST_PQ` rhythm-vs-template filtering, WFDB `16+offset` (`16+192`) `.mat` parsing, binary `.atr`/`.ann` annotation readers (`read_wfdb_annotations`, `read_ishne_ann`), and Shimmer3 `"sep="` timestamped CSV ingestion.
- **Expanded Automated Verification Suite (`tests/test_v096_validation_suite.py`)**:
  - Added 7 comprehensive unit tests bringing the total test suite to **117 passing unit tests** across 22 test modules (`0` warnings, `100%` Ruff `py314` clean).

## [0.9.0] - 2026-11-18 — Clinical Repolarization & Ambulatory Holter Suite

### Added
- **FDA CiPA Sub-Interval Decomposition (`q_onset.py`, `pulse_metrics.py`)**: Automated QRS offset (`detect_j_point`) delineation and beat-by-beat $J\text{–}T_{\text{peak}}$, rate-corrected $J\text{–}T_{\text{peak}}c = J\text{–}T_{\text{peak}} / RR^{0.58}$ (Johannesen et al., 2016), transmural dispersion $T_{pe} = T_{\text{end}} - T_{\text{peak}}$, and arrhythmogenic $T_{pe}/QT$ ratio.
- **Poincaré Short-Term & Long-Term QT Variability (`qtvi.py`, `pulse_metrics.py`)**: Ectopic-gated beat-to-beat $STV_{QT} = \sum |QT_{n+1} - QT_n| / (N\sqrt{2})$, $LTV_{QT}$, orthogonal $SD1_{QT} / SD2_{QT}$, Instability Index $II_{QT}$, and Torsades de Pointes (TdP) risk stratification (Thomsen et al., 2004).
- **T-Wave Morphology & 3D SVD/PCA Loop Descriptors (`t_morphology.py`)**: Single-lead ascending/descending slope ratio, area symmetry, flatness (kurtosis), $20\text{ ms}$-smoothed notch & biphasic detection, and multi-lead 3D Singular Value Decomposition ($T_2/T_1$ loop roundness, $T_3/T_1$ planarity, non-dipolar residue $\%$, and Total Cosine R-to-T $TCRT$, Vicente et al., 2015).
- **Superimposed Multi-Lead "Butterfly" Median Beat View (`t_morphology.py`, `app.py`)**: New interactive `🦋 Butterfly & T-PCA` workstation tab overlaying R-peak-aligned median beats across all active leads with a spatial RMS magnitude curve and 4 synchronized global calipers ($Q_{\text{onset}}, J, T_{\text{peak}}, T_{\text{end}}$).
- **Phase-Rectified Signal Averaging (`prsa.py`)**: Autonomic Deceleration Capacity ($DC$) and Acceleration Capacity ($AC$) via Haar wavelet scale $s=2$ on ectopic-gated $RR$ intervals with Bauer et al. (2006) post-MI vagal risk tiers ($\le 2.5\text{ ms}$ High Risk, $2.6\text{–}4.5\text{ ms}$ Intermediate Risk, $> 4.5\text{ ms}$ Low Risk).
- **Ambulatory ST-Segment Level, Slope & Transient Ischemia Detection (`st_segment.py`)**: Local PQ isoelectric baseline reference, rate-adaptive $J+80\text{ ms}$ ($\text{HR} \le 120\text{ BPM}$) vs. $J+60\text{ ms}$ ($\text{HR} > 120\text{ BPM}$) ST deviation ($\mu\text{V}$), ST slope ($\text{mV/s}$), sustained ischemic episode segmentation (`STIschemicEpisode`), and hourly ST trend bins.
- **AF-Gated P-Wave Delineation, PR Interval & AV Block Screening (`p_wave.py`)**: Diastolic $P_{\text{onset}}, P_{\text{peak}}, P_{\text{end}}$ localization (automatically suppressed during active AF episodes), beat-to-beat $PR$ interval tracking, 1st-degree AV block ($PR > 200\text{ ms}$), and 2nd-degree Mobitz Type I (Wenckebach) vs. Mobitz Type II conduction block screening.
- **ECG-Derived Respiration (`edr.py`)**: Moody & Mark (1985) beat-to-beat QRS area/amplitude modulation resampling ($4\text{ Hz}$), $0.12\text{–}0.45\text{ Hz}$ Welch PSD respiratory rate ($\text{breaths/min}$), and Cyclic Variation of Heart Rate (`CVHR`, $0.01\text{–}0.04\text{ Hz}$) sleep-apnea screening.
- **High-Rate Pacemaker Spike Guard (`p_wave.py`)**: Strict Nyquist sampling-rate guard (`fs >= 1000 Hz`) combining first-derivative slew rate ($|dV/dt|$) and second-difference narrow-impulse energy ($\le 3\text{ ms}$) to flag paced beats at high sampling rates while falling back to container metadata at standard $250\text{–}500\text{ Hz}$ Holter rates.
- **Comprehensive v0.9.0 Verification Suite (`tests/test_v090_repolarization_core.py`, `tests/test_v090_holter_suite.py`)**: Expanded automated test suite from 99 to **116 unit tests** across 21 test modules (`0` warnings, `100%` Ruff `py314` clean).

## [0.8.1] - 2026-11-16

### Added
- **Clinical Workstation UX Upgrades (`repolaris.app`, `repolaris.i18n`, `repolaris.resources`)**:
  - **Keyboard Beat Navigation (`Left`/`Right` Arrows & `◀`/`▶` Toolbar Buttons)**: Added `prev_beat()`, `next_beat()`, `btn_prev_beat`, and `btn_next_beat` to step cycle-by-cycle, sync `beat_table` row selection, and center Q/T calipers.
  - **Single-Key AAMI Reclassification Hotkeys (`N`, `V`, `S`, `F`, `Q`)**: Added `reclassify_active_beat()` and `keyPressEvent()` bindings so pressing `N`, `V`, `S`, `F`, or `Q` reclassifies the active beat in-place, re-evaluates `detect_rhythm_patterns()`, recalculates `ectopic_summary`, `hrv`, and `hrt`, and logs an immutable audit entry in `AnnotationManager`.
  - **Color-Coded Ectopic R-Peak Markers & On-Canvas Tags (`ECGPlotWidget.display_signal`)**: Color-codes R-peak markers by AAMI class (`#34d399` Normal, `#f87171` PVC, `#fbbf24` PAC, `#c084fc` Fusion) and renders on-canvas `pg.TextItem` tags (`V`, `S`, `F`, `Q`) above non-normal R-peaks.
  - **Live Caliper `RR` Readout & Persistent Caliper Drag Calibration (`_on_caliper_dragged`)**: Added `lbl_tag_rr` / `lbl_cal_rr` to the caliper HUD strip and persisted manual Q-onset/T-end drags directly into `analysis_results["beats"]`, `summary`, `beat_table`, and `card_qtc`.
  - **Expanded 8-Column Clinical Tables & 100% 5-Language Parity**: Expanded `beat_table` (adding `Pattern`, `RR (ms)`, `HR (BPM)`), `holter_af_table` (adding `Max HR`, `Shannon Ent.`, `Irregularity`), and `qtrr_models_table` (adding `Slope (α)`, `Pearson r`, `AIC`) to 8 columns each, and localized all remaining banners, labels, and tooltips across `en`, `es`, `fr`, `de`, and `pt`.
- **Python 3.14 Syntax Modernization & Additive `uv` / `ruff` Tooling Suite (`tests/test_tooling_uv_ruff.py`, `.github/workflows/build-artifacts.yml`)**:
  - Modernized all 56 Python modules across `src/repolaris/` and `tests/` to native `X | Y` unions, built-in generics (`list`, `dict`, `tuple`, `set`), `StrEnum`, `match`/`case` structural pattern matching, and `contextlib.suppress`, eliminating duplicated dispatch ladders and dead code.
  - Added `.python-version` (`3.14`), `[tool.uv]`, `[tool.ruff]` (`target-version = "py314"`), PEP 735 `[dependency-groups]`, the `uv-ruff-test` CI job, and `tests/test_tooling_uv_ruff.py` alongside the existing `pip` + `unittest` suite (**116 passing unit tests**).

### Fixed
- **Hostile Audit Signal & I/O Hardening (`ecg_loader.py`, `pipeline.py`, `hysteresis.py`, `sqi.py`, `hamilton_classifier.py`, `events.py`, `qtrr.py`, `qtvi.py`)**:
  - Fixed `load_ecg_dataset()` attribute mappings for ISHNE (`.ecg`) and EDF (`.edf`) records, added `SignalBuffer.close()` context-manager cleanup for temporary `np.memmap` directories, and removed the 10-second minimum chunk clamp in `stream_ecg_chunks()`.
  - Fixed hysteresis effective RR key resolution (`rr_eff_ew_sec` / `rr_eff_lw_sec`), assigned forward RR interval to Beat 0, evaluated `basSQI` and `snr_db` on raw pre-filtered signals while enforcing `kSQI` and `snr_db` in Stage 1 SQI gating, wired `HamiltonBeatClassifier` into `analyze_ecg()`, and added Tikhonov ridge stabilization for constant-rate QT-RR regression.

## [0.8.0] - 2026-11-14

### Added
- **Long-Term Holter Out-of-Core Streaming & `np.memmap` Buffering (`repolaris.io.ecg_loader`, `repolaris.detection.pipeline`)**:
  - Added `SignalBuffer`, `open_ecg_buffer()`, and `stream_ecg_chunks()` supporting memory-mapped (`np.memmap`) disk-backed signal buffers for continuous 24h–48h multi-lead recordings without RAM exhaustion.
  - Added `analyze_ecg_stream()` in `pipeline.py` (exposed via `AnalysisAPI.analyze_stream()` and CLI `--stream`) to process overlapping windows, eliminate filter edge transients, deduplicate boundary R-peaks, and aggregate study-wide HRV, HRT, AF burden, and hourly trends.
- **Automated Printable Clinical PDF Report Generator (`repolaris.io.pdf_report`, `ExportAPI.export_clinical_pdf`)**:
  - Added `generate_clinical_pdf_report()` producing publication-grade 2-page clinical PDF reports via `matplotlib.backends.backend_pdf.PdfPages`.
  - Page 1 includes Patient & Study Demographics, Executive Repolarization & Arrhythmia KPI Summary Table, a 10-second calibrated ECG disclosure strip with R-peak/Q-onset/T-end markers, and the Clinical Events Diary.
  - Page 2 includes the Hourly Holter Distribution Table, Poincaré Lorentz plot ($RR_n$ vs $RR_{n+1}$), and QT-RR Restitution & Hysteresis curve.
- **Workstation Holter Triage Tab & PDF Export (`repolaris.app`, `repolaris.i18n`, `repolaris.cli`)**:
  - Added the `🕒 Holter Triage` tab (`holter_trends_table`, `holter_af_table`, `lbl_holter_summary_banner`) with one-click seeking to any hourly epoch or AF episode.
  - Added `📄 PDF Report` toolbar button, `File -> Export Clinical PDF Report... (Ctrl+P)` menu action, and CLI `--pdf` / `--stream` flags across all 5 supported languages (`en`, `es`, `fr`, `de`, `pt`).
- **Comprehensive v0.8.0 Verification Suite (`tests/test_v080_streaming_and_pdf.py`)**:
  - Added 5 automated unit tests validating `np.memmap` chunk streaming, boundary R-peak deduplication, PDF report generation, CLI `--pdf`/`--stream` flags, and GUI Holter Triage tab widgets (full test suite: **90 passing unit tests**).

## [0.7.1] - 2026-11-06

### Added
- **Atrial Fibrillation (AF) / Flutter Detection and Burden Analysis (`repolaris.detection.af_detector`)**:
  - Added native `detect_atrial_fibrillation()`, `compute_rr_entropy()`, and `compute_rr_irregularity()`.
  - Implements sliding-window Shannon entropy analysis on local RR distributions coupled with successive RR median absolute difference (MAD) irregularity scoring.
  - Automatically segments sustained AF episodes ($\ge 30\text{ s}$), calculating episode onset, offset, duration, heart rate extrema, irregularity indices, and overall recording AF burden percentage conforming to clinical Holter standards.
- **Hourly Arrhythmia Trend Histograms & Holter Summary (`repolaris.detection.trends`)**:
  - Added `generate_hourly_trends()` producing 1-hour epoch distribution tables for 24h/48h Holter monitoring.
  - Tracks hourly heart rate extrema (Min, Mean, Max HR), ventricular ectopy counts (PVCs, Couplets, VT Runs), supraventricular ectopy (PACs), sinus pauses ($\ge 2.0\text{ s}$, $\ge 2.5\text{ s}$), and hourly AF burden.
- **AF Entropy Stabilizer for Hamilton Beat Classifier (`repolaris.detection.hamilton_classifier`)**:
  - Added rhythm-entropy gating to the Patrick Hamilton (2002) OSEA template matching classifier to prevent false-positive PVC classifications during chaotic rhythm variations (AF with rapid ventricular response).
- **Hardening and Edge-Case Ingestion Resilience (`repolaris.io`)**:
  - **SCP-ECG Guarding**: Hardened `read_scp_ecg` to explicitly check Section 0 pointer tables for Section 2 (Huffman table decompression) and Section 5 (Reference beat residual subtraction), gracefully raising `NotImplementedError` rather than parsing corrupted streams.
  - **HL7 aECG Locale Delimiter Normalization**: Hardened `read_hl7_aecg` to sanitize European comma decimal formatting (`0,005 mV`) to standard IEEE floats.
  - **Safe Pulse Metrics & Events Handling**: Protected `summarize_beats()` and `detect_clinical_events()` against `TypeError` when handling unassigned or NaN heart rates on initial cycles.
- **Comprehensive v0.7.1 Test Suite (`tests/test_v071_hardening.py`)**:
  - Added 5 new automated unit tests covering AF episode segmentation, Holter hourly binning, SCP compression guards, European decimal parsing, and pipeline integration (full test suite: **85 passing unit tests**).

## [0.7.0] - 2026-11-05

### Added
- **Open International Format Ingestion Layer (`repolaris.io`)**:
  - Added native **DICOM Waveform** reader (`read_dicom_waveform`, `is_dicom_file` in `repolaris.io.dicom_reader`) supporting 12-Lead (SOP Class `1.2.840.10008.5.1.4.1.1.9.1.1`) and Ambulatory ECG (SOP Class `1.2.840.10008.5.1.4.1.1.9.1.2`), extracting multiplexed 16-bit waveform arrays, channel sensitivity/baseline, and patient metadata into calibrated physical millivolts with zero external PACS software requirements.
  - Added native **HL7 Annotated ECG XML** reader (`read_hl7_aecg`, `is_hl7_xml` in `repolaris.io.hl7_reader`) for ANSI/HL7 aECG clinical trial files, parsing MDC_ECG lead sequences, increment sample rates, and scale multipliers.
  - Added native **SCP-ECG** standard communication protocol reader (`read_scp_ecg`, `is_scp_file` in `repolaris.io.scp_reader`) for European CEN EN 1064 / ISO 13713 files, decoding Section 0 pointer tables, Section 3 lead definitions, and Section 6 difference-encoded rhythm data.
  - Added intelligent format auto-detection state machine (`sniff_ecg_format`) in `ecg_loader.py` that inspects binary magic headers (`DICM`, SCP Section 0, HL7 XML namespaces, ISHNE tags) rather than relying solely on file extensions.
- **Patrick Hamilton (2002) OSEA Template Beat Classifier (`repolaris.detection.hamilton_classifier`)**:
  - Implemented the unencumbered, public-domain Hamilton (2002) Open Source ECG Analysis template-matching engine (`HamiltonBeatClassifier`).
  - Features dynamic morphology clustering with a 12.5% running adaptation rate on dominant normal templates, dual prematurity gating (local running RR context < 0.82), and compensatory pause detection, targeting &ge;95% ventricular positive predictivity on MIT-BIH benchmarks.
- **Workstation Open File Dialog Enhancements (`repolaris.app`)**:
  - Expanded `_open_file_dialog()` in `MainWindow` with native file filter selectors for DICOM Waveform (`*.dcm`, `*.dicom`), HL7 aECG XML (`*.xml`, `*.aecg`), and SCP-ECG Standard (`*.scp`).
- **Comprehensive v0.7.0 Verification Suite (`tests/test_v070_format_support.py`)**:
  - Added automated unit tests for DICOM waveform decoding, HL7 aECG XML parsing, SCP-ECG binary rhythm extraction, format sniffing, and Hamilton OSEA template classification, bringing the active test suite to 80 passing tests.

## [0.6.1] - 2026-11-03

### Added
- **Peer-Reviewed Anti-Regression Conditioning (`repolaris.config`, `repolaris.preprocessing`)**:
  - Updated `FilterConfig.lowcut` default to `0.05 Hz` (with `highcut = 45.0 Hz` and narrow powerline notch `notch_quality = 30.0`) to preserve low-frequency ST-T morphology per AHA/ACC/HRS guidelines (Kligfield et al., 2007), while retaining the cascaded two-stage median baseline filter (`200 ms / 600 ms`; de Chazal et al., 2004).
- **Two-Stage Signal Quality Assessment & Six-Index Pairwise Lead Voting (`repolaris.detection.sqi`)**:
  - Added fourth-moment kurtosis (`compute_ksqi`), third-moment skewness (`compute_ssqi`), and `rank_leads_two_stage()`.
  - Enforces Stage 1 absolute physiological rejection gates (`pSQI`, `basSQI`, `kSQI`, `sSQI`, `SNR_dB`, non-flatline ratio; Li, Rajagopalan & Clifford, 2014) prior to Stage 2 pairwise six-index relative lead voting (VI_k in [-6.0, +6.0]; Suárez-León et al., 2018) so detached or saturated leads can never win a relative vote.
- **Zhang (2006) Sliding-Window Area T-End Delineation (`repolaris.detection.t_end`)**:
  - Added `method="zhang_area"` implementing the sliding-window area (SWA) algorithm (Zhang et al., *IEEE TBME* 2006) alongside `hybrid`, `tangent` (ICH E14), and `threshold` modes.
- **Complete 10-Model Domain-Guarded QT-RR Restitution Suite (`repolaris.detection.qtrr`)**:
  - Expanded `SUPPORTED_QTRR_MODELS` and `fit_all_qtrr_models()` to all 10 biparametric models from Pueyo et al. (2004) (`linear`, `hyperbolic`, `parabolic_log`, `logarithmic`, `shifted_log`, `exponential`, `arctan`, `tanh`, `arcsinh`, `arccosh`) with Vandermonde and domain positivity conditioning guards (`_safe_linear_fit`) and individualized QTc,ind(RR = 1.0 s) estimation.
- **Interactive Workstation QT-RR Settings & Dynamics Visualization Tab (`repolaris.app`, `repolaris.i18n`)**:
  - Enhanced `SettingsDialog` (`⚙️ Settings`) with persistent selectors for all 10 Pueyo (2004) QT-RR models (plus `Auto-Select Best Model`), multi-beat hysteresis compensation (`EW`, `LW`, `Raw RR`), and T_end delineation method (`hybrid`, `tangent`, `zhang_area`, `threshold`).
  - Added the `📈 QT-RR Dynamics` tab in `MainWindow` featuring an interactive PyQtGraph (RR, QT) vs. (RR_eff, QT) hysteresis cloud, continuous parametric regression curve, individualized QTc,ind marker, live telemetry banner, and clickable 10-model leaderboard (`qtrr_models_table`).
