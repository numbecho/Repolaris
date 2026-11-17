"""Signal Quality Index (SQI) assessment and Two-Stage Lead Voting module for ECG recordings.

Implements a non-regressive two-stage signal quality architecture:
1. Stage 1 (Absolute Physiological Rejection Gate; Li, Rajagopalan & Clifford, 2014):
   Computes spectral and statistical indices (pSQI, basSQI, kSQI kurtosis, sSQI skewness,
   SNR_dB, and flatline ratio) to classify leads into 'EXCELLENT', 'ACCEPTABLE', or 'POOR'.
   Any lead failing the absolute 'ACCEPTABLE' floor is rejected so detached/saturated leads
   can never be selected.
2. Stage 2 (Pairwise Six-Index Relative Lead Voting Tie-Breaker; Suárez-León et al., 2018):
   Among leads that pass Stage 1, computes a pairwise comparison across 6 normalized quality
   indices yielding a Voting Index VI_k in [-6.0, +6.0] to select the optimal lead.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.signal import welch


def compute_band_power(
    signal: np.ndarray,
    fs: float,
    low_freq: float,
    high_freq: float,
    nperseg: int = 1024,
) -> float:
    """Computes total spectral power within a specific frequency band [low_freq, high_freq]."""
    n = len(signal)
    if n < 4:
        return 0.0
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
    relative to the extended ventricular frequency band (5-40 Hz) (Li et al., 2014).
    """
    p_qrs = compute_band_power(signal, fs, 5.0, 15.0)
    p_total = compute_band_power(signal, fs, 5.0, 40.0)

    if p_total <= 1e-12:
        return 0.0
    return float(np.clip(p_qrs / p_total, 0.0, 1.0))


def compute_bassqi(signal: np.ndarray, fs: float) -> float:
    """Computes the baseline wander signal quality index (basSQI).

    Measures 1.0 minus the fraction of low-frequency drift power (< 1.0 Hz)
    relative to total signal power (< 40.0 Hz) (Li et al., 2014).
    """
    p_baseline = compute_band_power(signal, fs, 0.0, 1.0)
    p_total = compute_band_power(signal, fs, 0.0, 40.0)

    if p_total <= 1e-12:
        return 1.0
    ratio = p_baseline / p_total
    return float(np.clip(1.0 - ratio, 0.0, 1.0))


def compute_ksqi(signal: np.ndarray) -> float:
    """Computes the fourth standardized moment (kurtosis, kSQI) of the ECG lead."""
    x = np.asarray(signal, dtype=np.float64)
    if len(x) < 4:
        return 0.0
    std = float(np.std(x))
    if std <= 1e-12:
        return 0.0
    z = (x - float(np.mean(x))) / std
    return float(np.mean(z**4))


def compute_ssqi(signal: np.ndarray) -> float:
    """Computes the absolute third standardized moment (skewness magnitude, sSQI)."""
    x = np.asarray(signal, dtype=np.float64)
    if len(x) < 4:
        return 0.0
    std = float(np.std(x))
    if std <= 1e-12:
        return 0.0
    z = (x - float(np.mean(x))) / std
    return float(np.abs(np.mean(z**3)))


def evaluate_lead_quality(
    signal: np.ndarray,
    fs: float,
    conditioned_signal: np.ndarray | None = None,
) -> dict[str, float | str | bool]:
    """Evaluates Stage 1 absolute multi-metric quality parameters for an ECG lead.

    When `conditioned_signal` is provided, baseline stability (`bassqi`) and high-frequency
    noise (`snr_db`) are evaluated on the raw physical signal before stopband attenuation,
    while QRS energy concentration (`psqi`) and morphology moments (`ksqi`, `ssqi`) are
    evaluated on the baseline-suppressed trace.
    """
    raw_x = np.asarray(signal, dtype=np.float64)
    cond_x = (
        np.asarray(conditioned_signal, dtype=np.float64)
        if conditioned_signal is not None
        else raw_x
    )

    if len(raw_x) < 10 or float(np.std(raw_x)) <= 1e-6:
        return {
            "psqi": 0.0,
            "bassqi": 0.0,
            "ksqi": 0.0,
            "ssqi": 0.0,
            "snr_db": -20.0,
            "non_flat_ratio": 0.0,
            "passed_absolute_gate": False,
            "verdict": "POOR",
        }

    psqi_val = compute_psqi(cond_x, fs)
    bassqi_val = compute_bassqi(raw_x, fs)
    ksqi_val = compute_ksqi(cond_x)
    ssqi_val = compute_ssqi(cond_x)

    diffs = np.abs(np.diff(raw_x))
    non_flat_ratio = float(np.mean(diffs > 1e-6)) if len(diffs) > 0 else 0.0

    p_qrs = compute_band_power(raw_x, fs, 5.0, 40.0)
    p_noise = compute_band_power(raw_x, fs, 40.0, min(fs / 2.0 - 1.0, 100.0))

    snr_db = 40.0 if p_noise <= 1e-12 else float(10.0 * np.log10(max(p_qrs / p_noise, 1e-3)))

    if (
        psqi_val >= 0.50
        and bassqi_val >= 0.70
        and non_flat_ratio >= 0.80
        and ksqi_val >= 3.0
        and snr_db >= 10.0
    ):
        verdict = "EXCELLENT"
    elif (
        psqi_val >= 0.30
        and bassqi_val >= 0.40
        and non_flat_ratio >= 0.50
        and ksqi_val >= 1.5
        and snr_db >= 3.0
    ):
        verdict = "ACCEPTABLE"
    else:
        verdict = "POOR"

    passed_gate = verdict in ("EXCELLENT", "ACCEPTABLE")

    return {
        "psqi": psqi_val,
        "bassqi": bassqi_val,
        "ksqi": ksqi_val,
        "ssqi": ssqi_val,
        "snr_db": snr_db,
        "non_flat_ratio": non_flat_ratio,
        "passed_absolute_gate": passed_gate,
        "verdict": verdict,
    }


def rank_leads_two_stage(
    lead_signals: dict[str, np.ndarray] | np.ndarray,
    fs: float,
    lead_names: list[str] | None = None,
) -> dict[str, Any]:
    """Executes Two-Stage SQA Lead Ranking (Absolute Gate + 6-Index Pairwise Voting VI in [-6, +6])."""
    if isinstance(lead_signals, dict):
        names = list(lead_signals.keys())
        signals = [np.asarray(lead_signals[k], dtype=np.float64) for k in names]
    else:
        arr = np.asarray(lead_signals, dtype=np.float64)
        if arr.ndim == 1:
            arr = arr[None, :]
        n_leads = arr.shape[0]
        names = (
            lead_names
            if (lead_names and len(lead_names) == n_leads)
            else [f"Lead_{i + 1}" for i in range(n_leads)]
        )
        signals = [arr[i] for i in range(n_leads)]

    per_lead: dict[str, dict[str, Any]] = {}
    passing_names: list[str] = []

    for name, sig in zip(names, signals, strict=False):
        q = evaluate_lead_quality(sig, fs)
        q["voting_index"] = -6.0
        per_lead[name] = q
        if q["passed_absolute_gate"]:
            passing_names.append(name)

    if not passing_names:
        return {
            "quorum_passed": False,
            "recommended_lead": None,
            "passing_leads": [],
            "rejected_leads": names,
            "per_lead": per_lead,
        }

    metric_keys = ("psqi", "bassqi", "ksqi", "ssqi", "snr_db", "non_flat_ratio")
    n_pass = len(passing_names)

    if n_pass == 1:
        only_lead = passing_names[0]
        per_lead[only_lead]["voting_index"] = 6.0
        return {
            "quorum_passed": True,
            "recommended_lead": only_lead,
            "passing_leads": passing_names,
            "rejected_leads": [n for n in names if n not in passing_names],
            "per_lead": per_lead,
        }

    for k_name in passing_names:
        net_wins = 0.0
        for m_key in metric_keys:
            val_k = float(per_lead[k_name][m_key])
            for j_name in passing_names:
                if k_name == j_name:
                    continue
                val_j = float(per_lead[j_name][m_key])
                if val_k > val_j + 1e-9:
                    net_wins += 1.0
                elif val_k < val_j - 1e-9:
                    net_wins -= 1.0
        vi_score = net_wins / float(n_pass - 1)
        per_lead[k_name]["voting_index"] = float(np.clip(vi_score, -6.0, 6.0))

    best_lead = max(
        passing_names,
        key=lambda n: (float(per_lead[n]["voting_index"]), float(per_lead[n]["snr_db"])),
    )

    return {
        "quorum_passed": True,
        "recommended_lead": best_lead,
        "passing_leads": passing_names,
        "rejected_leads": [n for n in names if n not in passing_names],
        "per_lead": per_lead,
    }
