# File Formats, Out-of-Core Streaming & Clinical PDF Reporting

A cornerstone of Repolaris is its **universal, zero-dependency ingestion and reporting engine** (`repolaris.io`), capable of reading all major international clinical, hospital, and academic ECG formats, streaming 24h–48h Holter recordings out-of-core via `np.memmap`, and generating printable 2-page clinical PDF reports.

---

## 1. Supported Format Matrix

| Format | Extension | Origin / Hardware | Parser Details |
| :--- | :--- | :--- | :--- |
| **DICOM Waveform** | `.dcm`, `.dicom` | Hospital PACS & 12-Lead Carts | SOP Classes `1.2.840.10008.5.1.4.1.1.9.1.1` and `9.1.2`, tag `(5400, 1010)` multiplexed extraction to calibrated physical mV. |
| **HL7 Annotated ECG** | `.xml`, `.aecg` | FDA Clinical Drug Trials (TQT) | ANSI/HL7 aECG XML standard, MDC_ECG lead mappings, and comma/period European decimal normalization. |
| **SCP-ECG Standard** | `.scp` | Hospital & Holter Devices | CEN EN 1064 / ISO 13713 Sections 0, 3, and 6 uncompressed rhythm decoding with safety guards. |
| **Portable Clinical ECG** | `.pecg` | Repolaris Native Exchange | 12-byte binary magic, CBOR/JSON metadata, Zstandard/Deflate compression, zero-copy `np.memmap`. |
| **ISHNE 1.0 Standard** | `.ecg` | Commercial Holters (Mortara, GE, Rozinn) | Full 1998 standard, 522-byte header, nV integer scaling, demographic parsing, demultiplexing. |
| **Excorde 3C** | `.e3c` | Fukuda Denshi Holter Monitors | In-memory ZIP extractor, 2-channel int16 binary stream, 25-byte QRS records (`<6IB`). |
| **European Data Format** | `.edf`, `.edf+` | Wearable Patches & Polysomnography | Official EDF/EDF+ specification, 256-byte header, per-channel physical dimension scaling. |
| **PhysioNet WFDB** | `.hea`, `.dat` | Clinical Research Benchmarks | Dual-file ASCII header parser, Format 16 bit-packed, Format 212 12-bit nibble packed. |
| **Delimited Text / NumPy** | `.csv`, `.txt`, `.npy` | Community Sensors & Raw Dumps | Direct matrix ingestion and memory-mapped streaming with arbitrary delimiters. |

---

## 2. Format Sniffing Engine (`sniff_ecg_format`)

Rather than relying solely on file extensions, Repolaris inspects file headers and magic bytes to guarantee deterministic routing:

* **DICOM**: Inspects 128-byte preamble followed by `b"DICM"` signature at offset 128.
* **SCP-ECG**: Reads bytes 0–14 verifying CRC, file length, and Section 0 ID (`sec_id == 0`).
* **HL7 aECG**: Checks XML root elements for `<AnnotatedECG>` and the `urn:hl7-org:v3` namespace.
* **PECG**: Verifies the `b"PECG"` 4-byte magic signature at offset 0.
* **ISHNE**: Validates the `ISHNE1.0` magic signature and variable header block offsets.

```python
from repolaris.io import sniff_ecg_format, load_ecg_dataset

# Automatically detect format
fmt = sniff_ecg_format("patient_ecg_file")
print(f"Detected format: {fmt}")

# Load all leads and clinical metadata
signals, fs, meta = load_ecg_dataset("patient_ecg_file")
print(f"Sampling frequency: {fs} Hz | Channels: {list(signals.keys())}")
```

---

## 3. Out-of-Core Holter Streaming (`SignalBuffer` & `stream_ecg_chunks`)

For continuous 24h–48h multi-lead Holter recordings ($> 1.8 \times 10^6$ samples per channel), `open_ecg_buffer()` and `stream_ecg_chunks()` back the signal array with an on-disk `np.memmap` cache so full-day recordings can be analyzed with bounded RAM usage:

```python
from repolaris.io import open_ecg_buffer, stream_ecg_chunks
from repolaris.detection.pipeline import analyze_ecg_stream

# 1. Zero-copy random-access lead slicing
buf = open_ecg_buffer("24h_holter.ecg", mmap_threshold_samples=1_800_000)
first_10s = buf.get_slice("Lead II", start_sample=0, end_sample=int(10 * buf.fs))

# 2. Full-study overlapping window streaming analysis (5-minute chunks, 5-second overlap)
results = analyze_ecg_stream("24h_holter.ecg", lead="Lead II", chunk_duration_sec=300.0, overlap_sec=5.0)
print(f"Total Beats: {results['summary']['total_beats']} | AF Burden: {results['af_report']['af_burden_pct']:.2f}%")
```

---

## 4. Printable 2-Page Clinical PDF Reports (`pdf_report.py`)

Repolaris generates vector clinical PDF reports (`generate_clinical_pdf_report`) with zero external browser or LaTeX dependencies:
* **Page 1:** Patient & Study Demographics, Executive Repolarization & Arrhythmia KPI Summary Table, a 10-second calibrated ECG disclosure strip ($25\text{ mm/s}$, $10\text{ mm/mV}$) with R-peak, Q-onset, and T-end markers, and the Clinical Events Diary.
* **Page 2:** Hourly Holter Distribution Table, Poincaré Lorentz plot ($RR_n$ vs $RR_{n+1}$), and QT-RR Restitution & Hysteresis curve.

```python
from repolaris.io import generate_clinical_pdf_report

generate_clinical_pdf_report(
    filepath="patient_holter_report.pdf",
    analysis_results=results,
    patient_metadata={"patient_id": "PT-104", "age": 64, "sex": "Female", "indication": "Syncope"},
    fs=buf.fs,
    lead_name="Lead II",
)
```

---

## 5. DICOM Waveform, HL7 aECG, SCP-ECG & Portable `.pecg`

### DICOM Waveform (`.dcm`, `.dicom`)
Conforming to DICOM Part 3 Annex A.34 and C.10.9, `read_dicom_waveform()` supports **12-Lead ECG** (`1.2.840.10008.5.1.4.1.1.9.1.1`) and **General ECG** (`1.2.840.10008.5.1.4.1.1.9.1.2`), calibrating raw ADC integers from Tag `(5400, 1010)` to physical millivolts:
$$\text{Signal (mV)} = (\text{ADC} - \text{Baseline}) \times \text{Sensitivity}$$

### HL7 Annotated ECG XML (`.xml`, `.aecg`)
Conforming to the ANSI/HL7 aECG standard utilized in FDA ICH E14 Thorough QT clinical trials, `read_hl7_aecg()` maps IEEE 11073-10102 `MDC_ECG_LEAD_*` codes to standard clinical names and normalizes European comma decimals (`0,005 mV`) to IEEE floats.

### SCP-ECG Standard (`.scp`)
Conforming to CEN EN 1064:2005+A1:2007 and ISO 13713, `read_scp_ecg()` decodes Section 0 pointer tables, Section 3 lead configurations, and Section 6 difference-encoded rhythm waveforms, while guarding against unsupported Section 2 Huffman or Section 5 residual files with a clean `NotImplementedError`.

### Portable Clinical ECG (`.pecg`)
Designed for de-identified peer consultation (`save_pecg`, `load_pecg`), preserving Age, Sex, Race, Pacemaker Status, and Clinical Indication with Zstandard (`zstd`), Deflate, or raw zero-copy `np.memmap` storage.
