"""Universal ECG File Ingestion Router module.

Provides a unified interface to automatically detect format signatures and ingest
electrocardiogram recordings across all clinical, academic, and device formats:
- .pecg: PyECG Portable Clinical Exchange Package (CBOR/JSON + Zstandard/Deflate)
- .ecg: ISHNE 1.0 Holter Standard (Badilini 1998)
- .e3c: Excorde 3C Holter proprietary archive
- .hea / .dat: PhysioNet WFDB Benchmark Format (Format 16 and Format 212 bit-packed)
- .edf: European Data Format (EDF / EDF+)
- .mat: MATLAB Workspace files (.mat)
- .npy: NumPy binary array dumps
- .csv / .txt: Raw delimited tabular recordings
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from pyecg.io.mat_reader import load_mat_ecg
from pyecg.io.e3c_reader import read_e3c
from pyecg.io.pecg_format import load_pecg
from pyecg.io.ishne_reader import read_ishne
from pyecg.io.wfdb_reader import read_wfdb
from pyecg.io.edf_reader import read_edf


def load_ecg_file(
    filepath: Union[str, Path, os.PathLike[str]],
    lead_name_or_index: Union[str, int] = 0,
) -> np.ndarray:
    """Loads a single specified lead signal from any supported ECG recording format.

    Args:
        filepath: Path to the target recording.
        lead_name_or_index: Lead name (e.g. 'Lead I', 'Channel 1') or 0-based integer index.

    Returns:
        1D numpy array of float64 physical waveform voltage values.

    Raises:
        FileNotFoundError: If the recording file cannot be found.
        ValueError: If the file format is unsupported or the lead cannot be resolved.
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    # 1. Custom Portable Exchange Format (.pecg)
    if ext == ".pecg":
        meta, signals = load_pecg(path, mmap=False)
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, signals.shape[0] - 1)
            return signals[idx]
        channels = meta.get("recording", {}).get("channels", [])
        for ch in channels:
            if ch.get("name") == lead_name_or_index:
                return signals[ch["index"]]
        return signals[0]

    # 2. ISHNE Holter Output Standard (.ecg)
    elif ext == ".ecg":
        record = read_ishne(path)
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, record.num_leads - 1)
            return record.signals[idx]
        for idx, name in enumerate(record.lead_names):
            if name == lead_name_or_index:
                return record.signals[idx]
        return record.signals[0]

    # 3. Excorde 3C Holter Archive (.e3c)
    elif ext == ".e3c":
        e3c_data = read_e3c(path)
        signals = e3c_data["signals"]
        lead_names = e3c_data["lead_names"]
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, len(lead_names) - 1)
            return signals[lead_names[idx]]
        if lead_name_or_index in signals:
            return signals[lead_name_or_index]
        return next(iter(signals.values()))

    # 4. European Data Format (.edf)
    elif ext == ".edf":
        edf_rec = read_edf(path)
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, edf_rec.num_signals - 1)
            return edf_rec.signals[idx]
        for idx, name in enumerate(edf_rec.lead_names):
            if name == lead_name_or_index:
                return edf_rec.signals[idx]
        return edf_rec.signals[0]

    # 5. PhysioNet WFDB Format (.hea or .dat)
    elif ext in (".hea", ".dat"):
        wfdb_rec = read_wfdb(path)
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, wfdb_rec.num_signals - 1)
            return wfdb_rec.signals[idx]
        for idx, name in enumerate(wfdb_rec.lead_names):
            if name == lead_name_or_index:
                return wfdb_rec.signals[idx]
        return wfdb_rec.signals[0]

    # 6. MATLAB Format (.mat)
    elif ext == ".mat":
        mat_res = load_mat_ecg(str(path))
        signals = mat_res["signals"]
        lead_names = mat_res["lead_names"]
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, len(lead_names) - 1)
            return signals[lead_names[idx]]
        if lead_name_or_index in signals:
            return signals[lead_name_or_index]
        return next(iter(signals.values()))

    # 7. NumPy Array (.npy)
    elif ext == ".npy":
        arr = np.load(str(path))
        if arr.ndim > 1:
            idx = min(lead_name_or_index if isinstance(lead_name_or_index, int) else 0, arr.shape[0] - 1)
            return arr[idx]
        return arr

    # 8. Delimited Text (.csv, .txt)
    elif ext in (".csv", ".txt"):
        arr = np.loadtxt(str(path), delimiter="," if ext == ".csv" else None)
        if arr.ndim > 1:
            idx = min(lead_name_or_index if isinstance(lead_name_or_index, int) else 0, arr.shape[1] - 1)
            return arr[:, idx]
        return arr

    else:
        raise ValueError(
            f"Unsupported file format '{ext}'. PyECG supports: .pecg, .ecg (ISHNE), "
            ".e3c (Excorde 3C), .edf, .hea/.dat (WFDB), .mat, .npy, .csv, and .txt."
        )


def load_ecg_dataset(
    filepath: Union[str, Path, os.PathLike[str]],
) -> Tuple[Dict[str, np.ndarray], float, Dict[str, Any]]:
    """Loads all leads, sampling rate, and clinical metadata from any supported ECG file.

    Args:
        filepath: Path to the target recording.

    Returns:
        A tuple of (signals_dict, fs, metadata_dict):
            - signals_dict: Dict[str, np.ndarray] mapping lead names to 1D waveform arrays.
            - fs: Sampling frequency in Hertz.
            - metadata_dict: Comprehensive clinical and technical metadata.
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    if ext == ".pecg":
        meta, signals_matrix = load_pecg(path, mmap=False)
        channels = meta.get("recording", {}).get("channels", [])
        signals: Dict[str, np.ndarray] = {}
        for i, ch in enumerate(channels):
            name = ch.get("name", f"Lead {i+1}")
            signals[name] = signals_matrix[i]
        if not signals:
            for i in range(signals_matrix.shape[0]):
                signals[f"Lead {i+1}"] = signals_matrix[i]
        fs = float(meta.get("recording", {}).get("sampling_rate_hz", 250.0))
        return signals, fs, meta

    elif ext == ".ecg":
        rec = read_ishne(path)
        signals = {name: rec.signals[i] for i, name in enumerate(rec.lead_names)}
        meta = {
            "patient_id": rec.patient_id,
            "patient_first_name": rec.patient_first_name,
            "patient_last_name": rec.patient_last_name,
            "gender": rec.gender,
            "race": rec.race,
            "record_date": rec.record_date,
            "start_time": rec.start_time,
        }
        return signals, float(rec.sampling_rate), meta

    elif ext == ".e3c":
        e3c_res = read_e3c(path)
        return e3c_res["signals"], float(e3c_res["fs"]), {"annotations": e3c_res.get("annotations", {})}

    elif ext == ".edf":
        rec = read_edf(path)
        signals = {name: rec.signals[i] for i, name in enumerate(rec.lead_names)}
        meta = {
            "patient_id": rec.patient_id,
            "recording_id": rec.recording_id,
            "start_date": rec.start_date,
            "start_time": rec.start_time,
        }
        return signals, float(rec.sample_rates[0]) if rec.sample_rates else 250.0, meta

    elif ext in (".hea", ".dat"):
        rec = read_wfdb(path)
        signals = {name: rec.signals[i] for i, name in enumerate(rec.lead_names)}
        return signals, float(rec.sampling_rate), {"record_name": rec.record_name}

    elif ext == ".mat":
        mat_res = load_mat_ecg(path)
        return mat_res["signals"], float(mat_res["fs"]), mat_res["raw_metadata"]

    elif ext == ".npy":
        arr = np.load(str(path))
        if arr.ndim == 1:
            return {"Lead I": arr}, 250.0, {}
        signals = {f"Lead {i+1}": arr[i] for i in range(arr.shape[0])}
        return signals, 250.0, {}

    elif ext in (".csv", ".txt"):
        arr = np.loadtxt(str(path), delimiter="," if ext == ".csv" else None)
        if arr.ndim == 1:
            return {"Lead I": arr}, 250.0, {}
        signals = {f"Lead {i+1}": arr[:, i] for i in range(arr.shape[1])}
        return signals, 250.0, {}

    else:
        raise ValueError(f"Unsupported file format '{ext}'.")
