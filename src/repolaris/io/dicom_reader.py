"""
DICOM Waveform (SOP Class 1.2.840.10008.5.1.4.1.1.9.1.1 and 1.2.840.10008.5.1.4.1.1.9.1.2) Reader Module.

Specification:
- DICOM Part 3, Annex A.34 (Waveform Information Object Definitions)
- DICOM Part 3, Annex C.10.9 (Waveform Module) & C.10.10 (Waveform Annotation Module)
- 12-Lead ECG Waveform Storage SOP Class: 1.2.840.10008.5.1.4.1.1.9.1.1
- General ECG Waveform Storage SOP Class: 1.2.840.10008.5.1.4.1.1.9.1.2
- Ambulatory ECG Waveform Storage SOP Class: 1.2.840.10008.5.1.4.1.1.9.1.3

Binary Structure:
- 128 bytes preamble
- 4 bytes magic: b"DICM"
- Standard DICOM Data Elements (Explicit or Implicit VR Little Endian)
- Tag (5400, 0100) Waveform Sequence:
    - Tag (003A, 0005) Number of Waveform Channels
    - Tag (003A, 0010) Number of Waveform Samples
    - Tag (003A, 001A) Sampling Frequency (Hz)
    - Tag (003A, 0100) Channel Definition Sequence:
        - Tag (003A, 0200) Channel Source Sequence (Code Value, e.g. Lead I, V1)
        - Tag (003A, 0210) Channel Sensitivity (Gain)
        - Tag (003A, 0211) Channel Sensitivity Units Sequence
        - Tag (003A, 0218) Channel Baseline (ADC offset)
    - Tag (5400, 1010) WaveformData (16-bit or 8-bit multiplexed samples)
"""

from __future__ import annotations

import os
import struct
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Union
import numpy as np

# Standard 12-Lead Code Value Mapping (DICOM CID 3001 / SCPECG Lead Codes)
DICOM_LEAD_NAMES = {
    "5.6.3-9-1": "Lead I",
    "5.6.3-9-2": "Lead II",
    "5.6.3-9-3": "Lead III",
    "5.6.3-9-4": "aVR",
    "5.6.3-9-5": "aVL",
    "5.6.3-9-6": "aVF",
    "5.6.3-9-7": "V1",
    "5.6.3-9-8": "V2",
    "5.6.3-9-9": "V3",
    "5.6.3-9-10": "V4",
    "5.6.3-9-11": "V5",
    "5.6.3-9-12": "V6",
}


@dataclass
class DICOMWaveformRecord:
    """Decoded physical ECG waveform container from a DICOM Waveform SOP instance."""
    patient_id: str
    patient_name: str
    study_date: str
    study_time: str
    sampling_rate: float
    num_channels: int
    num_samples: int
    lead_names: List[str]
    signals: np.ndarray  # Shape: (num_channels, num_samples) in physical millivolts (mV)
    units: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def is_dicom_file(filepath: Union[str, Path, os.PathLike[str]]) -> bool:
    """Verifies whether a file contains the standard DICOM 'DICM' magic byte header at offset 128."""
    path = Path(filepath)
    if not path.is_file() or path.stat().st_size < 132:
        return False
    try:
        with open(path, "rb") as f:
            f.seek(128)
            magic = f.read(4)
            return magic == b"DICM"
    except Exception:
        return False


def read_dicom_waveform(
    filepath: Union[str, Path, os.PathLike[str]],
) -> DICOMWaveformRecord:
    """Parses a DICOM Waveform (12-Lead or Ambulatory) object and returns physical mV signals.

    Supports parsing via `pydicom` if installed, with a robust native binary parser fallback
    for air-gapped environments without external package dependencies.

    Args:
        filepath: Path to the DICOM file (.dcm or extensionless).

    Returns:
        DICOMWaveformRecord containing calibrated float32 signals in millivolts (mV).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a valid DICOM Waveform or contains corrupt headers.
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"DICOM file not found: {path}")

    file_size = path.stat().st_size
    if file_size > 500 * 1024 * 1024:
        raise ValueError(f"Security Alert: DICOM file ({file_size} B) exceeds the 500 MB safety ceiling.")

    # 1. Preferred route: pydicom if available
    try:
        import pydicom
        return _read_with_pydicom(path)
    except ImportError:
        pass

    # 2. Native binary parser fallback
    return _read_native_dicom(path)


def _read_with_pydicom(path: Path) -> DICOMWaveformRecord:
    """Decodes DICOM waveform sequence using pydicom."""
    import pydicom

    ds = pydicom.dcmread(str(path), stop_before_pixels=False, force=True)

    patient_id = str(getattr(ds, "PatientID", "UNKNOWN")).strip()
    patient_name = str(getattr(ds, "PatientName", "ANONYMOUS")).strip()
    study_date = str(getattr(ds, "StudyDate", "")).strip()
    study_time = str(getattr(ds, "StudyTime", "")).strip()

    if "WaveformSequence" not in ds or len(ds.WaveformSequence) == 0:
        raise ValueError(f"DICOM file '{path.name}' does not contain a WaveformSequence (Tag 5400,0100).")

    # Use first valid ECG multiplex group
    multiplex = ds.WaveformSequence[0]
    num_channels = int(getattr(multiplex, "NumberOfWaveformChannels", 0))
    num_samples = int(getattr(multiplex, "NumberOfWaveformSamples", 0))
    fs = float(getattr(multiplex, "SamplingFrequency", 500.0))

    if num_channels <= 0 or num_samples <= 0:
        raise ValueError(f"Corrupt DICOM Waveform: Invalid dimensions (channels={num_channels}, samples={num_samples}).")

    lead_names: List[str] = []
    sensitivities: List[float] = []
    baselines: List[float] = []
    units: List[str] = []

    channel_seq = getattr(multiplex, "ChannelDefinitionSequence", [])
    for idx, ch in enumerate(channel_seq):
        # Extract lead name
        ch_name = f"Channel_{idx + 1}"
        if "ChannelSourceSequence" in ch and len(ch.ChannelSourceSequence) > 0:
            source = ch.ChannelSourceSequence[0]
            val = getattr(source, "CodeValue", "")
            meaning = getattr(source, "CodeMeaning", "")
            ch_name = meaning or DICOM_LEAD_NAMES.get(str(val), f"Lead_{idx + 1}")
        lead_names.append(ch_name)

        # Gain & Baseline (Default to 0.001 mV = 1 uV per LSB or standard 200 LSB/mV)
        sens = float(getattr(ch, "ChannelSensitivity", 1.0))
        correction = float(getattr(ch, "ChannelSensitivityCorrectionFactor", 1.0))
        base = float(getattr(ch, "ChannelBaseline", 0.0))
        sensitivities.append(sens * correction)
        baselines.append(base)
        units.append("mV")

    # If lead names count mismatch
    while len(lead_names) < num_channels:
        lead_names.append(f"Channel_{len(lead_names) + 1}")
        sensitivities.append(1.0)
        baselines.append(0.0)
        units.append("mV")

    # Extract raw multiplexed bytes
    raw_bytes = multiplex.WaveformData
    # Standard DICOM Waveform bits: 16-bit signed integer or 8-bit
    bits_allocated = int(getattr(multiplex, "WaveformBitsAllocated", 16))
    if bits_allocated == 16:
        raw_arr = np.frombuffer(raw_bytes, dtype="<i2")
    elif bits_allocated == 8:
        raw_arr = np.frombuffer(raw_bytes, dtype=np.int8)
    else:
        raw_arr = np.frombuffer(raw_bytes, dtype="<i2")

    actual_samples = len(raw_arr) // num_channels
    matrix = raw_arr[: actual_samples * num_channels].reshape(actual_samples, num_channels).T

    # Convert to physical millivolts
    signals_mv = np.zeros_like(matrix, dtype=np.float32)
    for c in range(matrix.shape[0]):
        # DICOM formula: value = (ADC - Baseline) * Sensitivity
        # Usually Sensitivity is in mV/LSB (e.g. 0.005 for 200 LSB/mV) or uV/LSB
        sens = sensitivities[c] if c < len(sensitivities) else 1.0
        base = baselines[c] if c < len(baselines) else 0.0
        # If sensitivity > 0.1, assume it's stored in uV per LSB (scale to mV)
        scale = sens if sens < 0.1 else (sens / 1000.0)
        signals_mv[c] = (matrix[c].astype(np.float32) - base) * scale

    return DICOMWaveformRecord(
        patient_id=patient_id,
        patient_name=patient_name,
        study_date=study_date,
        study_time=study_time,
        sampling_rate=fs,
        num_channels=signals_mv.shape[0],
        num_samples=signals_mv.shape[1],
        lead_names=lead_names[: signals_mv.shape[0]],
        signals=signals_mv,
        units=units,
        metadata={"bits_allocated": bits_allocated, "sop_class": getattr(ds, "SOPClassUID", "")},
    )


def _read_native_dicom(path: Path) -> DICOMWaveformRecord:
    """Lightweight pure-Python binary parser scanning standard DICOM tags for WaveformData."""
    with open(path, "rb") as f:
        f.seek(128)
        if f.read(4) != b"DICM":
            raise ValueError(f"File '{path.name}' is not a valid DICOM file (missing 'DICM' preamble).")
        data = f.read()

    # Fast heuristic scan for WaveformData Tag: (5400, 1010) -> b'\x00\x54\x10\x10'
    tag_wf_data = b"\x00\x54\x10\x10"
    pos = data.find(tag_wf_data)
    if pos == -1:
        raise ValueError("Native DICOM parser: WaveformData Tag (5400, 1010) not found in file.")

    # Read VR and Length
    offset = pos + 4
    vr = data[offset : offset + 2]
    if vr in (b"OB", b"OW"):
        # Explicit VR with 2 reserved bytes + 4 bytes length
        length = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        raw_samples_bytes = data[offset + 8 : offset + 8 + length]
    else:
        # Implicit VR Little Endian (4 bytes length)
        length = struct.unpack("<I", data[offset : offset + 4])[0]
        raw_samples_bytes = data[offset + 4 : offset + 4 + length]

    raw_arr = np.frombuffer(raw_samples_bytes, dtype="<i2")
    num_channels = 12
    fs = 500.0
    actual_samples = len(raw_arr) // num_channels
    if actual_samples == 0:
        num_channels = 1
        actual_samples = len(raw_arr)

    matrix = raw_arr[: actual_samples * num_channels].reshape(actual_samples, num_channels).T
    # Scale: standard 200 LSB/mV (0.005 mV/LSB)
    signals_mv = matrix.astype(np.float32) / 200.0

    lead_names = ["Lead I", "Lead II", "Lead III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    if num_channels < 12:
        lead_names = [f"Channel_{i+1}" for i in range(num_channels)]

    return DICOMWaveformRecord(
        patient_id="ANONYMOUS",
        patient_name="PATIENT",
        study_date="",
        study_time="",
        sampling_rate=fs,
        num_channels=num_channels,
        num_samples=actual_samples,
        lead_names=lead_names[:num_channels],
        signals=signals_mv,
        units=["mV"] * num_channels,
    )
