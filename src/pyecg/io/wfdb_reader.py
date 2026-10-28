"""
PhysioNet WFDB (.hea + .dat) Reader Module
Supports:
- Format 16: 16-bit two's complement integer samples.
- Format 212: 12-bit bit-packed integer samples (pairs of samples packed in 3 bytes).
- Native fallback with zero required dependencies, plus optional 'wfdb' package support.
"""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple
import numpy as np

try:
    import wfdb
    HAS_WFDB = True
except ImportError:
    HAS_WFDB = False


@dataclass
class WFDBRecord:
    record_name: str
    sampling_rate: float
    num_signals: int
    num_samples: int
    lead_names: List[str]
    units: List[str]
    signals: np.ndarray  # Shape: (num_signals, num_samples) in physical mV


def _read_format_212(raw_bytes: bytes, num_signals: int, num_samples: int) -> np.ndarray:
    """Unpacks PhysioNet Format 212 (pairs of 12-bit integers packed into 3 consecutive bytes)."""
    # 3 bytes = 2 samples (Sample 0 and Sample 1)
    # Byte 0: low 8 bits of Sample 0
    # Byte 1: low 4 bits = high 4 bits of Sample 0; high 4 bits = high 4 bits of Sample 1
    # Byte 2: low 8 bits of Sample 1
    total_samples = num_signals * num_samples
    num_triplets = total_samples // 2
    raw = np.frombuffer(raw_bytes[: num_triplets * 3], dtype=np.uint8).reshape(-1, 3)

    b0 = raw[:, 0].astype(np.int32)
    b1 = raw[:, 1].astype(np.int32)
    b2 = raw[:, 2].astype(np.int32)

    s0 = b0 | ((b1 & 0x0F) << 8)
    s1 = b2 | ((b1 & 0xF0) << 4)

    # Sign extend 12-bit to 32-bit
    s0 = np.where(s0 >= 2048, s0 - 4096, s0)
    s1 = np.where(s1 >= 2048, s1 - 4096, s1)

    interleaved = np.empty(num_triplets * 2, dtype=np.int32)
    interleaved[0::2] = s0
    interleaved[1::2] = s1

    # Reshape to (num_samples, num_signals) then transpose to (num_signals, num_samples)
    actual_samples = len(interleaved) // num_signals
    return interleaved[: actual_samples * num_signals].reshape(actual_samples, num_signals).T


def read_wfdb(record_path_or_header: str | Path) -> WFDBRecord:
    """Reads a PhysioNet WFDB record from .hea header and companion .dat binary file."""
    path = Path(record_path_or_header)
    if path.suffix == ".dat":
        header_path = path.with_suffix(".hea")
        dat_path = path
    elif path.suffix == ".hea":
        header_path = path
        dat_path = path.with_suffix(".dat")
    else:
        header_path = Path(str(path) + ".hea")
        dat_path = Path(str(path) + ".dat")

    if not header_path.exists():
        raise FileNotFoundError(f"WFDB header not found: {header_path}")

    # Use wfdb library if available
    if HAS_WFDB:
        try:
            record = wfdb.rdrecord(str(header_path.with_suffix("")))
            signals = record.p_signal.T.astype(np.float32)  # (channels, samples)
            return WFDBRecord(
                record_name=record.record_name,
                sampling_rate=float(record.fs),
                num_signals=record.n_sig,
                num_samples=record.sig_len,
                lead_names=record.sig_name,
                units=record.units,
                signals=signals
            )
        except Exception:
            pass  # Fall back to native reader below

    # Pure-Python Native WFDB Parser
    with open(header_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not lines:
        raise ValueError(f"Empty WFDB header: {header_path}")

    # Parse Record Line (Line 0): [name] [num_signals] [sampling_rate] [num_samples]
    first_tokens = lines[0].split()
    record_name = first_tokens[0]
    num_signals = int(first_tokens[1])
    fs = float(first_tokens[2]) if len(first_tokens) > 2 else 250.0
    sig_len = int(first_tokens[3]) if len(first_tokens) > 3 else 0

    lead_names = []
    gains = []
    baselines = []
    units = []
    formats = []
    dat_filenames = []

    for i in range(1, num_signals + 1):
        if i >= len(lines):
            break
        tokens = lines[i].split()
        dat_filenames.append(tokens[0])
        fmt = int(tokens[1])
        formats.append(fmt)

        # Parse gain: e.g. "200.0(0)/mV" or "200.0"
        gain_str = tokens[2] if len(tokens) > 2 else "200.0"
        baseline = 0
        unit = "mV"
        
        if "(" in gain_str and ")" in gain_str:
            g_part, rest = gain_str.split("(")
            b_part = rest.split(")")[0]
            gain = float(g_part) if g_part else 200.0
            baseline = int(b_part) if b_part else 0
        else:
            gain = float(gain_str.split("/")[0]) if "/" in gain_str else float(gain_str)

        if "/" in gain_str:
            unit = gain_str.split("/")[-1]

        gains.append(gain if gain != 0 else 200.0)
        baselines.append(baseline)
        units.append(unit)

        lead_name = tokens[8] if len(tokens) > 8 else f"Lead_{i}"
        lead_names.append(lead_name)

    # Read binary .dat file
    if not dat_path.exists():
        # Check if header references a specific dat filename in the same folder
        candidate = header_path.parent / dat_filenames[0]
        if candidate.exists():
            dat_path = candidate
        else:
            raise FileNotFoundError(f"WFDB binary data file not found: {dat_path}")

    with open(dat_path, "rb") as f:
        raw_bytes = f.read()

    main_format = formats[0] if formats else 16
    if main_format == 16:
        # Format 16: standard 16-bit signed integers interleaved
        raw_arr = np.frombuffer(raw_bytes, dtype="<i2")
        actual_samples = len(raw_arr) // num_signals
        matrix = raw_arr[: actual_samples * num_signals].reshape(actual_samples, num_signals).T
    elif main_format == 212:
        matrix = _read_format_212(raw_bytes, num_signals, sig_len or (len(raw_bytes) * 2 // 3 // num_signals))
    else:
        raise ValueError(f"Unsupported WFDB format {main_format}. (Supported: Format 16 and Format 212)")

    # Convert to physical millivolts
    physical_signals = np.zeros_like(matrix, dtype=np.float32)
    for ch in range(matrix.shape[0]):
        g = gains[ch] if ch < len(gains) else 200.0
        b = baselines[ch] if ch < len(baselines) else 0
        physical_signals[ch] = (matrix[ch].astype(np.float32) - b) / g

    return WFDBRecord(
        record_name=record_name,
        sampling_rate=fs,
        num_signals=physical_signals.shape[0],
        num_samples=physical_signals.shape[1],
        lead_names=lead_names,
        units=units,
        signals=physical_signals
    )
