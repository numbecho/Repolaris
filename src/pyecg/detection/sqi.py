"""Signal Quality Index (SQI) assessment module for ECG recordings.

Provides standardized signal quality metrics to help clinicians identify
high-fidelity lead channels and reject noisy, artifact-corrupted, or
baseline-wandering recordings prior to diagnostic repolarization analysis.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from scipy.signal import welch


def compute_band_power(
    signal: np.ndarray,
    fs: float,
    low_freq: float,
    high_freq: float,
    nperseg: int = 1024,
) -> float:
    """Computes total spectral power within a specific frequency band [low_freq, high_freq].

    Args:
        signal: 1D ECG waveform array.
        fs: Sampling frequency in Hertz.
        low_freq: Lower frequency bound in Hz.
        high_freq: Upper frequency bound in Hz.
        nperseg: Length of each segment for Welch's periodogram.

    Returns:
        Integrated power within the band.
    """
    n = len(signal)
    seg_len = min(nperseg, n)
    freqs, psd = welch(signal, fs=fs, nperseg=seg_len)

    band_mask = (freqs >= low_freq) & (freqs <= high_freq)
    if not np.any(band_mask):
        return 0.0

    trapz_fn = getattr(np, "trapezoid", getattr(np, "trapz", None))
    return float(trapz_fn(psd[band_mask], freqs[band_mask]))


def compute_psqi(signal: np.ndarray, fs: float) -> float:
    """Computes the QRS complex relative power signal quality index (pSQI).

    Evaluates the ratio of spectral energy in the core QRS band (5-15 Hz)
    relative to the extended ventricular frequency band (5-40 Hz).

    Args:
        signal: 1D ECG waveform array.
        fs: Sampling frequency in Hz.

    Returns:
        pSQI score in [0.0, 1.0]. Higher values indicate crisp QRS morphology.
    """
    p_qrs = compute_band_power(signal, fs, 5.0, 15.0)
    p_total = compute_band_power(signal, fs, 5.0, 40.0)

    if p_total <= 1e-12:
        return 0.0
    return float(np.clip(p_qrs / p_total, 0.0, 1.0))


def compute_bassqi(signal: np.ndarray, fs: float) -> float:
    """Computes the baseline wander signal quality index (basSQI).

    Measures 1.0 minus the fraction of low-frequency drift power (< 1.0 Hz)
    relative to total signal power (< 40.0 Hz).

    Args:
        signal: 1D ECG waveform array.
        fs: Sampling frequency in Hz.

    Returns:
        basSQI score in [0.0, 1.0]. Values approaching 1.0 indicate minimal baseline drift.
    """
    p_baseline = compute_band_power(signal, fs, 0.0, 1.0)
    p_total = compute_band_power(signal, fs, 0.0, 40.0)

    if p_total <= 1e-12:
        return 1.0
    ratio = p_baseline / p_total
    return float(np.clip(1.0 - ratio, 0.0, 1.0))


def evaluate_lead_quality(
    signal: np.ndarray,
    fs: float,
) -> Dict[str, Union[float, str]]:
    """Evaluates multi-metric quality parameters for an ECG lead.

    Args:
        signal: 1D ECG waveform array.
        fs: Sampling frequency in Hz.

    Returns:
        A dictionary containing:
            - 'psqi': QRS relative power index.
            - 'bassqi': Baseline stability index.
            - 'snr_db': Estimated signal-to-noise ratio in decibels.
            - 'verdict': Diagnostic usability assessment ('EXCELLENT', 'ACCEPTABLE', 'POOR').
    """
    psqi_val = compute_psqi(signal, fs)
    bassqi_val = compute_bassqi(signal, fs)

    # Estimate SNR as ratio of QRS band power (5-40Hz) to high-frequency noise (>40Hz)
    p_qrs = compute_band_power(signal, fs, 5.0, 40.0)
    p_noise = compute_band_power(signal, fs, 40.0, min(fs / 2.0 - 1.0, 100.0))

    if p_noise <= 1e-12:
        snr_db = 40.0
    else:
        snr_db = float(10.0 * np.log10(max(p_qrs / p_noise, 1e-3)))

    if psqi_val >= 0.5 and bassqi_val >= 0.7:
        verdict = "EXCELLENT"
    elif psqi_val >= 0.3 and bassqi_val >= 0.4:
        verdict = "ACCEPTABLE"
    else:
        verdict = "POOR"

    return {
        "psqi": psqi_val,
        "bassqi": bassqi_val,
        "snr_db": snr_db,
        "verdict": verdict,
    }
