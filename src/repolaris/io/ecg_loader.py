"""Universal Multi-Format ECG Loader and Format Sniffer Module.

Supports automatic binary/XML header sniffing and unified ingestion for:
1. Repolaris Portable Clinical ECG (.pecg)
2. ISHNE 1.0 Standard Holter (.ecg)
3. Excorde 3C Holter Archive (.e3c)
4. European Data Format (.edf, .edf+)
5. PhysioNet WFDB (.hea, .dat)
6. DICOM Waveform (SOP Class 1.2.840.10008.5.1.4.1.1.9.1.1 / 9.1.2) (.dcm, .dicom)
7. HL7 Annotated ECG XML (ANSI/HL7 aECG) (.xml, .aecg)
8. SCP-ECG Standard (CEN EN 1064 / ISO 13713) (.scp)
9. NumPy Binary Array (.npy)
10. Delimited Text (.csv, .txt)

Also provides out-of-core `SignalBuffer`, `open_ecg_buffer()`, and `stream_ecg_chunks()`
for bounded-memory 24h-48h Holter streaming.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
import contextlib
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np

from repolaris.io.dicom_reader import is_dicom_file, read_dicom_waveform
from repolaris.io.e3c_reader import read_e3c
from repolaris.io.edf_reader import read_edf
from repolaris.io.hl7_reader import is_hl7_xml, read_hl7_aecg
from repolaris.io.ishne_reader import read_ishne
from repolaris.io.pecg_format import load_pecg
from repolaris.io.scp_reader import is_scp_file, read_scp_ecg
from repolaris.io.wfdb_reader import read_wfdb


_EXT_FORMAT_MAP: dict[str, str] = {
    ".pecg": "pecg",
    ".ecg": "ishne",
    ".e3c": "e3c",
    ".edf": "edf",
    ".edf+": "edf",
    ".hea": "wfdb",
    ".dat": "wfdb",
    ".dcm": "dicom",
    ".dicom": "dicom",
    ".xml": "hl7",
    ".aecg": "hl7",
    ".scp": "scp",
    ".npy": "npy",
    ".csv": "csv",
    ".txt": "csv",
}


def sniff_ecg_format(filepath: str | Path | os.PathLike[str]) -> str:
    """Inspects file magic bytes, XML namespaces, and extensions to determine the ECG format."""
    path = Path(filepath)
    ext = path.suffix.lower()

    if path.is_file() and path.stat().st_size >= 16:
        with contextlib.suppress(OSError):
            with open(path, "rb") as f:
                head16 = f.read(16)
            if head16.startswith(b"PECG"):
                return "pecg"
            if head16.startswith(b"ISHNE"):
                return "ishne"
            if head16.startswith(b"\x93NUMPY"):
                return "npy"
            if head16.startswith(b"0       ") and ext in {".edf", ".bdf"}:
                return "edf"

        if is_dicom_file(path):
            return "dicom"
        if is_scp_file(path):
            return "scp"
        if is_hl7_xml(path):
            return "hl7"

    return _EXT_FORMAT_MAP.get(ext, "unknown")


def _select_lead(signals: dict[str, np.ndarray], lead_name_or_index: str | int) -> np.ndarray:
    """Selects a 1D waveform array from a lead dictionary by integer index or channel name."""
    if not signals:
        return np.zeros(0, dtype=np.float32)
    keys = list(signals.keys())
    if isinstance(lead_name_or_index, int):
        idx = min(max(0, lead_name_or_index), len(keys) - 1)
        return signals[keys[idx]]
    if lead_name_or_index in signals:
        return signals[lead_name_or_index]
    return signals[keys[0]]


def load_ecg_file(
    filepath: str | Path | os.PathLike[str],
    lead_name_or_index: str | int = 0,
    progress_callback: Callable[[float, str], None] | None = None,
) -> np.ndarray:
    """Loads a single 1D lead waveform (in physical mV) from any supported clinical ECG format."""
    signals, _, _ = load_ecg_dataset(filepath, progress_callback=progress_callback)
    return _select_lead(signals, lead_name_or_index)


def load_ecg_dataset(
    filepath: str | Path | os.PathLike[str],
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[dict[str, np.ndarray], float, dict[str, Any]]:
    """Loads all leads, sampling rate, and clinical metadata from any supported ECG file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if progress_callback:
        progress_callback(0.10, f"Scanning container bounds for {path.name}...")

    file_size = path.stat().st_size
    if file_size > 2 * 1024**3:
        raise ValueError(
            f"Security Alert: File '{path.name}' ({file_size / 1e9:.2f} GB) exceeds the 2 GB maximum allowed size."
        )

    fmt = sniff_ecg_format(path)

    match fmt:
        case "pecg":
            meta, signals_matrix = load_pecg(path, mmap=False, progress_callback=progress_callback)
            channels = meta.get("recording", {}).get("channels", [])
            if progress_callback:
                progress_callback(0.85, "Calibrating multi-channel signals...")
            if channels:
                signals = {
                    ch.get("name", f"Lead {i + 1}"): signals_matrix[i]
                    for i, ch in enumerate(channels)
                }
            else:
                signals = {f"Lead {i + 1}": signals_matrix[i] for i in range(signals_matrix.shape[0])}
            rec_data = meta.get("recording", {})
            fs = float(rec_data.get("sampling_rate", rec_data.get("sampling_rate_hz", 250.0)))
            meta["format"] = "PECG (Portable Clinical ECG)"
            if progress_callback:
                progress_callback(1.0, f"Successfully loaded {len(signals)} leads from {path.name}.")
            return signals, fs, meta

        case "ishne":
            if progress_callback:
                progress_callback(0.35, "Reading ISHNE Holter binary record...")
            rec = read_ishne(path)
            if progress_callback:
                progress_callback(0.80, "Calibrating Holter leads...")
            signals = {name: rec.signals[i] for i, name in enumerate(rec.lead_names)}
            full_name = f"{rec.first_name} {rec.last_name}".strip() or "ANONYMOUS"
            meta = {
                "format": "ISHNE 1.0 Holter (.ecg)",
                "patient_id": rec.patient_id,
                "first_name": rec.first_name,
                "last_name": rec.last_name,
                "patient_first_name": rec.first_name,
                "patient_last_name": rec.last_name,
                "patient_name": full_name,
                "gender": rec.sex,
                "sex": rec.sex,
                "race": rec.race,
                "birth_date": str(rec.birth_date) if rec.birth_date else "",
                "age": rec.age_years,
                "record_date": str(rec.record_date) if rec.record_date else "",
                "start_time": str(rec.start_time) if rec.start_time else "",
                "pacemaker": rec.pacemaker_status,
                "clinical_notes": rec.clinical_notes,
                "duration_sec": rec.duration_sec,
            }
            if progress_callback:
                progress_callback(1.0, f"Successfully loaded {len(signals)} ISHNE leads.")
            return signals, float(rec.sampling_rate), meta

        case "dicom":
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
            if progress_callback:
                progress_callback(1.0, f"Successfully loaded {len(signals)} DICOM leads.")
            return signals, dcm_rec.sampling_rate, meta

        case "hl7":
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
            if progress_callback:
                progress_callback(1.0, f"Successfully loaded {len(signals)} HL7 leads.")
            return signals, hl7_rec.sampling_rate, meta

        case "scp":
            if progress_callback:
                progress_callback(0.35, "Decompressing SCP-ECG binary rhythm data...")
            scp_rec = read_scp_ecg(path)
            signals = {name: scp_rec.signals[i] for i, name in enumerate(scp_rec.lead_names)}
            meta = {
                "format": "SCP-ECG (CEN EN 1064 / ISO 13713)",
                "patient_id": scp_rec.patient_id,
                "patient_name": scp_rec.patient_name,
                "num_leads": scp_rec.num_leads,
                "duration_sec": scp_rec.num_samples / scp_rec.sampling_rate,
            }
            if progress_callback:
                progress_callback(1.0, f"Successfully loaded {len(signals)} SCP-ECG leads.")
            return signals, scp_rec.sampling_rate, meta

        case "e3c":
            e3c_res = read_e3c(path)
            if progress_callback:
                progress_callback(1.0, "Successfully loaded Excorde 3C archive.")
            return (
                e3c_res["signals"],
                float(e3c_res["fs"]),
                {
                    "format": "Fukuda Excorde 3C (.e3c)",
                    "duration_sec": e3c_res.get("duration_s", 0.0),
                    "annotations": e3c_res.get("annotations", {}),
                },
            )

        case "edf":
            if progress_callback:
                progress_callback(0.35, "Reading European Data Format telemetry...")
            edf_rec = read_edf(path)
            signals = {name: edf_rec.signals[i] for i, name in enumerate(edf_rec.lead_names)}
            meta = {
                "format": "European Data Format (EDF / EDF+)",
                "patient_id": edf_rec.patient_id,
                "recording_id": edf_rec.recording_id,
                "start_date": edf_rec.start_date,
                "start_time": edf_rec.start_time,
                "duration_sec": edf_rec.duration_sec,
            }
            fs_val = float(edf_rec.sampling_rates[0]) if edf_rec.sampling_rates else 250.0
            if progress_callback:
                progress_callback(1.0, f"Successfully loaded {len(signals)} EDF leads.")
            return signals, fs_val, meta

        case "wfdb":
            if progress_callback:
                progress_callback(0.35, "Decoding PhysioNet WFDB record...")
            wfdb_rec = read_wfdb(path)
            signals = {name: wfdb_rec.signals[i] for i, name in enumerate(wfdb_rec.lead_names)}
            if progress_callback:
                progress_callback(1.0, f"Successfully loaded {len(signals)} WFDB leads.")
            return (
                signals,
                float(wfdb_rec.sampling_rate),
                {
                    "format": "PhysioNet WFDB (.hea / .dat)",
                    "record_name": wfdb_rec.record_name,
                    "patient_id": wfdb_rec.record_name,
                    "duration_sec": (
                        wfdb_rec.num_samples / wfdb_rec.sampling_rate
                        if wfdb_rec.sampling_rate > 0
                        else 0.0
                    ),
                },
            )

        case "npy":
            arr = np.load(str(path), allow_pickle=False)
            if arr.ndim == 1:
                signals = {"Lead I": arr}
            else:
                signals = {f"Lead {i + 1}": arr[i] for i in range(arr.shape[0])}
            if progress_callback:
                progress_callback(1.0, f"Successfully loaded {len(signals)} NumPy leads.")
            return signals, 250.0, {"format": "NumPy Array (.npy)"}

        case "csv":
            if file_size > 250 * 1024 * 1024:
                raise ValueError(
                    f"Security Alert: Delimited text file '{path.name}' exceeds the 250 MB ceiling."
                )
            arr = np.loadtxt(str(path), delimiter="," if path.suffix.lower() == ".csv" else None)
            if arr.ndim == 1:
                signals = {"Lead I": arr}
            else:
                signals = {f"Lead {i + 1}": arr[:, i] for i in range(arr.shape[1])}
            if progress_callback:
                progress_callback(1.0, f"Successfully loaded {len(signals)} CSV leads.")
            return signals, 250.0, {"format": f"Delimited Matrix ({path.suffix})"}

        case _:
            raise ValueError(
                f"Unsupported file format '{path.suffix}'. Repolaris supports: .pecg, .ecg (ISHNE), "
                ".dcm (DICOM Waveform), .xml/.aecg (HL7 aECG), .scp (SCP-ECG), .edf, .hea/.dat (WFDB), "
                ".e3c (Excorde 3C), .npy, .csv, and .txt."
            )


class SignalBuffer:
    """Out-of-core signal buffer wrapping an in-memory ndarray or disk-backed np.memmap."""

    def __init__(
        self,
        signals: dict[str, np.ndarray],
        fs: float,
        metadata: dict[str, Any],
        temp_mmap_dir: str | None = None,
    ) -> None:
        self.signals = signals
        self.fs = fs
        self.metadata = metadata
        self._temp_mmap_dir = temp_mmap_dir

    @property
    def lead_names(self) -> list[str]:
        return list(self.signals.keys())

    @property
    def num_leads(self) -> int:
        return len(self.signals)

    @property
    def num_samples(self) -> int:
        if not self.signals:
            return 0
        first = next(iter(self.signals.values()))
        return int(len(first))

    @property
    def duration_sec(self) -> float:
        return float(self.num_samples / self.fs) if self.fs > 0 else 0.0

    def get_slice(self, lead: str | int, start_sample: int, end_sample: int) -> np.ndarray:
        """Returns a contiguous 1D float32 slice for the specified lead."""
        arr = _select_lead(self.signals, lead)
        if len(arr) == 0:
            return arr
        s = max(0, int(start_sample))
        e = min(len(arr), int(end_sample))
        return np.asarray(arr[s:e], dtype=np.float32)

    def close(self) -> None:
        """Releases any open memory-mapped files and removes temporary backing directories."""
        if self._temp_mmap_dir and os.path.isdir(self._temp_mmap_dir):
            for arr in self.signals.values():
                if isinstance(arr, np.memmap) and getattr(arr, "_mmap", None) is not None:
                    with contextlib.suppress(Exception):
                        arr._mmap.close()
            shutil.rmtree(self._temp_mmap_dir, ignore_errors=True)
            self._temp_mmap_dir = None

    def __enter__(self) -> SignalBuffer:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()


def open_ecg_buffer(
    filepath: str | Path | os.PathLike[str],
    mmap_threshold_samples: int = 1_800_000,
    progress_callback: Callable[[float, str], None] | None = None,
) -> SignalBuffer:
    """Opens an ECG recording into a SignalBuffer, backing large multi-hour signals with np.memmap."""
    path = Path(filepath)
    fmt = sniff_ecg_format(path)
    if fmt == "pecg":
        with contextlib.suppress(Exception):
            meta, sig_mat = load_pecg(path, mmap=True, progress_callback=progress_callback)
            channels = meta.get("recording", {}).get("channels", [])
            sigs = {
                (channels[i].get("name", f"Lead {i + 1}") if i < len(channels) else f"Lead {i + 1}"): sig_mat[i]
                for i in range(sig_mat.shape[0])
            }
            fs = float(meta.get("recording", {}).get("sampling_rate", 500.0))
            meta["mmap_backed"] = isinstance(sig_mat, np.memmap)
            return SignalBuffer(sigs, fs, meta)

    signals, fs, meta = load_ecg_dataset(path, progress_callback=progress_callback)
    first_len = len(next(iter(signals.values()))) if signals else 0

    if first_len >= mmap_threshold_samples:
        tmp_dir = tempfile.mkdtemp(prefix="repolaris_mmap_")
        mmap_signals: dict[str, np.ndarray] = {}
        for idx, (lname, arr) in enumerate(signals.items()):
            mmap_path = os.path.join(tmp_dir, f"lead_{idx}.dat")
            mm = np.memmap(mmap_path, dtype=np.float32, mode="w+", shape=arr.shape)
            mm[:] = arr[:]
            mm.flush()
            mmap_signals[lname] = mm
        meta["mmap_backed"] = True
        return SignalBuffer(mmap_signals, fs, meta, temp_mmap_dir=tmp_dir)

    meta["mmap_backed"] = False
    return SignalBuffer(signals, fs, meta)


def stream_ecg_chunks(
    filepath: str | Path | os.PathLike[str],
    lead_name_or_index: str | int = 0,
    chunk_duration_sec: float = 300.0,
    overlap_sec: float = 5.0,
    progress_callback: Callable[[float, str], None] | None = None,
) -> Iterator[dict[str, Any]]:
    """Generator yielding overlapping waveform chunks for bounded-memory 24h-48h Holter streaming."""
    with open_ecg_buffer(filepath, progress_callback=progress_callback) as buf:
        fs = buf.fs
        total_samples = buf.num_samples
        chunk_samples = max(1, int(round(chunk_duration_sec * fs)))
        overlap_samples = max(0, int(round(overlap_sec * fs)))

        core_start = 0
        chunk_idx = 0
        while core_start < total_samples:
            core_end = min(total_samples, core_start + chunk_samples)
            win_start = max(0, core_start - overlap_samples)
            win_end = min(total_samples, core_end + overlap_samples)

            yield {
                "chunk_index": chunk_idx,
                "start_sample": win_start,
                "end_sample": win_end,
                "core_start_sample": core_start,
                "core_end_sample": core_end,
                "signal": buf.get_slice(lead_name_or_index, win_start, win_end),
                "fs": fs,
                "total_samples": total_samples,
                "metadata": buf.metadata,
            }
            core_start = core_end
            chunk_idx += 1
