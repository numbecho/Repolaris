"""
HL7 aECG (Annotated ECG XML) Reader Module.

Specification:
- ANSI/HL7 aECG Standard: Health Level Seven Annotated ECG Release 1.0 / 2.0
- FDA Cardiotoxicity & Thorough QT (TQT) trial data exchange specification
- XML Structure:
    - Root: <AnnotatedECG xmlns="urn:hl7-org:v3">
    - Patient Demographics: <clinicalDocument> / <recordTarget>
    - Component Waveforms: <component> / <series> / <sequence>
        - <code code="MDC_ECG_LEAD_I" ... />
        - <value xsi:type="GLIST_PQ"> or space-delimited text list <digits>
        - Increment / Sampling frequency (<increment value="0.002" unit="s"/> = 500 Hz)
        - Scale / Units (<scale value="0.005" unit="mV"/>)
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Union
import numpy as np


# Standard HL7 / IEEE 11073-10102 MDC_ECG Lead Code Mapping
HL7_LEAD_NAMES = {
    "MDC_ECG_LEAD_I": "Lead I",
    "MDC_ECG_LEAD_II": "Lead II",
    "MDC_ECG_LEAD_III": "Lead III",
    "MDC_ECG_LEAD_AVR": "aVR",
    "MDC_ECG_LEAD_AVL": "aVL",
    "MDC_ECG_LEAD_AVF": "aVF",
    "MDC_ECG_LEAD_V1": "V1",
    "MDC_ECG_LEAD_V2": "V2",
    "MDC_ECG_LEAD_V3": "V3",
    "MDC_ECG_LEAD_V4": "V4",
    "MDC_ECG_LEAD_V5": "V5",
    "MDC_ECG_LEAD_V6": "V6",
    "MDC_ECG_LEAD_X": "Lead X",
    "MDC_ECG_LEAD_Y": "Lead Y",
    "MDC_ECG_LEAD_Z": "Lead Z",
}


@dataclass
class HL7Record:
    """Decoded physiological signals and clinical trial metadata from an HL7 aECG XML document."""
    patient_id: str
    patient_name: str
    study_id: str
    effective_time: str
    sampling_rate: float
    num_leads: int
    num_samples: int
    lead_names: List[str]
    signals: np.ndarray  # Shape: (num_leads, num_samples) in physical millivolts (mV)
    units: List[str] = field(default_factory=list)


def is_hl7_xml(filepath: Union[str, Path, os.PathLike[str]]) -> bool:
    """Verifies whether a file is an HL7 Annotated ECG XML document."""
    path = Path(filepath)
    if not path.is_file() or path.stat().st_size < 50:
        return False
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(2048)
            return ("<AnnotatedECG" in head or "urn:hl7-org:v3" in head) and ("<series" in head or "<sequence" in head)
    except Exception:
        return False


def read_hl7_aecg(filepath: Union[str, Path, os.PathLike[str]]) -> HL7Record:
    """Parses an HL7 aECG XML recording and converts digit sequences to physical millivolts.

    Args:
        filepath: Path to the .xml or .aecg file.

    Returns:
        HL7Record with calibrated signals in millivolts (mV).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file exceeds safety limits or contains malformed XML/sequences.
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"HL7 aECG file not found: {path}")

    file_size = path.stat().st_size
    if file_size > 250 * 1024 * 1024:
        raise ValueError(f"Security Alert: HL7 aECG file ({file_size} B) exceeds the 250 MB safety ceiling.")

    tree = ET.parse(str(path))
    root = tree.getroot()

    def strip_ns(tag: str) -> str:
        return tag.split("}")[-1] if "}" in tag else tag

    patient_id = "ANONYMOUS"
    patient_name = "PATIENT"
    study_id = path.stem
    effective_time = ""
    fs = 500.0

    # Search for patient and effective time
    for elem in root.iter():
        t = strip_ns(elem.tag)
        if t == "patientPerson":
            for ch in elem:
                if strip_ns(ch.tag) == "name" and ch.text:
                    patient_name = ch.text.strip()
        elif t == "effectiveTime":
            val = elem.get("value")
            if val:
                effective_time = val.strip()

    lead_signals: List[np.ndarray] = []
    lead_names: List[str] = []
    units: List[str] = []

    # Find all sequence elements containing waveform digits
    for seq in root.iter():
        if strip_ns(seq.tag) != "sequence":
            continue

        raw_code = ""
        scale_val = 0.005
        digits_text = ""

        for child in seq:
            tag = strip_ns(child.tag)
            if tag == "code":
                raw_code = child.get("code", "")
            elif tag == "scale":
                try:
                    s_str = child.get("value", "0.005").strip().replace(",", ".")
                    scale_val = float(s_str)
                    unit = child.get("unit", "mV").lower()
                    if unit in ("uv", "microvolt", "µv"):
                        scale_val /= 1000.0
                except ValueError:
                    scale_val = 0.005
            elif tag == "increment":
                try:
                    inc_str = child.get("value", "0.002").strip().replace(",", ".")
                    inc_val = float(inc_str)
                    if inc_val > 0:
                        fs = 1.0 / inc_val
                except ValueError:
                    pass
            elif tag in ("digits", "value"):
                if child.text:
                    digits_text = child.text.strip()

        lead_name = HL7_LEAD_NAMES.get(raw_code, raw_code or f"Lead_{len(lead_names) + 1}")

        if digits_text:
            try:
                # Normalize potential European comma decimal formatting in text lists
                cleaned_text = digits_text.replace(",", ".") if "," in digits_text else digits_text
                raw_ints = np.fromstring(cleaned_text, dtype=np.int32, sep=" ")
                if len(raw_ints) > 0:
                    sig_mv = raw_ints.astype(np.float32) * scale_val
                    lead_signals.append(sig_mv)
                    lead_names.append(lead_name)
                    units.append("mV")
            except Exception:
                continue

    if not lead_signals:
        raise ValueError(f"HL7 aECG file '{path.name}' contains no valid waveform sequence digits.")

    min_len = min(len(s) for s in lead_signals)
    matrix = np.array([s[:min_len] for s in lead_signals], dtype=np.float32)

    return HL7Record(
        patient_id=patient_id,
        patient_name=patient_name,
        study_id=study_id,
        effective_time=effective_time,
        sampling_rate=fs,
        num_leads=matrix.shape[0],
        num_samples=matrix.shape[1],
        lead_names=lead_names,
        signals=matrix,
        units=units,
    )
