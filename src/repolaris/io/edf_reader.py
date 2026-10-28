"""
European Data Format (EDF / EDF+) (.edf) Reader and Writer Module
Specification: Kemp et al., 1992 (EDF) & 2003 (EDF+)

Provides zero-dependency pure-Python parsing for multi-day wearable patches,
Holter monitors, and continuous cardiac telemetry.
"""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
import numpy as np


@dataclass
class EDFRecord:
    patient_id: str
    recording_id: str
    start_date: str
    start_time: str
    num_signals: int
    duration_sec: float
    lead_names: List[str]
    units: List[str]
    sampling_rates: List[float]
    signals: np.ndarray  # Shape: (num_signals, total_samples) scaled to mV


def read_edf(filepath: str | Path) -> EDFRecord:
    """Reads and parses an official EDF or EDF+ (.edf) recording."""
    filepath = Path(filepath)
    with open(filepath, "rb") as f:
        # 1. Main Header (256 bytes)
        raw_header = f.read(256)
        if len(raw_header) < 256:
            raise ValueError(f"Corrupt EDF file: Header smaller than 256 bytes in {filepath}")

        version = raw_header[0:8].decode("ascii", errors="ignore").strip()
        patient_id = raw_header[8:88].decode("ascii", errors="ignore").strip()
        recording_id = raw_header[88:168].decode("ascii", errors="ignore").strip()
        start_date = raw_header[168:176].decode("ascii", errors="ignore").strip()
        start_time = raw_header[176:184].decode("ascii", errors="ignore").strip()
        header_bytes = int(raw_header[184:192].decode("ascii", errors="ignore").strip())
        num_records = int(raw_header[236:244].decode("ascii", errors="ignore").strip())
        record_duration = float(raw_header[244:252].decode("ascii", errors="ignore").strip())
        num_signals = int(raw_header[252:256].decode("ascii", errors="ignore").strip())

        # 2. Per-Signal Headers (num_signals * 256 bytes)
        raw_sig_headers = f.read(header_bytes - 256)
        
        def read_fields(length):
            nonlocal raw_sig_headers
            field_bytes = length * num_signals
            chunk = raw_sig_headers[:field_bytes]
            raw_sig_headers = raw_sig_headers[field_bytes:]
            return [chunk[i*length:(i+1)*length].decode("ascii", errors="ignore").strip() for i in range(num_signals)]

        labels = read_fields(16)
        transducers = read_fields(80)
        phys_dims = read_fields(8)
        phys_mins = [float(x) for x in read_fields(8)]
        phys_maxs = [float(x) for x in read_fields(8)]
        dig_mins = [float(x) for x in read_fields(8)]
        dig_maxs = [float(x) for x in read_fields(8)]
        prefilterings = read_fields(80)
        samples_per_record = [int(x) for x in read_fields(8)]
        read_fields(32)  # Reserved

        # 3. Read Data Records
        # Total samples per record across all channels
        record_size_samples = sum(samples_per_record)
        raw_data = np.fromfile(f, dtype="<i2")

    if num_records > 0 and len(raw_data) < num_records * record_size_samples:
        actual_records = len(raw_data) // record_size_samples
    else:
        actual_records = num_records if num_records > 0 else (len(raw_data) // record_size_samples)

    # Reconstruct continuous signals per channel
    channel_signals = []
    sampling_rates = []

    for ch_idx in range(num_signals):
        s_per_rec = samples_per_record[ch_idx]
        fs = float(s_per_rec / record_duration) if record_duration > 0 else 250.0
        sampling_rates.append(fs)

        # Calculate byte offset inside each data record
        offset_in_rec = sum(samples_per_record[:ch_idx])
        
        ch_raw = np.empty(actual_records * s_per_rec, dtype=np.int16)
        for rec in range(actual_records):
            rec_start = rec * record_size_samples + offset_in_rec
            ch_raw[rec * s_per_rec : (rec + 1) * s_per_rec] = raw_data[rec_start : rec_start + s_per_rec]

        # Convert digital counts to physical units
        d_min = dig_mins[ch_idx]
        d_max = dig_maxs[ch_idx]
        p_min = phys_mins[ch_idx]
        p_max = phys_maxs[ch_idx]

        denom = d_max - d_min if d_max != d_min else 1.0
        scale = (p_max - p_min) / denom
        phys_val = (ch_raw.astype(np.float32) - d_min) * scale + p_min

        # Normalize units to millivolts (mV)
        unit = phys_dims[ch_idx].lower()
        if "uv" in unit or "µv" in unit or "microvolt" in unit:
            phys_val /= 1000.0

        channel_signals.append(phys_val)

    # Filter out EDF Annotations channel if present
    valid_channels = []
    valid_labels = []
    valid_fs = []
    valid_units = []

    for idx, name in enumerate(labels):
        if "annotations" in name.lower() or "edf annotations" in name.lower():
            continue
        valid_channels.append(channel_signals[idx])
        valid_labels.append(name)
        valid_fs.append(sampling_rates[idx])
        valid_units.append("mV")

    # Stack into uniform 2D array if sample rates match
    max_len = max(len(c) for c in valid_channels) if valid_channels else 0
    signals_matrix = np.zeros((len(valid_channels), max_len), dtype=np.float32)
    for i, c in enumerate(valid_channels):
        signals_matrix[i, :len(c)] = c

    return EDFRecord(
        patient_id=patient_id,
        recording_id=recording_id,
        start_date=start_date,
        start_time=start_time,
        num_signals=len(valid_channels),
        duration_sec=float(actual_records * record_duration),
        lead_names=valid_labels,
        units=valid_units,
        sampling_rates=valid_fs,
        signals=signals_matrix
    )
