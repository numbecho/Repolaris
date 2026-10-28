# File Formats and Universal Ingestion

A cornerstone of Repolaris is its **universal, zero-dependency ingestion engine** (`repolaris.io.ecg_loader`), capable of reading all major international clinical and academic ECG formats.

---

## 1. Supported Format Matrix

| Format | Extension | Origin / Hardware | Parser Details |
| :--- | :--- | :--- | :--- |
| **Portable Clinical ECG** | `.pecg` | Repolaris Native Exchange | 12-byte binary magic, CBOR/JSON metadata, Zstandard/Deflate compression, zero-copy `np.memmap`. |
| **ISHNE 1.0 Standard** | `.ecg` | Commercial Holters (Mortara, GE, Rozinn) | Full 1998 standard, 522-byte header, nV integer scaling, demographic parsing, demultiplexing. |
| **Excorde 3C** | `.e3c` | Fukuda Denshi Holter Monitors | In-memory ZIP extractor, 2-channel int16 binary stream, 25-byte QRS records (`<6IB`). |
| **European Data Format** | `.edf`, `.edf+` | Wearable Patches & Polysomnography | Official EDF/EDF+ specification, 256-byte header, per-channel physical dimension scaling. |
| **PhysioNet WFDB** | `.hea`, `.dat` | Clinical Research Benchmarks | Dual-file ASCII header parser, Format 16 bit-packed, Format 212 12-bit nibble packed. |
| **MATLAB Workspace** | `.mat` | Academic Algorithms & Dumps | Automatic dimension sniffing (channels x samples vs samples x channels), `save_mat_ecg`. |
| **Delimited Text / NumPy** | `.csv`, `.txt`, `.npy` | Community Sensors & Raw Dumps | Direct matrix ingestion with arbitrary delimiters. |

---

## 2. Portable Clinical ECG (`.pecg`) Specification

The `.pecg` format was designed specifically for Repolaris to enable secure, de-identified peer consultation between clinical cardiologists and academic electrophysiologists.

### Binary Layout
```
+----------------------------------------------------------------------------------------------------+
| Offset | Field                  | Type       | Description                                         |
+----------------------------------------------------------------------------------------------------+
| 0 - 3  | Magic Bytes            | char[4]    | b"PECG"                                             |
| 4 - 5  | Format Version         | uint16     | Format version (default: 1)                         |
| 6      | Header Encoding        | uint8      | 0 = UTF-8 JSON, 1 = CBOR                            |
| 7      | Compression Mode       | uint8      | 0 = None (Raw), 1 = Zstandard (zstd), 2 = Deflate   |
| 8 - 11 | Metadata Length (N)    | uint32     | Byte length of serialized metadata block            |
| 12     | Metadata Block         | N bytes    | Structured demographics, channel specs, annotations |
| 12 + N | Waveform Payload       | End of File| Compressed or contiguous 2D binary voltage array    |
+----------------------------------------------------------------------------------------------------+
```

### De-Identification Guarantee
When generating a `.pecg` file, direct identifiers (Patient Full Name, Hospital Medical Record Number, Exact Street Address) are automatically removed. Essential clinical variables required for electrophysiological interpretation are strictly preserved:
* **Patient Age** (integer years)
* **Sex / Gender** (`Male`, `Female`, `Unknown`)
* **Race / Ethnicity** (for QT reference ranges)
* **Clinical Indication** (e.g., *"Syncope under sotalol therapy"*)

### Python Usage Example
```python
from repolaris.io.pecg_format import save_pecg, load_pecg
import numpy as np

# Export an anonymized study package
save_pecg(
    filepath="patient_case_001.pecg",
    signals=lead_matrix,            # Shape: (num_leads, num_samples) in mV
    sampling_rate=500.0,
    lead_names=["Lead I", "Lead II", "V5"],
    patient_info={
        "age": 58,
        "sex": "Female",
        "race": "Caucasian",
        "indication": "Suspected drug-induced LQTS"
    },
    annotations={
        "physician_notes": [
            {"author": "Dr. S. Mercantete", "comment": "T-wave inversion observed on beat 84"}
        ]
    },
    compression="zstd"              # Options: "zstd", "deflate", or "none"
)

# Open instantly with zero RAM overhead via memory-mapping (if compression="none"):
metadata, signals = load_pecg("patient_case_001.pecg", mmap=False)
print("Patient Age:", metadata["patient"]["age"])
print("Lead Count: ", metadata["recording"]["num_channels"])
```

---

## 3. ISHNE 1.0 Standard (`.ecg`)

The International Society for Holter and Noninvasive Electrocardiology (ISHNE) standard format was established by Fabio Badilini in 1998. Repolaris provides a pure-Python parser and generator:

* **Fixed Header (512 bytes):** Extracts patient ID, sex, date of birth, recording date, start time, lead specifications, and sampling frequency.
* **Variable Block:** Decodes freeform physician clinical comments and diary markers.
* **ADC Calibration:** Multiplexed 16-bit signed integers are scaled to physical millivolts (mV) using the exact nanovolt-per-bit resolution ($nV/	ext{LSB}$) recorded per channel.

```python
from repolaris.io.ishne_reader import read_ishne

record = read_ishne("holter_24h.ecg")
print(f"Patient: {record.first_name} {record.last_name} ({record.sex})")
print(f"Sampling Rate: {record.sampling_rate} Hz | Total Leads: {record.num_leads}")
print(f"Duration: {record.duration_sec / 3600:.2f} hours")
lead_1_mv = record.signals[0]
```

---

## 4. Excorde 3C (`.e3c`)

Excorde 3C Holter devices (Fukuda Denshi) package digital Holter studies as proprietary archives containing separate raw waveform files and binary QRS detection headers. Repolaris reads `.e3c` archives directly in memory without creating temporary files on disk:
* Automatically decompresses the internal ZIP structure in RAM.
* Ingests 2-channel 16-bit binary streams.
* Decodes 25-byte binary QRS event descriptors (`struct.unpack('<6IB', ...)`).
