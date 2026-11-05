"""Repolaris Universal Multi-Format ECG Ingestion and Container Serialization Subpackage."""

from __future__ import annotations

from repolaris.io.e3c_reader import read_e3c
from repolaris.io.ecg_loader import load_ecg_dataset, load_ecg_file, sniff_ecg_format
from repolaris.io.edf_reader import read_edf
from repolaris.io.ishne_reader import read_ishne, write_ishne
from repolaris.io.pecg_format import load_pecg, save_pecg
from repolaris.io.wfdb_reader import read_wfdb
from repolaris.io.dicom_reader import read_dicom_waveform, is_dicom_file, DICOMWaveformRecord
from repolaris.io.hl7_reader import read_hl7_aecg, is_hl7_xml, HL7Record
from repolaris.io.scp_reader import read_scp_ecg, is_scp_file, SCPRecord

__all__ = [
    "load_ecg_file",
    "load_ecg_dataset",
    "sniff_ecg_format",
    "save_pecg",
    "load_pecg",
    "read_ishne",
    "write_ishne",
    "read_e3c",
    "read_edf",
    "read_wfdb",
    "read_dicom_waveform",
    "is_dicom_file",
    "DICOMWaveformRecord",
    "read_hl7_aecg",
    "is_hl7_xml",
    "HL7Record",
    "read_scp_ecg",
    "is_scp_file",
    "SCPRecord",
]
