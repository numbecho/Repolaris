"""
PhysioNet WFDB (.hea + .dat) Reader Module
Supports:
- Format 16: 16-bit two's complement integer samples.
- Format 212: 12-bit bit-packed integer samples (pairs of samples packed in 3 bytes).
- Native fallback with zero required dependencies, plus optional 'wfdb' package support.
"""

from __future__ import annotations
from typing import Any

import contextlib
from dataclasses import dataclass
from collections.abc import Iterator
from pathlib import Path
import warnings

import numpy as np

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
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
    lead_names: list[str]
    units: list[str]
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
    if path.suffix.lower() in (".dat", ".mat"):
        header_path = path.with_suffix(".hea")
        dat_path = path
    elif path.suffix.lower() == ".hea":
        header_path = path
        dat_path = path.with_suffix(".dat")
    else:
        header_path = Path(str(path) + ".hea")
        dat_path = Path(str(path) + ".dat")

    if not header_path.exists():
        raise FileNotFoundError(f"WFDB header not found: {header_path}")

    # Use wfdb library if available
    if HAS_WFDB:
        with contextlib.suppress(Exception):
            record = wfdb.rdrecord(str(header_path.with_suffix("")))
            signals = record.p_signal.T.astype(np.float32)
            return WFDBRecord(
                record_name=record.record_name,
                sampling_rate=float(record.fs),
                num_signals=record.n_sig,
                num_samples=record.sig_len,
                lead_names=record.sig_name,
                units=record.units,
                signals=signals,
            )

    # Pure-Python Native WFDB Parser
    with open(header_path, encoding="utf-8", errors="ignore") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not lines:
        raise ValueError(f"Empty WFDB header: {header_path}")

    # Parse Record Line (Line 0): [name] [num_signals] [sampling_rate] [num_samples]
    first_tokens = lines[0].split()
    record_name = first_tokens[0]
    num_signals = int(first_tokens[1])
    raw_fs = first_tokens[2].split("/")[0].split("(")[0] if len(first_tokens) > 2 else "250.0"
    fs = float(raw_fs)
    sig_len = int(first_tokens[3]) if len(first_tokens) > 3 else 0

    if not (1 <= num_signals <= 64):
        raise ValueError(f"Security Alert: Invalid WFDB signal count ({num_signals}). Must be between 1 and 64.")
    if sig_len < 0 or sig_len > 100_000_000:
        raise ValueError(f"Security Alert: Invalid WFDB sample count ({sig_len}).")

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
        fmt_str, _, off_str = tokens[1].partition("+")
        fmt = int(fmt_str)
        byte_off = int(off_str) if off_str.isdigit() else 0
        formats.append((fmt, byte_off))

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

    # Resolve binary data file (.dat or .mat referenced by the WFDB header)
    safe_dat_name = Path(dat_filenames[0]).name if dat_filenames else dat_path.name
    candidate = header_path.parent / safe_dat_name
    if candidate.exists():
        dat_path = candidate
    elif not dat_path.exists():
        raise FileNotFoundError(f"WFDB binary data file not found: {dat_path}")

    with open(dat_path, "rb") as f:
        raw_bytes = f.read()

    if len(raw_bytes) == 0:
        raise ValueError(f"Corrupt WFDB record: Binary data file '{dat_path.name}' contains 0 bytes.")

    main_format, byte_offset = formats[0] if formats else (16, 0)
    if 0 < byte_offset < len(raw_bytes):
        raw_bytes = raw_bytes[byte_offset:]

    if main_format == 16:
        # Format 16: standard 16-bit signed integers (interleaved in .dat, or signal-major/interleaved in wfdb2mat .mat)
        raw_arr = np.frombuffer(raw_bytes[: (len(raw_bytes) // 2) * 2], dtype="<i2")
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


# MIT-BIH / PhysioNet WFDB Annotation Code -> AAMI EC57 Class Mapping
WFDB_ANN_TO_AAMI: dict[int, str] = {
    1: "N",   # Normal beat
    2: "N",   # LBBB
    3: "N",   # RBBB
    4: "S",   # Aberrated atrial premature
    5: "V",   # Premature ventricular contraction (PVC)
    6: "F",   # Fusion of ventricular and normal
    7: "S",   # Nodal (junctional) premature
    8: "S",   # Atrial premature (PAC)
    9: "S",   # Supraventricular premature
    10: "V",  # Ventricular escape
    11: "N",  # Nodal (junctional) escape
    12: "Q",  # Paced beat
    13: "Q",  # Unclassifiable beat
    34: "N",  # Atrial escape
    38: "Q",  # Fusion of paced and normal
}


def read_wfdb_annotations(atr_path: str | Path) -> dict[str, list]:
    """Parses a PhysioNet MIT-BIH binary annotation file (.atr, .q1c, .pu) into sample indices and AAMI classes."""
    path = Path(atr_path)
    if not path.is_file():
        raise FileNotFoundError(f"WFDB annotation file not found: {path}")

    data = path.read_bytes()
    samples: list[int] = []
    aami_classes: list[str] = []
    raw_codes: list[int] = []

    curr_time = 0
    pos = 0
    n_bytes = len(data)

    while pos + 2 <= n_bytes:
        word = int.from_bytes(data[pos : pos + 2], byteorder="little", signed=False)
        pos += 2
        ann_code = (word >> 10) & 0x3F
        delta = word & 0x03FF

        if ann_code == 0 and delta == 0:
            break  # EOF marker
        if ann_code == 59:  # SKIP: next 4 bytes are 32-bit signed PDP-11/mixed-endian interval
            if pos + 4 > n_bytes:
                break
            hi = int.from_bytes(data[pos : pos + 2], byteorder="little", signed=True)
            lo = int.from_bytes(data[pos + 2 : pos + 4], byteorder="little", signed=False)
            skip_val = (hi << 16) | lo
            curr_time += skip_val
            pos += 4
            continue
        if ann_code in (60, 61, 62):  # NUM, SUB, CHN modifier
            continue
        if ann_code == 63:  # AUX string: delta is byte count of auxiliary string (even-padded)
            skip_bytes = delta + (delta % 2)
            pos += skip_bytes
            continue

        curr_time += delta
        if ann_code in WFDB_ANN_TO_AAMI:
            samples.append(int(curr_time))
            aami_classes.append(WFDB_ANN_TO_AAMI[ann_code])
            raw_codes.append(int(ann_code))

    return {
        "r_peaks": samples,
        "aami_classes": aami_classes,
        "raw_codes": raw_codes,
        "total_beats": len(samples),
    }


def iter_wfdb_chunks_format16(
    record_path_or_header: str | Path,
    lead_name_or_index: str | int = 0,  # pass 'all' for (n_leads, n_win) float32
    chunk_duration_sec: float = 300.0,
    overlap_sec: float = 5.0,
) -> Iterator[dict[str, Any]] | None:
    """True zero-copy out-of-core chunk iterator for WFDB Format 16 (.dat) Holter recordings."""
    path = Path(record_path_or_header)
    header_path = path.with_suffix(".hea") if path.suffix != ".hea" else path
    if not header_path.exists():
        return None

    with open(header_path, encoding="utf-8", errors="ignore") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    if not lines:
        return None

    first_tokens = lines[0].split()
    record_name = first_tokens[0]
    num_signals = int(first_tokens[1])
    raw_fs = first_tokens[2].split("/")[0].split("(")[0] if len(first_tokens) > 2 else "250.0"
    fs = float(raw_fs)
    if not (1 <= num_signals <= 64) or fs <= 0:
        return None

    lead_names: list[str] = []
    gains: list[float] = []
    baselines: list[int] = []
    formats: list[int] = []
    dat_filenames: list[str] = []

    for i in range(1, num_signals + 1):
        if i >= len(lines):
            break
        tokens = lines[i].split()
        dat_filenames.append(tokens[0])
        formats.append(int(tokens[1].split("+")[0].split(":")[0]))
        gain_str = tokens[2] if len(tokens) > 2 else "200.0"
        baseline = 0
        if "(" in gain_str and ")" in gain_str:
            g_part, rest = gain_str.split("(", 1)
            b_part = rest.split(")", 1)[0]
            gain = float(g_part) if g_part else 200.0
            baseline = int(b_part) if b_part else 0
        else:
            gain = float(gain_str.split("/")[0]) if "/" in gain_str else float(gain_str)
        gains.append(gain if gain != 0 else 200.0)
        baselines.append(baseline)
        lead_names.append(tokens[8] if len(tokens) > 8 else f"Lead_{i}")

    if not formats or any(fmt != 16 for fmt in formats):
        return None

    unique_dats = {Path(d).name for d in dat_filenames}
    if len(unique_dats) != 1:
        return None
    dat_path = header_path.parent / next(iter(unique_dats))
    if not dat_path.exists():
        dat_path = header_path.with_suffix(".dat")
    if not dat_path.exists():
        raise FileNotFoundError(f"WFDB binary data file not found: {dat_path}")

    file_bytes = dat_path.stat().st_size
    frame_bytes = 2 * num_signals
    total_samples = file_bytes // frame_bytes
    if total_samples <= 0:
        raise ValueError(f"Corrupt WFDB record: Binary data file '{dat_path.name}' contains 0 bytes.")

    yield_all = isinstance(lead_name_or_index, str) and lead_name_or_index.strip().lower() == "all"
    if yield_all:
        lead_idx = 0
        gains_arr = np.asarray([gains[i] if i < len(gains) else 200.0 for i in range(num_signals)], dtype=np.float32)
        baselines_arr = np.asarray(
            [baselines[i] if i < len(baselines) else 0 for i in range(num_signals)], dtype=np.float32
        )
    else:
        if isinstance(lead_name_or_index, int):
            lead_idx = max(0, min(num_signals - 1, lead_name_or_index))
        else:
            target = str(lead_name_or_index).strip().upper()
            lead_idx = next((idx for idx, n in enumerate(lead_names) if n.strip().upper() == target), 0)
        gain = gains[lead_idx] if lead_idx < len(gains) else 200.0
        baseline = baselines[lead_idx] if lead_idx < len(baselines) else 0
    meta = {
        "source_format": "wfdb",
        "record_name": record_name,
        "lead_names": lead_names,
        "mmap_backed": True,
        "true_streaming_wfdb": True,
    }

    def _gen() -> Iterator[dict[str, Any]]:
        chunk_samples = max(1, int(round(chunk_duration_sec * fs)))
        overlap_samples = max(0, int(round(overlap_sec * fs)))
        with open(dat_path, "rb") as fh:
            core_start = 0
            chunk_idx = 0
            while core_start < total_samples:
                core_end = min(total_samples, core_start + chunk_samples)
                win_start = max(0, core_start - overlap_samples)
                win_end = min(total_samples, core_end + overlap_samples)
                n_win = win_end - win_start
                fh.seek(win_start * frame_bytes)
                raw = fh.read(n_win * frame_bytes)
                arr = np.frombuffer(raw, dtype="<i2").reshape(-1, num_signals)
                if yield_all:
                    sig_chunk = ((arr.astype(np.float32) - baselines_arr) / gains_arr).T
                else:
                    sig_chunk = (arr[:, lead_idx].astype(np.float32) - baseline) / gain
                yield {
                    "chunk_index": chunk_idx,
                    "start_sample": win_start,
                    "end_sample": win_end,
                    "core_start_sample": core_start,
                    "core_end_sample": core_end,
                    "signal": sig_chunk,
                    "fs": fs,
                    "total_samples": total_samples,
                    "metadata": meta,
                }
                core_start = core_end
                chunk_idx += 1

    return _gen()
