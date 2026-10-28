"""MATLAB (.mat) ECG file reader and writer module.

Provides high-compatibility parsing of legacy and modern MATLAB workspace (.mat)
files containing electrocardiographic recordings, with support for automatic lead
discovery, sampling rate detection, duration computation, and metadata extraction.
Preserves the Apache-2.0 license and incorporates structure conventions from
PyECG / ironshore legacy implementations.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from scipy.io import loadmat, savemat


def load_mat_ecg(
    filepath: Union[str, os.PathLike[str]],
    default_fs: float = 250.0,
) -> Dict[str, Any]:
    """Loads ECG signals and associated metadata from a MATLAB .mat file.

    Inspects variables in the .mat archive to identify ECG multi-channel
    arrays, sampling rate (`fs` or `Fs`), lead names, and record duration.
    Supports both legacy PyECG conventions (`mat['ecg']` with shape [channels, samples]
    or [samples, channels]) and generic PhysioNet/WFDB MATLAB formats.

    Args:
        filepath: Path to the .mat file.
        default_fs: Fallback sampling frequency in Hz if not detected in the file.

    Returns:
        A dictionary containing:
            - 'signals': Dict[str, np.ndarray] mapping lead names to 1D float64 signal arrays.
            - 'fs': Sampling frequency as a float.
            - 'lead_names': List of lead name strings.
            - 'duration_s': Total duration in seconds.
            - 'samples': Total number of sample points per channel.
            - 'hours': Integer hours component of duration.
            - 'minutes': Integer minutes component of duration.
            - 'seconds': Integer seconds component of duration.
            - 'raw_metadata': Dict of additional scalar/string fields extracted from the file.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If no valid numeric signal arrays can be located in the file.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"MATLAB ECG file not found: {filepath}")

    mat: Dict[str, Any] = loadmat(str(filepath), squeeze_me=False)

    # 1. Discover sampling frequency (fs / Fs / sampling_rate)
    fs: float = default_fs
    fs_candidates = ["fs", "Fs", "sample_rate", "sampling_rate", "frequency", "Freq"]
    for key in fs_candidates:
        if key in mat:
            val = mat[key]
            if isinstance(val, (int, float, np.number)):
                fs = float(val)
                break
            elif isinstance(val, np.ndarray) and val.size > 0:
                fs = float(val.ravel()[0])
                break

    # 2. Discover lead names if provided
    lead_names: List[str] = []
    lead_candidates = ["leads", "lead_names", "channels", "chan_names", "labels"]

    def _clean_str(x: Any) -> str:
        if isinstance(x, np.ndarray):
            x = x.flat[0] if x.size > 0 else ""
        s = str(x)
        for ch in [" ", "[", "]", "'", '"']:
            s = s.strip(ch)
        return s

    for key in lead_candidates:
        if key in mat:
            val = mat[key]
            if isinstance(val, (list, tuple)):
                lead_names = [_clean_str(item) for item in val if _clean_str(item)]
                break
            elif isinstance(val, np.ndarray):
                lead_names = [_clean_str(item) for item in val.ravel() if _clean_str(item)]
                break

    # 3. Locate signal matrices or vectors
    signals: Dict[str, np.ndarray] = {}
    raw_metadata: Dict[str, Any] = {}

    # Check for dedicated 'ecg' or 'val' matrix (standard in PyECG and PhysioNet wfdb2mat)
    primary_signal_keys = ["ecg", "ECG", "val", "data", "signals", "signal"]
    found_primary = False

    for key in primary_signal_keys:
        if key in mat and isinstance(mat[key], np.ndarray) and mat[key].size > 50:
            arr = mat[key].astype(np.float64)
            # Determine channel vs sample orientation
            if arr.ndim == 1:
                name = lead_names[0] if lead_names else "Lead I"
                signals[name] = arr
            elif arr.ndim == 2:
                # If rows <= 32 and cols > rows, assume shape is (channels, samples)
                if arr.shape[0] <= 32 and arr.shape[1] > arr.shape[0]:
                    n_ch, n_samples = arr.shape
                    for ch_idx in range(n_ch):
                        ch_name = (
                            lead_names[ch_idx]
                            if ch_idx < len(lead_names)
                            else f"Lead {ch_idx + 1}"
                        )
                        signals[ch_name] = arr[ch_idx, :]
                else:
                    # Shape is (samples, channels)
                    n_samples, n_ch = arr.shape
                    for ch_idx in range(n_ch):
                        ch_name = (
                            lead_names[ch_idx]
                            if ch_idx < len(lead_names)
                            else f"Lead {ch_idx + 1}"
                        )
                        signals[ch_name] = arr[:, ch_idx]
            found_primary = True
            break

    # If no primary multi-channel array found, discover individual channel arrays
    if not found_primary:
        for k, v in mat.items():
            if k.startswith("__"):
                continue
            if isinstance(v, np.ndarray) and v.size > 50 and np.issubdtype(v.dtype, np.number):
                signals[k] = np.squeeze(v).astype(np.float64)
            elif not isinstance(v, np.ndarray) or v.size <= 10:
                raw_metadata[k] = v

    if not signals:
        raise ValueError(f"No valid numeric ECG signal arrays found in {filepath}")

    # Compute duration metrics
    first_sig = next(iter(signals.values()))
    total_samples = int(len(first_sig))
    total_seconds = float(total_samples) / fs

    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)

    final_lead_names = list(signals.keys())

    return {
        "signals": signals,
        "fs": fs,
        "lead_names": final_lead_names,
        "duration_s": total_seconds,
        "samples": total_samples,
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
        "raw_metadata": raw_metadata,
    }


def save_mat_ecg(
    filepath: Union[str, os.PathLike[str]],
    signals: Dict[str, np.ndarray],
    fs: float,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Exports ECG signals and parameters to a MATLAB .mat workspace file.

    Formats the channels into a unified 2D matrix [channels, samples] under key
    `ecg`, stores sampling frequency under key `fs`, and includes lead names
    under key `leads`.

    Args:
        filepath: Destination path for the .mat file.
        signals: Dictionary mapping channel/lead names to 1D numpy arrays.
        fs: Sampling frequency in Hertz.
        metadata: Optional dictionary of additional parameters or annotations to save.
    """
    lead_list = list(signals.keys())
    data_matrix = np.array([signals[k] for k in lead_list], dtype=np.float64)

    mat_dict: Dict[str, Any] = {
        "ecg": data_matrix,
        "fs": float(fs),
        "leads": lead_list,
    }

    if metadata:
        for k, v in metadata.items():
            if not k.startswith("__") and k not in mat_dict:
                mat_dict[k] = v

    savemat(str(filepath), mat_dict)
