# File Formats and Universal Ingestion

A cornerstone of Repolaris is its **universal, zero-dependency ingestion engine** (`repolaris.io.ecg_loader`), capable of reading all major international clinical, hospital, and academic ECG formats.

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
| **Delimited Text / NumPy** | `.csv`, `.txt`, `.npy` | Community Sensors & Raw Dumps | Direct matrix ingestion with arbitrary delimiters. |

---

## 2. Format Sniffing Engine (`sniff_ecg_format`)

Rather than relying solely on file extensions, Repolaris inspects file headers and magic bytes to guarantee deterministic routing:

* **DICOM**: Inspects 128-byte preamble followed by `b"DICM"` signature at offset 128.
* **SCP-ECG**: Reads bytes 0–14 verifying CRC, file length, and Section 0 ID (`sec_id == 0`).
* **HL7 aECG**: Checks XML root elements for `<AnnotatedECG>` and the `urn:hl7-org:v3` namespace.
* **PECG**: Verifies the `b"PECG"` 4-byte magic signature at offset 0.
* **ISHNE**: Validates the 522-byte binary header with magic variable block length offsets.

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

## 3. DICOM Waveform (`.dcm`, `.dicom`)

Conforming to DICOM Part 3 Annex A.34 and C.10.9:
* Supports **12-Lead ECG Waveform Storage** (SOP Class `1.2.840.10008.5.1.4.1.1.9.1.1`) and **General ECG** (`1.2.840.10008.5.1.4.1.1.9.1.2`).
* Pure-Python native parser extracting multiplexed samples from Tag `(5400, 1010)` with automatic fallback to `pydicom` if installed.
* Calibrates raw ADC integers to physical millivolts using channel sensitivity and baseline tags:
  $$\text{Signal (mV)} = (\text{ADC} - \text{Baseline}) \times \text{Sensitivity}$$

```python
from repolaris.io.dicom_reader import read_dicom_waveform

rec = read_dicom_waveform("clinical_12lead.dcm")
print(f"Patient: {rec.patient_name} (ID: {rec.patient_id})")
print(f"Channels: {rec.num_channels} | Duration: {rec.num_samples / rec.sampling_rate:.1f}s")
lead_I = rec.signals[0]
```

---

## 4. HL7 Annotated ECG XML (`.xml`, `.aecg`)

Conforming to the ANSI/HL7 aECG standard utilized in FDA ICH E14 Thorough QT clinical trials:
* Maps IEEE 11073-10102 `MDC_ECG_LEAD_*` codes directly to standard clinical names (Lead I–III, aVR, aVL, aVF, V1–V6).
* Extracts sampling frequency from `<increment>` duration tags and voltage scale multipliers from `<scale>`.
* **Locale Normalization**: Automatically normalizes comma decimal formats (`0,005 mV`) common in European clinical trials to IEEE floating point.

```python
from repolaris.io.hl7_reader import read_hl7_aecg

rec = read_hl7_aecg("tqt_trial_subject.xml")
print(f"Leads: {rec.lead_names} | Sampling Rate: {rec.sampling_rate} Hz")
```

---

## 5. SCP-ECG Standard (`.scp`)

Conforming to European Standard CEN EN 1064:2005+A1:2007 and ISO 13713:
* Decodes Section 0 pointer tables, Section 3 lead configurations, and Section 6 difference-encoded rhythm waveforms.
* **Safety Guards**: Detects files requiring Section 2 Huffman decompression or Section 5 reference beat residual subtraction and raises a clean `NotImplementedError` to prevent bitstream corruption.

```python
from repolaris.io.scp_reader import read_scp_ecg

rec = read_scp_ecg("standard_ecg.scp")
print(f"Decoded {rec.num_leads} leads sampled at {rec.sampling_rate} Hz")
```

---

## 6. Portable Clinical ECG (`.pecg`)

Designed for de-identified peer consultation:
* **Demographic Preservation**: Anonymizes direct identifiers while preserving Age, Sex, Race, Pacemaker Status, and Clinical Indication.
* **Storage Modes**: Supports Zstandard (`zstd`), Deflate, or raw zero-copy `np.memmap`.

```python
from repolaris.io.pecg_format import save_pecg, load_pecg

save_pecg(
    filepath="patient_case.pecg",
    signals=lead_matrix,
    sampling_rate=500.0,
    lead_names=["Lead I", "Lead II", "V5"],
    patient_info={"age": 58, "sex": "Female", "indication": "Drug safety evaluation"},
    compression="zstd"
)
```
