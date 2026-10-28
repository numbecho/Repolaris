"""
ISHNE Holter Standard Output File Format (.ecg) Reader and Writer
Specification: Fabio Badilini et al., Annals of Noninvasive Electrocardiology, 1998.

Binary Structure:
- 8 bytes: Magic number b"ISHNE1.0"
- 2 bytes: CRC-CCITT Checksum (uint16)
- 512 bytes: Fixed-length header block:
    - long Var_length_block_size (int32)
    - long Sample_Size_ECG (int32 - total samples per lead)
    - long offset_var_length_block (int32)
    - long Offset_ECG_block (int32)
    - short file_Version (int16)
    - char First_Name[40]
    - char Last_Name[40]
    - char ID[20]
    - short Sex (0: unknown, 1: male, 2: female)
    - short Race (0: unknown, 1: Caucasian, 2: Black, 3: Oriental)
    - short Birth_Date[3] (day, month, year)
    - short Record_Date[3] (day, month, year)
    - short File_Date[3] (day, month, year)
    - short Start_Time[3] (hour, min, sec)
    - short nLeads (number of stored leads)
    - short Lead_Spec[12] (lead IDs from table 1)
    - short Lead_Qual[12] (quality ratings)
    - short Resolution[12] (integer nV per LSB)
    - short Pacemaker (0: no, 1: unknown, etc.)
    - char Recorder[40]
    - short Sampling_Rate (Hertz)
    - char Proprietary[80]
    - char Copyright[80]
    - char Reserved[88]
- Variable-length text block (Var_length_block_size bytes)
- Continuous multiplexed 16-bit signed integer samples (little-endian)
"""

import struct
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, date, time
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

MAGIC = b"ISHNE1.0"

LEAD_CODE_MAP = {
    0: "Unknown",
    1: "Generic_bipolar",
    2: "X_bipolar",
    3: "Y_bipolar",
    4: "Z_bipolar",
    5: "Lead_I",
    6: "Lead_II",
    7: "Lead_III",
    8: "aVR",
    9: "aVL",
    10: "aVF",
    11: "V1",
    12: "V2",
    13: "V3",
    14: "V4",
    15: "V5",
    16: "V6",
    17: "ES",
    18: "AS",
    19: "AI",
}

RACE_CODE_MAP = {
    0: "Unknown",
    1: "Caucasian",
    2: "Black / African",
    3: "Asian / Oriental"
}

SEX_CODE_MAP = {
    0: "Unknown",
    1: "Male",
    2: "Female"
}


@dataclass
class ISHNERecord:
    patient_id: str
    first_name: str
    last_name: str
    sex: str
    race: str
    birth_date: Optional[date]
    record_date: Optional[date]
    start_time: Optional[time]
    sampling_rate: float
    num_leads: int
    lead_names: List[str]
    resolutions_nv: List[int]
    total_samples: int
    duration_sec: float
    clinical_notes: str
    signals: np.ndarray  # Shape: (num_leads, num_samples) in physical millivolts (mV)

    @property
    def age_years(self) -> Optional[int]:
        if self.birth_date and self.record_date:
            return self.record_date.year - self.birth_date.year - (
                (self.record_date.month, self.record_date.day) < (self.birth_date.month, self.birth_date.day)
            )
        return None


def read_ishne(filepath: str | Path) -> ISHNERecord:
    """Reads and parses an official ISHNE 1.0 Holter (.ecg) binary file."""
    filepath = Path(filepath)
    with open(filepath, "rb") as f:
        magic = f.read(8)
        if not magic.startswith(b"ISHNE"):
            raise ValueError(f"Invalid ISHNE file: expected magic b'ISHNE1.0', got {magic}")
            
        crc = struct.unpack("<H", f.read(2))[0]
        fixed_block = f.read(512)
        if len(fixed_block) < 512:
            raise ValueError("Corrupt ISHNE file: header is smaller than 522 bytes.")

        # Fixed block unpack
        # 4 ints (4B), 1 short (2B), 40s, 40s, 20s, 2 shorts (sex, race), 4 sets of 3 shorts (dates/time)
        fmt_prefix = "<4i h 40s 40s 20s 2h 3h 3h 3h 3h h"
        prefix_size = struct.calcsize(fmt_prefix)
        prefix_data = struct.unpack(fmt_prefix, fixed_block[:prefix_size])
        
        var_block_size = prefix_data[0]
        sample_size_ecg = prefix_data[1]  # Samples per channel
        offset_var_block = prefix_data[2]
        offset_ecg_block = prefix_data[3]
        file_version = prefix_data[4]
        first_name = prefix_data[5].decode("latin1", errors="ignore").strip("\x00 \t\r\n")
        last_name = prefix_data[6].decode("latin1", errors="ignore").strip("\x00 \t\r\n")
        patient_id = prefix_data[7].decode("latin1", errors="ignore").strip("\x00 \t\r\n")
        sex_code = prefix_data[8]
        race_code = prefix_data[9]
        b_day, b_month, b_year = prefix_data[10], prefix_data[11], prefix_data[12]
        r_day, r_month, r_year = prefix_data[13], prefix_data[14], prefix_data[15]
        f_day, f_month, f_year = prefix_data[16], prefix_data[17], prefix_data[18]
        s_hour, s_min, s_sec = prefix_data[19], prefix_data[20], prefix_data[21]
        n_leads = prefix_data[22]

        # Remaining fixed block: 12 lead_spec, 12 lead_qual, 12 res, 1 pacemaker, 40s recorder, 1 sampling_rate, 80s, 80s, 88s
        fmt_suffix = "<12h 12h 12h h 40s h 80s 80s 88s"
        suffix_data = struct.unpack(fmt_suffix, fixed_block[prefix_size:])
        
        lead_specs = suffix_data[0:12]
        lead_quals = suffix_data[12:24]
        resolutions = suffix_data[24:36]
        pacemaker = suffix_data[36]
        recorder = suffix_data[37].decode("latin1", errors="ignore").strip("\x00 ")
        sampling_rate = suffix_data[38]

        # Variable text block
        clinical_notes = ""
        if var_block_size > 0:
            f.seek(offset_var_block)
            raw_text = f.read(var_block_size)
            clinical_notes = raw_text.decode("latin1", errors="ignore").strip("\x00 \r\n")

        # Read multiplexed continuous 16-bit integer ECG samples
        f.seek(offset_ecg_block)
        total_elements = n_leads * sample_size_ecg
        raw_samples = np.fromfile(f, dtype="<i2", count=total_elements)

    if raw_samples.size != total_elements:
        actual_samples_per_lead = raw_samples.size // n_leads
        raw_samples = raw_samples[: actual_samples_per_lead * n_leads]
        sample_size_ecg = actual_samples_per_lead

    # Demultiplex: raw layout is [s0_ch0, s0_ch1, ... s0_chN, s1_ch0, s1_ch1, ...]
    multiplexed_matrix = raw_samples.reshape(-1, n_leads).T  # Shape: (n_leads, sample_size_ecg)

    # Convert to physical millivolts (mV) using per-lead resolution (in nV)
    signals_mv = np.zeros_like(multiplexed_matrix, dtype=np.float32)
    lead_names = []
    resolutions_nv = []

    for i in range(n_leads):
        res_nv = resolutions[i] if (i < len(resolutions) and resolutions[i] > 0) else 5000  # Default 5 uV
        resolutions_nv.append(res_nv)
        
        # Scale: raw * nV / 1,000,000 = mV
        signals_mv[i] = (multiplexed_matrix[i].astype(np.float32) * res_nv) / 1_000_000.0
        
        spec_code = lead_specs[i] if i < len(lead_specs) else 0
        name = LEAD_CODE_MAP.get(spec_code, f"Channel_{i+1}")
        lead_names.append(name)

    # Safe date constructions
    def make_date(d, m, y):
        try:
            return date(y, m, d) if (1 <= m <= 12 and 1 <= d <= 31 and y > 1900) else None
        except Exception:
            return None

    def make_time(h, m, s):
        try:
            return time(h, m, s) if (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59) else None
        except Exception:
            return None

    return ISHNERecord(
        patient_id=patient_id,
        first_name=first_name,
        last_name=last_name,
        sex=SEX_CODE_MAP.get(sex_code, "Unknown"),
        race=RACE_CODE_MAP.get(race_code, "Unknown"),
        birth_date=make_date(b_day, b_month, b_year),
        record_date=make_date(r_day, r_month, r_year),
        start_time=make_time(s_hour, s_min, s_sec),
        sampling_rate=float(sampling_rate if sampling_rate > 0 else 200.0),
        num_leads=n_leads,
        lead_names=lead_names,
        resolutions_nv=resolutions_nv,
        total_samples=sample_size_ecg,
        duration_sec=float(sample_size_ecg / (sampling_rate or 200.0)),
        clinical_notes=clinical_notes,
        signals=signals_mv
    )


def write_ishne(
    filepath: str | Path,
    signals_mv: np.ndarray,
    sampling_rate: int,
    lead_codes: list[int],
    resolutions_nv: Optional[list[int]] = None,
    patient_id: str = "ANONYMOUS",
    first_name: str = "",
    last_name: str = "",
    sex_code: int = 0,
    race_code: int = 0,
    record_date: Optional[date] = None,
    start_time: Optional[time] = None,
    clinical_notes: str = ""
) -> str:
    """Creates a standards-compliant ISHNE 1.0 Holter (.ecg) binary file."""
    filepath = Path(filepath)
    signals_mv = np.asarray(signals_mv, dtype=np.float32)
    if signals_mv.ndim == 1:
        signals_mv = signals_mv.reshape(1, -1)
        
    n_leads, sample_size = signals_mv.shape
    if n_leads > 12:
        raise ValueError("ISHNE 1.0 format supports a maximum of 12 simultaneous leads.")

    if resolutions_nv is None:
        resolutions_nv = [5000] * n_leads  # Default 5 uV (5000 nV) per LSB

    # Convert physical mV back to multiplexed int16 ADC samples
    raw_int16 = np.zeros((sample_size, n_leads), dtype="<i2")
    for ch in range(n_leads):
        res = resolutions_nv[ch]
        # Counts = mV * 1,000,000 / res_nv
        counts = np.clip((signals_mv[ch] * 1_000_000.0) / res, -32768, 32767).astype("<i2")
        raw_int16[:, ch] = counts

    text_bytes = clinical_notes.encode("latin1", errors="replace")
    var_block_size = len(text_bytes)
    offset_var_block = 522
    offset_ecg_block = offset_var_block + var_block_size

    r_d = record_date.day if record_date else 1
    r_m = record_date.month if record_date else 1
    r_y = record_date.year if record_date else 2026
    s_h = start_time.hour if start_time else 0
    s_mi = start_time.minute if start_time else 0
    s_s = start_time.second if start_time else 0

    lead_specs_arr = [-9] * 12
    lead_quals_arr = [-9] * 12
    res_arr = [-9] * 12
    for i in range(n_leads):
        lead_specs_arr[i] = lead_codes[i] if i < len(lead_codes) else 0
        lead_quals_arr[i] = 1  # 1 = Good quality
        res_arr[i] = resolutions_nv[i]

    # Pack 512-byte fixed block
    fmt_prefix = "<4i h 40s 40s 20s 2h 3h 3h 3h 3h h"
    prefix = struct.pack(
        fmt_prefix,
        var_block_size,
        sample_size,
        offset_var_block,
        offset_ecg_block,
        1,  # Version 1
        first_name.encode("latin1")[:40].ljust(40, b"\x00"),
        last_name.encode("latin1")[:40].ljust(40, b"\x00"),
        patient_id.encode("latin1")[:20].ljust(20, b"\x00"),
        sex_code,
        race_code,
        0, 0, 0,  # Birth date
        r_d, r_m, r_y,
        r_d, r_m, r_y,  # File date
        s_h, s_mi, s_s,
        n_leads
    )

    fmt_suffix = "<12h 12h 12h h 40s h 80s 80s 88s"
    suffix = struct.pack(
        fmt_suffix,
        *lead_specs_arr,
        *lead_quals_arr,
        *res_arr,
        0,  # No pacemaker
        b"PyECG_Holter".ljust(40, b"\x00"),
        sampling_rate,
        b"".ljust(80, b"\x00"),
        b"".ljust(80, b"\x00"),
        b"".ljust(88, b"\x00")
    )

    fixed_header = prefix + suffix
    crc = 0  # CRC is optional in many open loaders

    with open(filepath, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<H", crc))
        f.write(fixed_header)
        if text_bytes:
            f.write(text_bytes)
        f.write(raw_int16.tobytes())

    return str(filepath)
