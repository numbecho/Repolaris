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
    - De-identified patient demographics (age, race, sex, clinical indication)
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
from typing import Optional, Dict, Any, Tuple
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
    compression: str = "zstd"  # "zstd", "deflate", "zlib", or "none"
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

    # 1. Prepare de-identified metadata dictionary (preserving age, race, sex)
    patient_dict = {
        "age": patient_info.get("age") if patient_info else None,
        "race": patient_info.get("race") if patient_info else None,
        "sex": patient_info.get("sex", "UNKNOWN") if patient_info else "UNKNOWN",
        "indication": patient_info.get("indication", "") if patient_info else ""
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
    comp_mode = compression.lower()
    if comp_mode == "zstd":
        if HAS_ZSTD:
            cctx = zstd.ZstdCompressor(level=3)
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

    with open(filepath, "wb") as f:
        f.write(header)
        f.write(meta_bytes)
        f.write(waveform_payload)

    return str(filepath)


def load_pecg(filepath: str | Path, mmap: bool = False) -> Tuple[Dict[str, Any], np.ndarray]:
    """
    Loads a .pecg study package.
    
    If mmap=True and the file is uncompressed, returns a zero-copy memory-mapped array.
    If the file is zstd/deflate compressed, transparently decompresses into memory.
    """
    filepath = Path(filepath)
    with open(filepath, "rb") as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError(f"Invalid .pecg file: Expected magic b'PECG', got {magic}")
            
        version, enc_type, comp_flag, meta_length = struct.unpack("<HBB I", f.read(8))
        meta_bytes = f.read(meta_length)

    # 1. Decode metadata
    if enc_type == ENCODING_CBOR:
        if not HAS_CBOR:
            raise ImportError("File uses CBOR header encoding, but 'cbor2' is not installed.")
        metadata = cbor2.loads(meta_bytes)
    else:
        metadata = json.loads(meta_bytes.decode("utf-8"))

    rec_meta = metadata["recording"]
    num_channels = rec_meta["num_channels"]
    num_samples = rec_meta["num_samples"]
    dtype_str = rec_meta["channels"][0].get("data_type", "float32")
    dtype = np.float32 if dtype_str == "float32" else np.int16

    data_offset = 12 + meta_length

    # 2. Decompress / Read Waveform
    if comp_flag == COMPRESSION_NONE:
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
                raw_bytes = f.read(num_channels * num_samples * dtype().itemsize)
                signals = np.frombuffer(raw_bytes, dtype=dtype).reshape((num_channels, num_samples)).copy()

    elif comp_flag == COMPRESSION_ZSTD:
        if not HAS_ZSTD:
            raise ImportError("File is compressed with Zstandard (zstd). Install it via: pip install zstandard")
        with open(filepath, "rb") as f:
            f.seek(data_offset)
            compressed_bytes = f.read()
        dctx = zstd.ZstdDecompressor()
        raw_bytes = dctx.decompress(compressed_bytes)
        signals = np.frombuffer(raw_bytes, dtype=dtype).reshape((num_channels, num_samples)).copy()

    elif comp_flag in (COMPRESSION_DEFLATE, COMPRESSION_ZLIB):
        with open(filepath, "rb") as f:
            f.seek(data_offset)
            compressed_bytes = f.read()
        raw_bytes = zlib.decompress(compressed_bytes)
        signals = np.frombuffer(raw_bytes, dtype=dtype).reshape((num_channels, num_samples)).copy()

    else:
        raise ValueError(f"Unsupported compression flag: {comp_flag}")

    return metadata, signals