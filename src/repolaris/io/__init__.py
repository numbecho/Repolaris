"""Repolaris Universal Multi-Format ECG Ingestion and Container Serialization Subpackage."""

from __future__ import annotations

from repolaris.io.dicom_reader import DICOMWaveformRecord, is_dicom_file, read_dicom_waveform
from repolaris.io.e3c_reader import read_e3c
from repolaris.io.ecg_loader import (
    SignalBuffer,
    load_ecg_dataset,
    load_ecg_file,
    open_ecg_buffer,
    sniff_ecg_format,
    stream_ecg_chunks,
)
from repolaris.io.edf_reader import read_edf
from repolaris.io.hl7_reader import HL7Record, is_hl7_xml, read_hl7_aecg
from repolaris.io.ishne_reader import read_ishne, write_ishne
from repolaris.io.pdf_report import generate_clinical_pdf_report
from repolaris.io.pecg_format import load_pecg, save_pecg
from repolaris.io.scp_reader import SCPRecord, is_scp_file, read_scp_ecg
from repolaris.io.wfdb_reader import read_wfdb

__all__ = [
    "load_ecg_file",
    "load_ecg_dataset",
    "sniff_ecg_format",
    "SignalBuffer",
    "open_ecg_buffer",
    "stream_ecg_chunks",
    "generate_clinical_pdf_report",
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
