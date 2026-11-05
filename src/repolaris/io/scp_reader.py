"""
SCP-ECG (Standard Communication Protocol for Computer-Assisted Electrocardiography) Reader Module.

Specification:
- European Standard: CEN EN 1064:2005+A1:2007
- International Standard: ISO 13713
- Binary Structure:
    - Bytes 0-1: CRC-CCITT Checksum over entire file
    - Bytes 2-5: Total File Length (uint32)
    - Section 0: Pointer Table to Sections 1-11
        - Section Header (16 bytes): CRC (uint16), Section ID (uint16=0), Length (uint32), Version (uint8), Protocol (uint8), Reserved (6 bytes)
        - Pointer Table: Array of (Section ID uint16, Section Length uint32, Section Offset uint32)
    - Section 1: Header / Patient Data
    - Section 3: Lead Definitions
    - Section 6: Rhythm Data
"""

from __future__ import annotations

import os
import struct
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Union
import numpy as np

# Standard SCP Lead Identification Codes (CEN EN 1064 Table 8)
SCP_LEAD_NAMES = {
    1: "Lead I",
    2: "Lead II",
    3: "Lead III",
    4: "aVR",
    5: "aVL",
    6: "aVF",
    7: "V1",
    8: "V2",
    9: "V3",
    10: "V4",
    11: "V5",
    12: "V6",
    13: "V7",
    14: "V8",
    15: "V9",
    16: "V3R",
    17: "V4R",
    18: "V5R",
    19: "X",
    20: "Y",
    21: "Z",
}


@dataclass
class SCPRecord:
    """Decoded physiological signals and clinical header data from an SCP-ECG binary container."""
    sampling_rate: float
    num_leads: int
    num_samples: int
    lead_names: List[str]
    signals: np.ndarray  # Shape: (num_leads, num_samples) in physical millivolts (mV)
    units: List[str] = field(default_factory=list)
    patient_id: str = "ANONYMOUS"
    patient_name: str = "PATIENT"


def is_scp_file(filepath: Union[str, Path, os.PathLike[str]]) -> bool:
    """Verifies whether a file is an SCP-ECG binary file by inspecting Section 0 pointers."""
    path = Path(filepath)
    if not path.is_file() or path.stat().st_size < 32:
        return False
    try:
        with open(path, "rb") as f:
            _crc = f.read(2)
            file_len = struct.unpack("<I", f.read(4))[0]
            sec_crc, sec_id, sec_len = struct.unpack("<HHI", f.read(8))
            return sec_id == 0 and sec_len > 16 and file_len <= path.stat().st_size + 16
    except Exception:
        return False


def read_scp_ecg(filepath: Union[str, Path, os.PathLike[str]]) -> SCPRecord:
    """Parses an SCP-ECG (EN 1064) file and returns physical waveforms in millivolts.

    Decodes Section 0 (pointers), Section 3 (lead specs), and Section 6 (rhythm data).

    Args:
        filepath: Path to the .scp file.

    Returns:
        SCPRecord containing calibrated float32 signals in mV.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If Section 0, Section 3, or Section 6 is missing or malformed.
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"SCP-ECG file not found: {path}")

    file_size = path.stat().st_size
    if file_size > 250 * 1024 * 1024:
        raise ValueError(f"Security Alert: SCP file ({file_size} B) exceeds 250 MB safety ceiling.")

    with open(path, "rb") as f:
        data = f.read()

    if len(data) < 32:
        raise ValueError(f"Corrupt SCP-ECG file: Length ({len(data)} B) too small for valid header.")

    _crc, _reported_len = struct.unpack("<HI", data[0:6])

    # Section 0 header starts at byte 6 (16 bytes total header)
    s0_crc, s0_id, s0_len = struct.unpack("<HHI", data[6:14])
    if s0_id != 0:
        raise ValueError(f"Invalid SCP file: First section ID is {s0_id}, expected Section 0 pointer table.")

    # Read pointer table in Section 0 body (starts at byte 6 + 16 = 22)
    sec_pointers: Dict[int, Tuple[int, int]] = {}  # sec_id -> (length, offset_0_based)
    offset = 22
    s0_end = 6 + s0_len
    while offset + 10 <= s0_end and offset + 10 <= len(data):
        sec_id, sec_len, sec_off = struct.unpack("<HII", data[offset : offset + 10])
        if sec_off > 0 and sec_len > 0:
            sec_pointers[sec_id] = (sec_len, sec_off - 1)  # Convert 1-based offset to 0-based index
        offset += 10

    # 1. Parse Section 3 (Lead Definitions)
    if 3 not in sec_pointers:
        raise ValueError("Corrupt SCP-ECG file: Mandatory Section 3 (Lead Definitions) not found.")

    s3_len, s3_off = sec_pointers[3]
    if s3_off + s3_len > len(data):
        raise ValueError("Section 3 extends beyond file boundary.")

    # Section 3 Header is 16 bytes: 2B CRC, 2B ID, 4B Len, 1B Ver, 1B Prot, 6B Res
    s3_body = s3_off + 16
    n_leads = data[s3_body]
    if n_leads <= 0 or n_leads > 64:
        raise ValueError(f"Invalid SCP lead count: {n_leads}")

    lead_names: List[str] = []
    # Each lead in Section 3 has: 4B start sample, 4B end sample, 1B lead id
    l_off = s3_body + 4
    for _ in range(n_leads):
        if l_off + 9 > s3_off + s3_len:
            break
        _start_samp, _end_samp, l_code = struct.unpack("<IIB", data[l_off : l_off + 9])
        lead_name = SCP_LEAD_NAMES.get(l_code, f"Lead_{len(lead_names) + 1}")
        lead_names.append(lead_name)
        l_off += 9

    # 2. Parse Section 6 (Rhythm WaveformData)
    if 6 not in sec_pointers:
        raise ValueError("Corrupt SCP-ECG file: Mandatory Section 6 (Rhythm Data) not found.")

    s6_len, s6_off = sec_pointers[6]
    if s6_off + s6_len > len(data):
        raise ValueError("Section 6 extends beyond file boundary.")

    # Section 6 Header is 16 bytes
    s6_body = s6_off + 16
    # 2B AVM (in nV), 2B sampling interval (in us), 1B diff, 1B bimodal
    avm_nv, sample_interval_us, diff_mode, _bimodal = struct.unpack("<HHBB", data[s6_body : s6_body + 6])
    avm_nv = avm_nv if avm_nv > 0 else 5000  # Default 5 uV per LSB = 5000 nV
    fs = 1_000_000.0 / sample_interval_us if sample_interval_us > 0 else 500.0

    # Rhythm data start: length of lead 1 data, length of lead 2 data... then samples
    cur_ptr = s6_body + 6
    lead_byte_counts = []
    for _ in range(n_leads):
        cnt = struct.unpack("<H", data[cur_ptr : cur_ptr + 2])[0]
        lead_byte_counts.append(cnt)
        cur_ptr += 2

    signals: List[np.ndarray] = []
    for ch in range(n_leads):
        cnt = lead_byte_counts[ch]
        ch_bytes = data[cur_ptr : cur_ptr + cnt]
        cur_ptr += cnt

        # Decode 16-bit integer samples
        raw_samples = np.frombuffer(ch_bytes[: (len(ch_bytes) // 2) * 2], dtype="<i2")
        if diff_mode == 1:
            raw_samples = np.cumsum(raw_samples)
        elif diff_mode == 2:
            raw_samples = np.cumsum(np.cumsum(raw_samples))

        # Convert to mV: raw * nV / 1,000,000
        sig_mv = (raw_samples.astype(np.float32) * avm_nv) / 1_000_000.0
        signals.append(sig_mv)

    min_samples = min(len(s) for s in signals) if signals else 0
    if min_samples == 0:
        raise ValueError("SCP Section 6 contains 0 valid samples.")

    matrix = np.array([s[:min_samples] for s in signals], dtype=np.float32)

    return SCPRecord(
        sampling_rate=fs,
        num_leads=matrix.shape[0],
        num_samples=matrix.shape[1],
        lead_names=lead_names[: matrix.shape[0]],
        signals=matrix,
        units=["mV"] * matrix.shape[0],
    )
