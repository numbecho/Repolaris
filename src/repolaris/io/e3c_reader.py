"""Excorde 3C Holter (.e3c) ECG file reader module.

Parses proprietary Excorde 3C Holter recording archives (.e3c), which package
raw multi-lead binary electrocardiogram waveforms and algorithmic beat annotations
(QRS onsets, offsets, R peaks, RR metrics, and beat classifications) inside
a compressed ZIP container.
"""

from __future__ import annotations

import io
import os
import struct
import zipfile
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


def read_e3c(
    filepath: Union[str, os.PathLike[str]],
    default_fs: float = 250.0,
    gain_scale: float = 2.65e-3,
    channels: int = 2,
) -> Dict[str, Any]:
    """Reads multi-lead ECG waveforms and QRS annotations from an Excorde 3C (.e3c) archive.

    Decompresses `current.ECG` and `current.QRS` directly in-memory from the container:
    - `current.ECG`: Little-endian 16-bit signed integer interleaved channel data.
    - `current.QRS`: 25-byte fixed-width beat annotation records (<6IB: qrson, qrsend,
      pattern, rpeak, rrprev, rrmean, bclass).

    Args:
        filepath: Path to the .e3c zip container.
        default_fs: Sampling frequency in Hertz (standard Excorde 3C is 250.0 Hz).
        gain_scale: Conversion multiplier to convert raw ADC integers to physical millivolts.
        channels: Number of recorded leads (default: 2).

    Returns:
        A dictionary containing:
            - 'signals': Dict[str, np.ndarray] mapping channel names ('Channel 1', 'Channel 2')
              to 1D float64 physical waveform arrays.
            - 'fs': Sampling frequency in Hz.
            - 'lead_names': List of channel labels.
            - 'duration_s': Total recording duration in seconds.
            - 'samples': Total samples per lead.
            - 'annotations': Dict containing beat arrays ('qrson', 'qrsend', 'rpeak',
              'rrprev', 'rrmean', 'bclass', 'pattern').
            - 'hours': Integer hours of recording.
            - 'minutes': Integer minutes of recording.
            - 'seconds': Integer seconds of recording.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the file is not a valid Excorde 3C ZIP archive or is corrupted.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Excorde 3C file not found: {filepath}")

    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            namelist = zf.namelist()
            ecg_name = next((n for n in namelist if n.lower().endswith("current.ecg") or n.lower().endswith(".ecg")), None)
            qrs_name = next((n for n in namelist if n.lower().endswith("current.qrs") or n.lower().endswith(".qrs")), None)

            if not ecg_name:
                raise ValueError(f"No current.ECG data stream found inside {filepath}")

            ecg_bytes = zf.read(ecg_name)
            qrs_bytes = zf.read(qrs_name) if qrs_name else b""
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Corrupted or invalid Excorde 3C archive: {filepath}") from exc

    # Parse raw ECG binary waveform (16-bit signed integer little-endian, Fortran-order channels)
    n_total_samples = len(ecg_bytes) // 2
    samples_per_ch = n_total_samples // channels
    raw_data = np.frombuffer(ecg_bytes[: samples_per_ch * channels * 2], dtype=np.int16)

    # Reshape channels: Excorde stores samples in interleaved / column-major order
    reshaped = raw_data.reshape((channels, samples_per_ch), order="F").astype(np.float64) * gain_scale

    lead_names = [f"Channel {i + 1}" for i in range(channels)]
    signals = {lead_names[i]: reshaped[i, :] for i in range(channels)}

    # Parse QRS annotations if available
    annotations: Dict[str, np.ndarray] = {
        "qrson": np.array([], dtype=np.int64),
        "qrsend": np.array([], dtype=np.int64),
        "pattern": np.array([], dtype=np.int64),
        "rpeak": np.array([], dtype=np.int64),
        "rrprev": np.array([], dtype=np.int64),
        "rrmean": np.array([], dtype=np.int64),
        "bclass": np.array([], dtype=np.uint8),
    }

    if qrs_bytes:
        record_size = 25  # 6 * 4 (uint32) + 1 (uint8)
        n_beats = len(qrs_bytes) // record_size
        if n_beats > 0:
            fmt = f"<{n_beats * 6}I{n_beats}B"
            # Unpack record by record
            rec_fmt = "<6IB"
            q_on = []
            q_end = []
            patt = []
            r_pk = []
            rr_pr = []
            rr_mn = []
            b_cl = []
            for b_idx in range(n_beats):
                start = b_idx * record_size
                vals = struct.unpack_from(rec_fmt, qrs_bytes, start)
                q_on.append(vals[0])
                q_end.append(vals[1])
                patt.append(vals[2])
                r_pk.append(vals[3])
                rr_pr.append(vals[4])
                rr_mn.append(vals[5])
                b_cl.append(vals[6])

            annotations = {
                "qrson": np.array(q_on, dtype=np.int64),
                "qrsend": np.array(q_end, dtype=np.int64),
                "pattern": np.array(patt, dtype=np.int64),
                "rpeak": np.array(r_pk, dtype=np.int64),
                "rrprev": np.array(rr_pr, dtype=np.int64),
                "rrmean": np.array(rr_mn, dtype=np.int64),
                "bclass": np.array(b_cl, dtype=np.uint8),
            }

    duration_s = float(samples_per_ch) / default_fs
    hours = int(duration_s // 3600)
    minutes = int((duration_s % 3600) // 60)
    seconds = int(duration_s % 60)

    return {
        "signals": signals,
        "fs": default_fs,
        "lead_names": lead_names,
        "duration_s": duration_s,
        "samples": samples_per_ch,
        "annotations": annotations,
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
    }
