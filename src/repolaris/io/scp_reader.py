"""
SCP-ECG (Standard Communication Protocol for Computer-Assisted Electrocardiography) Reader Module.

Specification:
- European Standard: CEN EN 1064:2005+A1:2007
- International Standard: ISO 13713
- Binary Structure:
    - Bytes 0-1: CRC-CCITT Checksum over entire file
    - Bytes 2-5: Total File Length (uint32)
    - Section 0: Pointer Table to Sections 1-11
    - Section 1: Header / Patient Data
    - Section 2: Huffman Tables (supports CEN EN 1064 Default Table 19999)
    - Section 3: Lead Definitions (start/end sample, lead ID, subtraction flags)
    - Section 4: QRS Location & Reference Beat Subtraction Zones
    - Section 5: Reference Beat Data (supports Default Huffman 19999)
    - Section 6: Rhythm Data (uncompressed, 1st/2nd difference, or Default Huffman 19999)
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# Standard SCP Lead Identification Codes (CEN EN 1064 Table 8)
SCP_LEAD_NAMES = {
    1: "Lead I",
    2: "Lead II",
    3: "V1",
    4: "V2",
    5: "V3",
    6: "V4",
    7: "V5",
    8: "V6",
    9: "V7",
    10: "V2R",
    11: "V3R",
    12: "V4R",
    13: "V5R",
    14: "V6R",
    15: "V7R",
    16: "X",
    17: "Y",
    18: "Z",
    61: "Lead III",
    62: "aVR",
    63: "aVL",
    64: "aVF",
}

# CEN EN 1064:2005 Table A.1 — Default Huffman Table (n_tables == 19999)
# Each entry: (prefix_bits_str_msb_first, extra_bits, value_or_mode)
# mode None => literal integer value; "signed8" => 8-bit signed literal; "signed16" => 16-bit signed literal
_CEN_DEFAULT_HUFFMAN: list[tuple[str, int, int | str]] = [
    ("0", 0, 0),
    ("100", 0, 1),
    ("101", 0, -1),
    ("1100", 0, 2),
    ("1101", 0, -2),
    ("11100", 0, 3),
    ("11101", 0, -3),
    ("111100", 0, 4),
    ("111101", 0, -4),
    ("1111100", 0, 5),
    ("1111101", 0, -5),
    ("11111100", 0, 6),
    ("11111101", 0, -6),
    ("111111100", 0, 7),
    ("111111101", 0, -7),
    ("1111111100", 0, 8),
    ("1111111101", 0, -8),
    ("1111111110", 8, "signed8"),
    ("1111111111", 16, "signed16"),
]


def _build_default_huffman_trie() -> dict:
    root: dict = {}
    for bits, extra, val in _CEN_DEFAULT_HUFFMAN:
        node = root
        for b in bits:
            bit_i = 1 if b == "1" else 0
            node = node.setdefault(bit_i, {})
        node["leaf"] = (extra, val)
    return root


_DEFAULT_HUFFMAN_TRIE = _build_default_huffman_trie()


def _decode_cen_default_huffman(payload: bytes, expected_samples: int) -> np.ndarray:
    """Decodes a bitstream encoded with the CEN EN 1064 Default Huffman Table (19999).

    Per CEN EN 1064 Section 5.4.3.2, bits are read MSB-first within each byte.
    """
    out = np.empty(expected_samples, dtype=np.int32)
    n_bytes = len(payload)
    bit_pos = 0
    total_bits = n_bytes * 8
    trie = _DEFAULT_HUFFMAN_TRIE
    count = 0

    while count < expected_samples and bit_pos < total_bits:
        node = trie
        while "leaf" not in node:
            if bit_pos >= total_bits:
                return out[:count]
            byte_val = payload[bit_pos >> 3]
            bit = (byte_val >> (7 - (bit_pos & 7))) & 1
            bit_pos += 1
            if bit not in node:
                return out[:count]
            node = node[bit]

        extra_bits, val = node["leaf"]
        if extra_bits == 0:
            out[count] = int(val)
        else:
            if bit_pos + extra_bits > total_bits:
                return out[:count]
            raw_u = 0
            for _ in range(extra_bits):
                byte_val = payload[bit_pos >> 3]
                bit = (byte_val >> (7 - (bit_pos & 7))) & 1
                raw_u = (raw_u << 1) | bit
                bit_pos += 1
            # Two's complement sign extension for 8-bit or 16-bit signed literal
            sign_bit = 1 << (extra_bits - 1)
            if raw_u & sign_bit:
                raw_u -= 1 << extra_bits
            out[count] = raw_u
        count += 1

    return out[:count]


def _reconstruct_differences(samples: np.ndarray, diff_mode: int) -> np.ndarray:
    """Reconstructs 1st- or 2nd-order difference encoded SCP-ECG sample sequences.

    Per CEN EN 1064 Section 5.4.3.1:
    - diff_mode == 0: Direct samples.
    - diff_mode == 1: First differences; sample[0] is raw, sample[n] = sample[n-1] + diff[n].
    - diff_mode == 2: Second differences; sample[0] and sample[1] are raw,
      sample[n] = 2 * sample[n-1] - sample[n-2] + diff[n].
    """
    arr = samples.astype(np.int64, copy=True)
    if arr.size == 0 or diff_mode == 0:
        return arr
    if diff_mode == 1:
        return np.cumsum(arr)
    if diff_mode == 2:
        if arr.size <= 2:
            return arr
        for i in range(2, arr.size):
            arr[i] = arr[i] + 2 * arr[i - 1] - arr[i - 2]
        return arr
    return arr


@dataclass
class SCPRecord:
    """Decoded physiological signals and clinical header data from an SCP-ECG binary container."""
    sampling_rate: float
    num_leads: int
    num_samples: int
    lead_names: list[str]
    signals: np.ndarray  # Shape: (num_leads, num_samples) in physical millivolts (mV)
    units: list[str] = field(default_factory=list)
    patient_id: str = "ANONYMOUS"
    patient_name: str = "PATIENT"


def is_scp_file(filepath: str | Path | os.PathLike[str]) -> bool:
    """Verifies whether a file is an SCP-ECG binary file by inspecting Section 0 pointers."""
    path = Path(filepath)
    if not path.is_file() or path.stat().st_size < 32:
        return False
    try:
        with open(path, "rb") as f:
            _crc = f.read(2)
            file_len = struct.unpack("<I", f.read(4))[0]
            _sec_crc, sec_id, sec_len = struct.unpack("<HHI", f.read(8))
            return sec_id == 0 and sec_len > 16 and file_len <= path.stat().st_size + 16
    except Exception:
        return False


def read_scp_ecg(filepath: str | Path | os.PathLike[str]) -> SCPRecord:
    """Parses an SCP-ECG (EN 1064) file and returns physical waveforms in millivolts.

    Supports uncompressed, 1st/2nd-difference encoded, CEN EN 1064 Default Huffman
    Table (19999) compressed Section 6 rhythm data, and Section 5 reference-beat
    residual reconstruction.
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
    _s0_crc, s0_id, s0_len = struct.unpack("<HHI", data[6:14])
    if s0_id != 0:
        raise ValueError(f"Invalid SCP file: First section ID is {s0_id}, expected Section 0 pointer table.")

    # Read pointer table in Section 0 body (starts at byte 6 + 16 = 22)
    sec_pointers: dict[int, tuple[int, int]] = {}  # sec_id -> (length, offset_0_based)
    offset = 22
    s0_end = 6 + s0_len
    while offset + 10 <= s0_end and offset + 10 <= len(data):
        sec_id, sec_len, sec_off = struct.unpack("<HII", data[offset : offset + 10])
        if sec_off > 0 and sec_len > 0:
            sec_pointers[sec_id] = (sec_len, sec_off - 1)  # Convert 1-based offset to 0-based index
        offset += 10

    # Check Section 2 (Huffman tables): support CEN EN 1064 Default Table (19999)
    use_default_huffman = False
    if 2 in sec_pointers and sec_pointers[2][0] > 16:
        s2_len, s2_off = sec_pointers[2]
        if s2_off + 18 <= len(data):
            n_huff_tables = struct.unpack("<H", data[s2_off + 16 : s2_off + 18])[0]
            if n_huff_tables == 19999:
                use_default_huffman = True
            else:
                raise NotImplementedError(
                    f"SCP-ECG Section 2 custom Huffman tables (n_tables={n_huff_tables}) are not supported; "
                    "only uncompressed and CEN EN 1064 Default Huffman Table (19999) are supported."
                )

    # 1. Parse Section 3 (Lead Definitions)
    if 3 not in sec_pointers:
        raise ValueError("Corrupt SCP-ECG file: Mandatory Section 3 (Lead Definitions) not found.")

    s3_len, s3_off = sec_pointers[3]
    if s3_off + s3_len > len(data):
        raise ValueError("Section 3 extends beyond file boundary.")

    # Section 3 Header is 16 bytes
    s3_body = s3_off + 16
    n_leads = data[s3_body]
    s3_flags = data[s3_body + 1]
    ref_beat_subtracted = bool(s3_flags & 0x01)
    if n_leads <= 0 or n_leads > 64:
        raise ValueError(f"Invalid SCP lead count: {n_leads}")

    lead_names: list[str] = []
    lead_expected_samples: list[int] = []
    # Each lead in Section 3 has: 4B start sample, 4B end sample, 1B lead id
    l_off = s3_body + 2
    # Handle both standard 2-byte Section 3 header (n_leads, flags) and 4-byte padded synthetic headers
    if l_off + n_leads * 9 > s3_off + s3_len:
        l_off = s3_body + 4
    elif n_leads >= 1:
        # Heuristic: in standard SCP Section 3, start_sample is 1-based (>=1) and end_sample > start_sample
        s_try, e_try, c_try = struct.unpack("<IIB", data[l_off : l_off + 9])
        if (s_try == 0 or e_try < s_try or c_try == 0) and (s3_body + 4 + n_leads * 9 <= s3_off + s3_len):
            l_off = s3_body + 4

    for _ in range(n_leads):
        if l_off + 9 > s3_off + s3_len:
            break
        start_samp, end_samp, l_code = struct.unpack("<IIB", data[l_off : l_off + 9])
        lead_name = SCP_LEAD_NAMES.get(l_code, f"Lead_{len(lead_names) + 1}")
        lead_names.append(lead_name)
        n_exp = int(end_samp - start_samp + 1) if end_samp >= start_samp and start_samp >= 1 else 0
        lead_expected_samples.append(n_exp)
        l_off += 9

    # Optional Section 4 (QRS locations) + Section 5 (Reference beat) when ref_beat_subtracted is active
    qrs_zones: list[tuple[int, int, int]] = []  # (sub_start, fiducial, sub_end) 1-based
    ref_beat_fiducial = 0
    ref_beat_signals: list[np.ndarray] | None = None
    if ref_beat_subtracted and 4 in sec_pointers and 5 in sec_pointers:
        s4_len, s4_off = sec_pointers[4]
        if s4_off + 22 <= len(data):
            s4_body = s4_off + 16
            ref_len_ms, ref_beat_fiducial, n_qrs = struct.unpack("<HHH", data[s4_body : s4_body + 6])
            q_ptr = s4_body + 6
            for _ in range(n_qrs):
                if q_ptr + 14 > s4_off + s4_len:
                    break
                _q_type, sub_start, fid, sub_end = struct.unpack("<HIII", data[q_ptr : q_ptr + 14])
                qrs_zones.append((sub_start, fid, sub_end))
                q_ptr += 14

            if qrs_zones:
                s5_len, s5_off = sec_pointers[5]
                s5_body = s5_off + 16
                _s5_avm, s5_dt_us, s5_diff, _s5_res = struct.unpack("<HHBB", data[s5_body : s5_body + 6])
                s5_ptr = s5_body + 6
                s5_byte_counts = []
                for _ in range(n_leads):
                    s5_byte_counts.append(struct.unpack("<H", data[s5_ptr : s5_ptr + 2])[0])
                    s5_ptr += 2
                ref_n_samples = int(round((ref_len_ms * 1000.0) / max(1, s5_dt_us))) if ref_len_ms > 0 else 600
                ref_beat_signals = []
                for ch in range(n_leads):
                    cnt5 = s5_byte_counts[ch]
                    b5 = data[s5_ptr : s5_ptr + cnt5]
                    s5_ptr += cnt5
                    if use_default_huffman:
                        raw5 = _decode_cen_default_huffman(b5, ref_n_samples)
                    else:
                        raw5 = np.frombuffer(b5[: (len(b5) // 2) * 2], dtype="<i2")
                    ref_beat_signals.append(_reconstruct_differences(raw5, s5_diff))
    elif ref_beat_subtracted and 5 not in sec_pointers:
        raise NotImplementedError(
            "SCP-ECG Section 3 indicates reference beat subtraction, but Section 5 is missing."
        )

    # 2. Parse Section 6 (Rhythm Waveform Data)
    if 6 not in sec_pointers:
        raise ValueError("Corrupt SCP-ECG file: Mandatory Section 6 (Rhythm Data) not found.")

    s6_len, s6_off = sec_pointers[6]
    if s6_off + s6_len > len(data):
        raise ValueError("Section 6 extends beyond file boundary.")

    s6_body = s6_off + 16
    avm_nv, sample_interval_us, diff_mode, _bimodal = struct.unpack("<HHBB", data[s6_body : s6_body + 6])
    avm_nv = avm_nv if avm_nv > 0 else 5000  # Default 5 uV per LSB = 5000 nV
    fs = 1_000_000.0 / sample_interval_us if sample_interval_us > 0 else 500.0

    cur_ptr = s6_body + 6
    lead_byte_counts = []
    for _ in range(n_leads):
        cnt = struct.unpack("<H", data[cur_ptr : cur_ptr + 2])[0]
        lead_byte_counts.append(cnt)
        cur_ptr += 2

    signals: list[np.ndarray] = []
    for ch in range(n_leads):
        cnt = lead_byte_counts[ch]
        ch_bytes = data[cur_ptr : cur_ptr + cnt]
        cur_ptr += cnt

        if use_default_huffman:
            exp_n = lead_expected_samples[ch] if ch < len(lead_expected_samples) and lead_expected_samples[ch] > 0 else cnt * 4
            raw_samples = _decode_cen_default_huffman(ch_bytes, exp_n)
        else:
            raw_samples = np.frombuffer(ch_bytes[: (len(ch_bytes) // 2) * 2], dtype="<i2")

        recon = _reconstruct_differences(raw_samples, diff_mode)

        # Add Section 5 reference beat back into residual zones if subtracted
        if ref_beat_subtracted and ref_beat_signals is not None and ch < len(ref_beat_signals):
            ref_sig = ref_beat_signals[ch]
            for sub_start, fid, sub_end in qrs_zones:
                # 1-based sample indices
                for s_idx in range(max(1, sub_start), min(len(recon), sub_end) + 1):
                    r_idx = (s_idx - fid) + ref_beat_fiducial - 1
                    if 0 <= r_idx < len(ref_sig):
                        recon[s_idx - 1] += ref_sig[r_idx]

        # Convert to mV: raw * nV / 1,000,000
        sig_mv = (recon.astype(np.float32) * avm_nv) / 1_000_000.0
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
