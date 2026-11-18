"""ECG-Derived Respiration (EDR) & Sleep-Disordered Breathing Screening module.

Derives continuous respiratory effort modulation from beat-to-beat QRS area/amplitude
variations (Moody, Mark, Zoccola & Mantero, 1985/1986) coupled with Cyclic Variation of
Heart Rate (CVHR) spectral power (0.01-0.04 Hz) for overnight ambulatory sleep apnea
screening without external thoracic belts or nasal cannulas.

References:
    - Moody G.B., Mark R.G., Zoccola A., Mantero S. (1985). "Derivation of Respiratory
      Signals from Multi-lead ECGs." Computers in Cardiology, 12, 113-116.
    - Hayano J., Watanabe E., Saito Y., et al. (2011). "Screening for obstructive sleep
      apnea by cyclic variation of heart rate." Circulation: Arrhythmia and Electrophysiology, 4(1), 64-72.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.signal import butter, filtfilt, welch

from repolaris.detection.q_onset import detect_j_point, detect_q_onset
from repolaris.detection.qrs import detect_r_peaks

_trapz_fn = getattr(np, "trapezoid", None) or getattr(np, "trapz", None)


def compute_ecg_derived_respiration(
    signal: np.ndarray,
    fs: float = 500.0,
    r_peaks: np.ndarray | None = None,
    beats: list[dict[str, Any]] | None = None,
    fs_edr: float = 4.0,
) -> dict[str, Any]:
    """Extracts the ECG-Derived Respiration (EDR) waveform, respiratory rate (breaths/min), and CVHR apnea index.

    Args:
        signal: 1D conditioned ECG waveform array (mV).
        fs: ECG sampling frequency in Hz (default: 500.0).
        r_peaks: Optional 1D array of R-peak sample indices.
        beats: Optional list of segmented beat dictionaries containing `q_onset_sample`
            and `j_point_sample`.
        fs_edr: Uniform resampling rate for the derived respiratory waveform in Hz (default: 4.0 Hz).

    Returns:
        Dictionary with `respiratory_rate_brpm`, `respiratory_freq_hz`, `edr_time_sec`,
        `edr_waveform`, `cvhr_power_ratio`, `apnea_screening_verdict`, and `valid`.
    """
    n_sig = len(signal)
    if n_sig < int(fs * 3.0) or fs <= 0:
        return {
            "valid": False,
            "respiratory_rate_brpm": 0.0,
            "respiratory_freq_hz": 0.0,
            "edr_time_sec": [],
            "edr_waveform": [],
            "cvhr_power_ratio": 0.0,
            "apnea_screening_verdict": "INSUFFICIENT_DURATION",
        }

    if beats and len(beats) >= 4:
        beat_times: list[float] = []
        qrs_mod_series: list[float] = []
        rr_series_ms: list[float] = []

        for b in beats:
            r_idx = int(b["r_peak_sample"])
            q_idx = int(b.get("q_onset_sample", max(0, r_idx - int(round(0.040 * fs)))))
            j_idx = int(b.get("j_point_sample", min(n_sig - 1, r_idx + int(round(0.045 * fs)))))
            w0 = max(0, min(q_idx, r_idx - int(round(0.035 * fs))))
            w1 = min(n_sig, max(j_idx + 1, r_idx + int(round(0.040 * fs))))
            qrs_seg = np.asarray(signal[w0:w1], dtype=np.float64)
            if len(qrs_seg) < 2:
                continue
            # Combine peak-to-peak QRS envelope and integrated absolute QRS area (Moody et al., 1985)
            qrs_area = float(_trapz_fn(np.abs(qrs_seg), dx=1.0 / fs))
            qrs_ptp = float(np.ptp(qrs_seg))
            beat_times.append(float(r_idx / fs))
            qrs_mod_series.append(0.5 * qrs_ptp + 10.0 * qrs_area)
            rr_s = float(b.get("rr_sec", 0.85) or 0.85)
            rr_series_ms.append(rr_s * 1000.0)
    else:
        if r_peaks is None:
            r_peaks = detect_r_peaks(signal, fs)
        if len(r_peaks) < 4:
            return {
                "valid": False,
                "respiratory_rate_brpm": 0.0,
                "respiratory_freq_hz": 0.0,
                "edr_time_sec": [],
                "edr_waveform": [],
                "cvhr_power_ratio": 0.0,
                "apnea_screening_verdict": "INSUFFICIENT_BEATS",
            }
        beat_times = []
        qrs_mod_series = []
        rr_series_ms = []
        for idx, r_idx in enumerate(r_peaks):
            r_int = int(r_idx)
            q_idx = detect_q_onset(signal, r_int, fs)
            j_idx = detect_j_point(signal, r_int, fs)
            w0 = max(0, min(q_idx, r_int - int(round(0.035 * fs))))
            w1 = min(n_sig, max(j_idx + 1, r_int + int(round(0.040 * fs))))
            qrs_seg = np.asarray(signal[w0:w1], dtype=np.float64)
            if len(qrs_seg) < 2:
                continue
            qrs_area = float(_trapz_fn(np.abs(qrs_seg), dx=1.0 / fs))
            qrs_ptp = float(np.ptp(qrs_seg))
            beat_times.append(float(r_int / fs))
            qrs_mod_series.append(0.5 * qrs_ptp + 10.0 * qrs_area)
            rr_s = float((r_int - int(r_peaks[idx - 1])) / fs) if idx > 0 else 0.85
            rr_series_ms.append(rr_s * 1000.0)

    if len(beat_times) < 4:
        return {
            "valid": False,
            "respiratory_rate_brpm": 0.0,
            "respiratory_freq_hz": 0.0,
            "edr_time_sec": [],
            "edr_waveform": [],
            "cvhr_power_ratio": 0.0,
            "apnea_screening_verdict": "INSUFFICIENT_BEATS",
        }

    t_beats = np.asarray(beat_times, dtype=np.float64)
    mod_vals = np.asarray(qrs_mod_series, dtype=np.float64)
    mod_centered = mod_vals - float(np.mean(mod_vals))

    t_start = float(t_beats[0])
    t_end = float(t_beats[-1])
    dur = t_end - t_start
    if dur < 2.5:
        return {
            "valid": False,
            "respiratory_rate_brpm": 0.0,
            "respiratory_freq_hz": 0.0,
            "edr_time_sec": [],
            "edr_waveform": [],
            "cvhr_power_ratio": 0.0,
            "apnea_screening_verdict": "INSUFFICIENT_DURATION",
        }

    n_grid = max(16, int(round(dur * fs_edr)))
    t_grid = np.linspace(t_start, t_end, n_grid)
    edr_interp = np.interp(t_grid, t_beats, mod_centered)

    # Filter into physiological respiratory band [0.12 Hz, 0.45 Hz] (7.2 - 27.0 breaths/min)
    nyq = 0.5 * fs_edr
    low = max(0.05, 0.12 / nyq)
    high = min(0.95, 0.45 / nyq)
    if len(edr_interp) >= 18 and low < high:
        b_coef, a_coef = butter(2, [low, high], btype="band")
        edr_wave = filtfilt(b_coef, a_coef, edr_interp)
    else:
        edr_wave = edr_interp - float(np.mean(edr_interp))

    # Normalize EDR waveform to unit standard deviation when non-degenerate
    edr_std = float(np.std(edr_wave))
    if edr_std > 1e-7:
        edr_wave = edr_wave / edr_std

    # Estimate dominant respiratory frequency via Welch PSD in [0.12, 0.45] Hz
    nperseg = min(len(edr_wave), max(16, int(round(16.0 * fs_edr))))
    freqs, psd = welch(edr_wave, fs=fs_edr, nperseg=nperseg, nfft=max(256, nperseg * 4))
    resp_mask = (freqs >= 0.12) & (freqs <= 0.45)

    if np.any(resp_mask) and float(np.max(psd[resp_mask])) > 1e-9:
        resp_freqs = freqs[resp_mask]
        resp_psd = psd[resp_mask]
        dom_freq_hz = float(resp_freqs[int(np.argmax(resp_psd))])
    else:
        # Zero-crossing fallback
        zc = np.where(np.diff(np.signbit(edr_wave)))[0]
        dom_freq_hz = float(len(zc) / (2.0 * dur)) if len(zc) >= 2 else 0.25
        dom_freq_hz = float(np.clip(dom_freq_hz, 0.12, 0.45))

    brpm = dom_freq_hz * 60.0

    # Cyclic Variation of Heart Rate (CVHR) sleep-disordered breathing index (0.01 - 0.04 Hz VLF oscillation)
    rr_interp = np.interp(t_grid, t_beats, np.asarray(rr_series_ms, dtype=np.float64))
    rr_centered = rr_interp - float(np.mean(rr_interp))
    f_rr, p_rr = welch(rr_centered, fs=fs_edr, nperseg=nperseg, nfft=max(256, nperseg * 4))
    cvhr_mask = (f_rr >= 0.01) & (f_rr <= 0.04)
    tot_mask = (f_rr >= 0.01) & (f_rr <= 0.45)

    tot_pwr = float(_trapz_fn(p_rr[tot_mask], f_rr[tot_mask])) if np.any(tot_mask) else 0.0
    cvhr_pwr = float(_trapz_fn(p_rr[cvhr_mask], f_rr[cvhr_mask])) if np.any(cvhr_mask) else 0.0
    cvhr_ratio = (cvhr_pwr / tot_pwr) if tot_pwr > 1e-9 else 0.0

    if dur < 60.0:
        apnea_verdict = "NORMAL_RESPIRATION"
    elif cvhr_ratio >= 0.55:
        apnea_verdict = "HIGH_SDB_RISK"
    elif cvhr_ratio >= 0.38:
        apnea_verdict = "MODERATE_SDB_RISK"
    else:
        apnea_verdict = "LOW_SDB_RISK"

    return {
        "valid": True,
        "respiratory_rate_brpm": round(float(brpm), 2),
        "respiratory_freq_hz": round(float(dom_freq_hz), 4),
        "edr_time_sec": [round(float(t), 3) for t in t_grid[:240]],
        "edr_waveform": [round(float(v), 4) for v in edr_wave[:240]],
        "cvhr_power_ratio": round(float(cvhr_ratio), 4),
        "apnea_screening_verdict": apnea_verdict,
    }
