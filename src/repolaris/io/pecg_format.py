"""
PyECG Custom (.pecg) Binary File Format with Zstandard and Deflate Support

Architecture:
- 12-Byte Binary Container Header:
    - Bytes 0-3: Magic bytes b"PECG"
    - Bytes 4-5: uint16 format version (default = 1)
    - Byte 6:    uint8 header encoding (0 = JSON UTF-8, 1 = CBOR)
    - Byte 7:    uint8 compression flag:
                   0 = COMPRESSION_NONE (Raw binary, supports zero-copy np.memmap)
                   1 = COMPRESSION_ZSTD (Zstandard - multi-GB/s decompression & high ratio)
                   2 = COMPRESSION_DEFLATE (Standard Deflate/Zlib - universal zero-dependency)
    - Bytes 8-11: uint32 metadata byte length (N)
- Metadata Block (N bytes):
    - De-identified patient demographics (age, race, sex, clinical indication, pacemaker)
    - Channel specifications (names, sampling rates, gains, baselines, units)
    - Physician annotations, calipers, and clinical event markers
- Waveform Block (from offset 12 + N to EOF):
    - If uncompressed: Contiguous 2D NumPy array (channels x samples) supporting np.memmap.
    - If zstd/deflate: Compressed byte stream for compact export and sharing.
"""

import struct
import json
import zlib
from pathlib import Path
import os
from typing import Optional, Dict, Any, Tuple, Callable
import numpy as np

try:
    import cbor2
    HAS_CBOR = True
except ImportError:
    HAS_CBOR = False

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

MAGIC = b"PECG"
CURRENT_VERSION = 1

# Header Encoding
ENCODING_JSON = 0
ENCODING_CBOR = 1

# Waveform Compression
COMPRESSION_NONE = 0
COMPRESSION_ZSTD = 1
COMPRESSION_DEFLATE = 2
COMPRESSION_ZLIB = 2  # Alias for DEFLATE

# Security & Sanitization Constants (DoS & Decompression Bomb Mitigation)
MAX_METADATA_BYTES = 10 * 1024 * 1024       # 10 MB maximum metadata header block
MAX_ALLOWABLE_CHANNELS = 64                 # Maximum plausible clinical/BSPM channels
MAX_ALLOWABLE_SAMPLES = 100_000_000         # Maximum ~27 hours at 1000 Hz or ~115 hours at 240 Hz
MAX_UNCOMPRESSED_PAYLOAD = 2 * 1024**3      # 2 GB maximum in-memory waveform payload


def save_pecg(
    filepath: str | Path,
    signals: np.ndarray,
    sampling_rate: float,
    lead_names: list[str],
    patient_info: Optional[Dict[str, Any]] = None,
    annotations: Optional[Dict[str, Any]] = None,
    events: Optional[list] = None,
    adc_gains: Optional[list[float]] = None,
    adc_baselines: Optional[list[int]] = None,
    use_cbor: bool = False,
    compression: str = "zstd",  # "zstd", "deflate", "zlib", or "none"
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    Saves a multi-channel ECG study to a single portable .pecg file.
    
    Parameters:
        compression: "zstd" (fastest & highest ratio), "deflate" / "zlib" (standard universal), or "none" (enables mmap).
    """
    filepath = Path(filepath)
    signals = np.asarray(signals)
    
    if signals.ndim == 1:
        signals = signals.reshape(1, -1)
        
    num_channels, num_samples = signals.shape
    
    # Ensure correct dtype for storage (int16 or float32)
    if np.issubdtype(signals.dtype, np.floating):
        dtype_str = "float32"
        storage_signals = signals.astype(np.float32)
    else:
        dtype_str = "int16"
        storage_signals = signals.astype(np.int16)

    if progress_callback:
        progress_callback(0.15, "Preparing de-identified patient demographics and channel specifications...")
    # 1. Prepare de-identified metadata dictionary (preserving age, race, sex, indication, pacemaker)
    raw_pm = patient_info.get("pacemaker") if patient_info else None
    if raw_pm is None:
        pm_status = "NO"
    elif isinstance(raw_pm, bool):
        pm_status = "YES" if raw_pm else "NO"
    else:
        pm_status = str(raw_pm).strip()

    patient_dict = {
        "age": patient_info.get("age") if patient_info else None,
        "race": patient_info.get("race") if patient_info else None,
        "sex": patient_info.get("sex", "UNKNOWN") if patient_info else "UNKNOWN",
        "indication": patient_info.get("indication", "") if patient_info else "",
        "pacemaker": pm_status
    }

    channels_spec = []
    for i in range(num_channels):
        name = lead_names[i] if i < len(lead_names) else f"Lead_{i+1}"
        gain = adc_gains[i] if (adc_gains and i < len(adc_gains)) else (200.0 if dtype_str == "int16" else 1.0)
        base = adc_baselines[i] if (adc_baselines and i < len(adc_baselines)) else 0
        channels_spec.append({
            "index": i,
            "name": name,
            "sampling_rate": float(sampling_rate),
            "adc_gain": float(gain),
            "adc_baseline": int(base),
            "unit": "mV",
            "data_type": dtype_str,
            "num_samples": int(num_samples)
        })

    metadata = {
        "format": "PECG",
        "version": CURRENT_VERSION,
        "recording": {
            "num_channels": int(num_channels),
            "num_samples": int(num_samples),
            "sampling_rate": float(sampling_rate),
            "duration_sec": float(num_samples / sampling_rate),
            "channels": channels_spec
        },
        "patient": patient_dict,
        "annotations": annotations or {},
        "events": events or []
    }

    # 2. Serialize metadata block (CBOR or JSON)
    if use_cbor and HAS_CBOR:
        meta_bytes = cbor2.dumps(metadata)
        enc_type = ENCODING_CBOR
    else:
        meta_bytes = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
        enc_type = ENCODING_JSON

    meta_length = len(meta_bytes)
    raw_waveform_bytes = storage_signals.tobytes()

    # 3. Compress waveform payload
    if progress_callback:
        progress_callback(0.40, "Compressing waveform payload...")
    comp_mode = compression.lower()
    if comp_mode == "zstd":
        if HAS_ZSTD:
            threads = min(os.cpu_count() or 1, 4)
            cctx = zstd.ZstdCompressor(level=3, threads=threads)
            waveform_payload = cctx.compress(raw_waveform_bytes)
            comp_flag = COMPRESSION_ZSTD
        else:
            # Graceful fallback to Deflate if zstandard isn't installed
            waveform_payload = zlib.compress(raw_waveform_bytes, level=6)
            comp_flag = COMPRESSION_DEFLATE
    elif comp_mode in ("deflate", "zlib"):
        waveform_payload = zlib.compress(raw_waveform_bytes, level=6)
        comp_flag = COMPRESSION_DEFLATE
    elif comp_mode in ("none", "raw", None):
        waveform_payload = raw_waveform_bytes
        comp_flag = COMPRESSION_NONE
    else:
        raise ValueError(f"Unknown compression format: '{compression}'. Choose 'zstd', 'deflate', or 'none'.")

    # 4. Pack 12-byte container header
    header = struct.pack(
        "<4sHBB I",
        MAGIC,
        CURRENT_VERSION,
        enc_type,
        comp_flag,
        meta_length
    )

    if progress_callback:
        progress_callback(0.80, f"Writing .pecg binary container to {filepath.name}...")
    with open(filepath, "wb") as f:
        f.write(header)
        f.write(meta_bytes)
        f.write(waveform_payload)

    if progress_callback:
        progress_callback(1.0, f"Successfully exported {filepath.name}")

    return str(filepath)


def load_pecg(filepath: str | Path, mmap: bool = False, progress_callback: Optional[Callable[[float, str], None]] = None) -> Tuple[Dict[str, Any], np.ndarray]:
    """
    Loads a .pecg study package with comprehensive security and sanity checks.
    
    Guards against:
    - Truncated or over-length binary container headers.
    - Massive metadata allocations (> 10 MB ceiling).
    - Unreasonable channel counts (> 64) and sample counts (> 100M).
    - Zstandard and Deflate decompression bombs (enforcing max_output_size).
    - Waveform buffer allocation overflow (> 2 GB ceiling).
    - Corrupt or dimension-mismatched payload byte lengths.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    file_size = filepath.stat().st_size
    if file_size < 12:
        raise ValueError(f"Corrupt .pecg container: File size ({file_size} B) is smaller than the 12-byte header.")

    if progress_callback:
        progress_callback(0.15, f"Reading container header for {filepath.name}...")
    with open(filepath, "rb") as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError(f"Invalid .pecg file: Expected magic b'PECG', got {magic}")
            
        version, enc_type, comp_flag, meta_length = struct.unpack("<HBB I", f.read(8))
        
        # 1. Validate metadata boundary & memory allocation ceiling
        if meta_length > MAX_METADATA_BYTES:
            raise ValueError(f"Security Alert: Metadata block size ({meta_length} B) exceeds the 10 MB safety ceiling.")
        if 12 + meta_length > file_size:
            raise ValueError(f"Corrupt .pecg container: Declared metadata offset (12 + {meta_length} B) extends beyond end-of-file ({file_size} B).")
            
        meta_bytes = f.read(meta_length)

    if progress_callback:
        progress_callback(0.40, "Decoding container metadata...")
    # 2. Decode and validate structured metadata
    try:
        if enc_type == ENCODING_CBOR:
            if not HAS_CBOR:
                raise ImportError("File uses CBOR header encoding, but 'cbor2' is not installed.")
            metadata = cbor2.loads(meta_bytes)
        else:
            metadata = json.loads(meta_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Corrupt or invalid metadata payload: {e}") from e

    rec_meta = metadata.get("recording")
    if not isinstance(rec_meta, dict):
        raise ValueError("Malformed .pecg metadata: Missing or invalid 'recording' object.")

    num_channels = rec_meta.get("num_channels", 0)
    num_samples = rec_meta.get("num_samples", 0)
    fs = rec_meta.get("sampling_rate", 0.0)

    # 3. Enforce physiological and sanity bounds
    if not (1 <= num_channels <= MAX_ALLOWABLE_CHANNELS):
        raise ValueError(f"Security Alert: Invalid channel count ({num_channels}). Must be between 1 and {MAX_ALLOWABLE_CHANNELS}.")
    if not (1 <= num_samples <= MAX_ALLOWABLE_SAMPLES):
        raise ValueError(f"Security Alert: Invalid sample count ({num_samples}). Must be between 1 and {MAX_ALLOWABLE_SAMPLES}.")
    if fs <= 0.0 or not np.isfinite(fs):
        raise ValueError(f"Invalid sampling rate: {fs} Hz.")

    channels_list = rec_meta.get("channels", [])
    dtype_str = channels_list[0].get("data_type", "float32") if channels_list else "float32"
    dtype = np.float32 if dtype_str == "float32" else np.int16
    itemsize = np.dtype(dtype).itemsize
    expected_bytes = num_channels * num_samples * itemsize

    if expected_bytes > MAX_UNCOMPRESSED_PAYLOAD:
        raise ValueError(f"Security Alert: Expected waveform allocation ({expected_bytes / 1e6:.1f} MB) exceeds the 2 GB safety ceiling.")

    data_offset = 12 + meta_length
    remaining_file_bytes = file_size - data_offset

    if progress_callback:
        progress_callback(0.70, "Decompressing and verifying waveform channels...")
    # 4. Decompress / Read Waveform with exact byte verification
    if comp_flag == COMPRESSION_NONE:
        if remaining_file_bytes < expected_bytes:
            raise ValueError(f"Corrupt .pecg file: Raw payload is truncated ({remaining_file_bytes} B available, expected {expected_bytes} B).")
        if mmap:
            signals = np.memmap(
                filepath,
                dtype=dtype,
                mode="r",
                offset=data_offset,
                shape=(num_channels, num_samples)
            )
        else:
            with open(filepath, "rb") as f:
                f.seek(data_offset)
                raw_bytes = f.read(expected_bytes)
            if len(raw_bytes) != expected_bytes:
                raise ValueError(f"Truncated read: Expected {expected_bytes} bytes, received {len(raw_bytes)}.")
            signals = np.frombuffer(raw_bytes, dtype=dtype).reshape((num_channels, num_samples)).copy()

    elif comp_flag == COMPRESSION_ZSTD:
        if not HAS_ZSTD:
            raise ImportError("File is compressed with Zstandard (zstd). Install it via: pip install zstandard")
        with open(filepath, "rb") as f:
            f.seek(data_offset)
            compressed_bytes = f.read()
        
        # Enforce exact expected decompressed output size to neutralize decompression bombs
        dctx = zstd.ZstdDecompressor()
        try:
            raw_bytes = dctx.decompress(compressed_bytes, max_output_size=expected_bytes)
        except Exception as e:
            raise ValueError(f"Zstandard decompression failed: {e}") from e

        if len(raw_bytes) != expected_bytes:
            raise ValueError(f"Decompression size mismatch: Expected {expected_bytes} bytes, got {len(raw_bytes)} bytes.")
        signals = np.frombuffer(raw_bytes, dtype=dtype).reshape((num_channels, num_samples)).copy()

    elif comp_flag in (COMPRESSION_DEFLATE, COMPRESSION_ZLIB):
        with open(filepath, "rb") as f:
            f.seek(data_offset)
            compressed_bytes = f.read()
        
        # Stream decompress with bounded byte ceiling to neutralize decompression bombs
        decompressor = zlib.decompressobj()
        try:
            raw_bytes = decompressor.decompress(compressed_bytes, expected_bytes + 1)
        except Exception as e:
            raise ValueError(f"Deflate decompression failed: {e}") from e

        if len(raw_bytes) != expected_bytes or decompressor.unconsumed_tail:
            raise ValueError(f"Security Alert: Decompressed payload does not match expected dimensions ({expected_bytes} B expected).")
        signals = np.frombuffer(raw_bytes, dtype=dtype).reshape((num_channels, num_samples)).copy()

    else:
        raise ValueError(f"Unsupported compression flag: {comp_flag}")

    if progress_callback:
        progress_callback(1.0, f"Successfully loaded {num_channels} leads from {filepath.name}")
    return metadata, signals