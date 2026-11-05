"""Universal ECG File Ingestion Router module.

Provides a unified interface to automatically detect format signatures and ingest
electrocardiogram recordings across all clinical, academic, and device formats:
- .pecg: PyECG Portable Clinical Exchange Package (CBOR/JSON + Zstandard/Deflate)
- .ecg: ISHNE 1.0 Holter Standard (Badilini 1998)
- .e3c: Excorde 3C Holter proprietary archive
- .hea / .dat: PhysioNet WFDB Benchmark Format (Format 16 and Format 212 bit-packed)
- .edf: European Data Format (EDF / EDF+)
- .dcm / .dicom: DICOM Waveform (SOP Class 1.2.840.10008.5.1.4.1.1.9.1.1 / 9.1.2)
- .xml / .aecg: HL7 Annotated ECG XML (ANSI/HL7 aECG FDA standard)
- .scp: SCP-ECG Standard Communication Protocol (CEN EN 1064 / ISO 13713)
- .npy: NumPy binary array dumps
- .csv / .txt: Raw delimited tabular recordings
"""

from __future__ import annotations

import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import numpy as np

from repolaris.io.e3c_reader import read_e3c
from repolaris.io.pecg_format import load_pecg
from repolaris.io.ishne_reader import read_ishne
from repolaris.io.wfdb_reader import read_wfdb
from repolaris.io.edf_reader import read_edf
from repolaris.io.dicom_reader import read_dicom_waveform, is_dicom_file
from repolaris.io.hl7_reader import read_hl7_aecg, is_hl7_xml
from repolaris.io.scp_reader import read_scp_ecg, is_scp_file


def sniff_ecg_format(filepath: Union[str, Path, os.PathLike[str]]) -> str:
    """Sniffs file content headers and magic bytes to determine the exact ECG format.

    Returns one of: 'pecg', 'dicom', 'hl7', 'scp', 'ishne', 'edf', 'wfdb', 'e3c', 'npy', 'csv', or 'unknown'.
    """
    path = Path(filepath)
    if not path.is_file():
        return "unknown"

    ext = path.suffix.lower()

    # 1. Magic byte / structural sniffing
    if is_dicom_file(path) or ext in (".dcm", ".dicom"):
        return "dicom"
    if is_scp_file(path) or ext == ".scp":
        return "scp"
    if is_hl7_xml(path) or ext in (".xml", ".aecg"):
        return "hl7"

    # 2. Extension-based routing
    if ext == ".pecg":
        return "pecg"
    elif ext == ".ecg":
        return "ishne"
    elif ext == ".e3c":
        return "e3c"
    elif ext == ".edf":
        return "edf"
    elif ext in (".hea", ".dat"):
        return "wfdb"
    elif ext == ".npy":
        return "npy"
    elif ext in (".csv", ".txt"):
        return "csv"

    return "unknown"


def load_ecg_file(
    filepath: Union[str, Path, os.PathLike[str]],
    lead_name_or_index: Union[str, int] = 0,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> np.ndarray:
    """Loads a single specified lead signal from any supported ECG recording format.

    Args:
        filepath: Path to the target recording.
        lead_name_or_index: Lead name (e.g. 'Lead I', 'Channel 1') or 0-based integer index.

    Returns:
        1D numpy array of float32/float64 physical waveform voltage values in millivolts.

    Raises:
        FileNotFoundError: If the recording file cannot be found.
        ValueError: If the file format is unsupported or the lead cannot be resolved.
    """
    path = Path(filepath)
    fmt = sniff_ecg_format(path)
    if progress_callback:
        progress_callback(0.15, f"Opening {path.name} ({fmt.upper()})...")

    # 1. Custom Portable Exchange Format (.pecg)
    if fmt == "pecg":
        meta, signals = load_pecg(path, mmap=False, progress_callback=progress_callback)
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, signals.shape[0] - 1)
            return signals[idx]
        channels = meta.get("recording", {}).get("channels", [])
        for ch in channels:
            if ch.get("name") == lead_name_or_index:
                return signals[ch["index"]]
        return signals[0]

    # 2. ISHNE Holter Output Standard (.ecg)
    elif fmt == "ishne":
        record = read_ishne(path)
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, record.num_leads - 1)
            return record.signals[idx]
        for idx, name in enumerate(record.lead_names):
            if name == lead_name_or_index:
                return record.signals[idx]
        return record.signals[0]

    # 3. Excorde 3C Holter Archive (.e3c)
    elif fmt == "e3c":
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
    elif fmt == "edf":
        edf_rec = read_edf(path)
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, edf_rec.num_signals - 1)
            return edf_rec.signals[idx]
        for idx, name in enumerate(edf_rec.lead_names):
            if name == lead_name_or_index:
                return edf_rec.signals[idx]
        return edf_rec.signals[0]

    # 5. PhysioNet WFDB Format (.hea or .dat)
    elif fmt == "wfdb":
        wfdb_rec = read_wfdb(path)
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, wfdb_rec.num_signals - 1)
            return wfdb_rec.signals[idx]
        for idx, name in enumerate(wfdb_rec.lead_names):
            if name == lead_name_or_index:
                return wfdb_rec.signals[idx]
        return wfdb_rec.signals[0]

    # 6. DICOM Waveform (SOP Class 1.2.840.10008.5.1.4.1.1.9.1.1 / 9.1.2)
    elif fmt == "dicom":
        dcm_rec = read_dicom_waveform(path)
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, dcm_rec.num_channels - 1)
            return dcm_rec.signals[idx]
        for idx, name in enumerate(dcm_rec.lead_names):
            if name == lead_name_or_index:
                return dcm_rec.signals[idx]
        return dcm_rec.signals[0]

    # 7. HL7 aECG XML Standard
    elif fmt == "hl7":
        hl7_rec = read_hl7_aecg(path)
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, hl7_rec.num_leads - 1)
            return hl7_rec.signals[idx]
        for idx, name in enumerate(hl7_rec.lead_names):
            if name == lead_name_or_index:
                return hl7_rec.signals[idx]
        return hl7_rec.signals[0]

    # 8. SCP-ECG Standard (CEN EN 1064)
    elif fmt == "scp":
        scp_rec = read_scp_ecg(path)
        if isinstance(lead_name_or_index, int):
            idx = min(lead_name_or_index, scp_rec.num_leads - 1)
            return scp_rec.signals[idx]
        for idx, name in enumerate(scp_rec.lead_names):
            if name == lead_name_or_index:
                return scp_rec.signals[idx]
        return scp_rec.signals[0]

    # 9. NumPy Array (.npy)
    elif fmt == "npy":
        arr = np.load(str(path), allow_pickle=False)
        if arr.ndim > 1:
            idx = min(lead_name_or_index if isinstance(lead_name_or_index, int) else 0, arr.shape[0] - 1)
            return arr[idx]
        return arr

    # 10. Delimited Text (.csv, .txt)
    elif fmt == "csv":
        arr = np.loadtxt(str(path), delimiter="," if path.suffix.lower() == ".csv" else None)
        if arr.ndim > 1:
            idx = min(lead_name_or_index if isinstance(lead_name_or_index, int) else 0, arr.shape[1] - 1)
            return arr[:, idx]
        return arr

    else:
        raise ValueError(
            f"Unsupported file format '{path.suffix}'. Repolaris supports: .pecg, .ecg (ISHNE), "
            ".dcm (DICOM Waveform), .xml/.aecg (HL7 aECG), .scp (SCP-ECG), .edf, .hea/.dat (WFDB), "
            ".e3c (Excorde 3C), .npy, .csv, and .txt."
        )


def load_ecg_dataset(
    filepath: Union[str, Path, os.PathLike[str]],
    progress_callback: Optional[Callable[[float, str], None]] = None,
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
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if progress_callback:
        progress_callback(0.10, f"Scanning container bounds for {path.name}...")

    file_size = path.stat().st_size
    if file_size > 2 * 1024**3:
        raise ValueError(f"Security Alert: File '{path.name}' ({file_size / 1e9:.2f} GB) exceeds the 2 GB maximum allowed size.")

    fmt = sniff_ecg_format(path)

    if fmt == "pecg":
        meta, signals_matrix = load_pecg(path, mmap=False, progress_callback=progress_callback)
        channels = meta.get("recording", {}).get("channels", [])
        signals: Dict[str, np.ndarray] = {}
        if progress_callback:
            progress_callback(0.85, "Calibrating multi-channel signals in parallel...")
        def _extract_ch(item):
            i, ch = item
            name = ch.get("name", f"Lead {i+1}")
            return name, signals_matrix[i]
        if channels:
            with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 1, 4)) as pool:
                for name, sig in pool.map(_extract_ch, enumerate(channels)):
                    signals[name] = sig
        else:
            def _extract_idx(i):
                return f"Lead {i+1}", signals_matrix[i]
            with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 1, 4)) as pool:
                for name, sig in pool.map(_extract_idx, range(signals_matrix.shape[0])):
                    signals[name] = sig
        rec_data = meta.get("recording", {})
        fs = float(rec_data.get("sampling_rate", rec_data.get("sampling_rate_hz", 250.0)))
        meta["format"] = "PECG (Portable Clinical ECG)"
        if progress_callback:
            progress_callback(1.0, f"Successfully loaded {len(signals)} leads from {path.name}.")
        return signals, fs, meta

    elif fmt == "ishne":
        if progress_callback:
            progress_callback(0.35, "Reading ISHNE Holter binary record...")
        rec = read_ishne(path)
        if progress_callback:
            progress_callback(0.80, "Calibrating Holter leads in parallel...")
        def _extract_ishne(item):
            i, name = item
            return name, rec.signals[i]
        with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 1, 4)) as pool:
            signals = dict(pool.map(_extract_ishne, enumerate(rec.lead_names)))
        meta = {
            "format": "ISHNE 1.0 Holter (.ecg)",
            "patient_id": rec.patient_id,
            "patient_first_name": rec.patient_first_name,
            "patient_last_name": rec.patient_last_name,
            "gender": rec.sex,
            "race": rec.race,
            "birth_date": rec.birth_date,
            "age": rec.age_years,
            "record_date": rec.record_date,
            "start_time": rec.start_time,
            "pacemaker": rec.pacemaker_status,
            "clinical_notes": rec.clinical_notes,
            "duration_sec": rec.duration_sec,
        }
        return signals, float(rec.sampling_rate), meta

    elif fmt == "dicom":
        if progress_callback:
            progress_callback(0.35, "Decoding DICOM Waveform SOP object...")
        dcm_rec = read_dicom_waveform(path)
        signals = {name: dcm_rec.signals[i] for i, name in enumerate(dcm_rec.lead_names)}
        meta = {
            "format": "DICOM Waveform (ISO 12052)",
            "patient_id": dcm_rec.patient_id,
            "patient_name": dcm_rec.patient_name,
            "study_date": dcm_rec.study_date,
            "study_time": dcm_rec.study_time,
            "num_channels": dcm_rec.num_channels,
            "duration_sec": dcm_rec.num_samples / dcm_rec.sampling_rate,
        }
        return signals, dcm_rec.sampling_rate, meta

    elif fmt == "hl7":
        if progress_callback:
            progress_callback(0.35, "Parsing HL7 aECG XML series...")
        hl7_rec = read_hl7_aecg(path)
        signals = {name: hl7_rec.signals[i] for i, name in enumerate(hl7_rec.lead_names)}
        meta = {
            "format": "HL7 Annotated ECG XML (ANSI/HL7 aECG)",
            "patient_id": hl7_rec.patient_id,
            "patient_name": hl7_rec.patient_name,
            "study_id": hl7_rec.study_id,
            "effective_time": hl7_rec.effective_time,
            "duration_sec": hl7_rec.num_samples / hl7_rec.sampling_rate,
        }
        return signals, hl7_rec.sampling_rate, meta

    elif fmt == "scp":
        if progress_callback:
            progress_callback(0.35, "Decompressing SCP-ECG binary rhythm data...")
        scp_rec = read_scp_ecg(path)
        signals = {name: scp_rec.signals[i] for i, name in enumerate(scp_rec.lead_names)}
        meta = {
            "format": "SCP-ECG (CEN EN 1064 / ISO 13713)",
            "num_leads": scp_rec.num_leads,
            "duration_sec": scp_rec.num_samples / scp_rec.sampling_rate,
        }
        return signals, scp_rec.sampling_rate, meta

    elif fmt == "e3c":
        e3c_res = read_e3c(path)
        return e3c_res["signals"], float(e3c_res["fs"]), {"format": "Fukuda Excorde 3C (.e3c)", "duration_sec": e3c_res.get("duration_s", 0.0), "annotations": e3c_res.get("annotations", {})}

    elif fmt == "edf":
        if progress_callback:
            progress_callback(0.35, "Reading European Data Format telemetry...")
        rec = read_edf(path)
        def _extract_edf(item):
            i, name = item
            return name, rec.signals[i]
        with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 1, 4)) as pool:
            signals = dict(pool.map(_extract_edf, enumerate(rec.lead_names)))
        meta = {
            "format": "European Data Format (EDF / EDF+)",
            "patient_id": rec.patient_id,
            "recording_id": rec.recording_id,
            "start_date": rec.start_date,
            "start_time": rec.start_time,
            "duration_sec": rec.duration_sec,
        }
        return signals, float(rec.sample_rates[0]) if rec.sample_rates else 250.0, meta

    elif fmt == "wfdb":
        if progress_callback:
            progress_callback(0.35, "Decoding PhysioNet WFDB record...")
        rec = read_wfdb(path)
        def _extract_wfdb(item):
            i, name = item
            return name, rec.signals[i]
        with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 1, 4)) as pool:
            signals = dict(pool.map(_extract_wfdb, enumerate(rec.lead_names)))
        return signals, float(rec.sampling_rate), {"format": "PhysioNet WFDB (.hea / .dat)", "record_name": rec.record_name, "patient_id": rec.record_name}

    elif fmt == "npy":
        arr = np.load(str(path), allow_pickle=False)
        if arr.ndim == 1:
            signals = {"Lead I": arr}
        else:
            def _extract_npy(i):
                return f"Lead {i+1}", arr[i]
            with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 1, 4)) as pool:
                signals = dict(pool.map(_extract_npy, range(arr.shape[0])))
        return signals, 250.0, {"format": "NumPy Array (.npy)"}

    elif fmt == "csv":
        if file_size > 250 * 1024 * 1024:
            raise ValueError(f"Security Alert: Delimited text file '{path.name}' exceeds the 250 MB ceiling.")
        arr = np.loadtxt(str(path), delimiter="," if path.suffix.lower() == ".csv" else None)
        if arr.ndim == 1:
            signals = {"Lead I": arr}
        else:
            def _extract_csv(i):
                return f"Lead {i+1}", arr[:, i]
            with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 1, 4)) as pool:
                signals = dict(pool.map(_extract_csv, range(arr.shape[1])))
        return signals, 250.0, {"format": "Delimited Matrix (" + path.suffix + ")"}

    else:
        raise ValueError(f"Unsupported file format '{path.suffix}'.")
