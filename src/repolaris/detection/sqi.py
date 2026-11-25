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


def _compute_psd(
    signal: np.ndarray,
    fs: float,
    nperseg: int = 1024,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Computes a single Welch PSD for reuse across multiple frequency-band integrals."""
    n = len(signal)
    if n < 4 or fs <= 0:
        return None
    seg_len = min(nperseg, n)
    freqs, psd = welch(signal, fs=fs, nperseg=seg_len)
    return freqs, psd


def _integrate_band(
    freqs: np.ndarray,
    psd: np.ndarray,
    low_freq: float,
    high_freq: float,
) -> float:
    """Integrates a precomputed Welch PSD over [low_freq, high_freq]."""
    if high_freq <= low_freq:
        return 0.0
    band_mask = (freqs >= low_freq) & (freqs <= high_freq)
    if not np.any(band_mask):
        return 0.0
    trapz_fn = getattr(np, "trapezoid", None) or getattr(np, "trapz", None)
    return float(trapz_fn(psd[band_mask], freqs[band_mask]))


def compute_band_power(
    signal: np.ndarray,
    fs: float,
    low_freq: float,
    high_freq: float,
    nperseg: int = 1024,
) -> float:
    """Computes total spectral power within a specific frequency band [low_freq, high_freq]."""
    spec = _compute_psd(signal, fs, nperseg=nperseg)
    if spec is None:
        return 0.0
    freqs, psd = spec
    return _integrate_band(freqs, psd, low_freq, high_freq)


def compute_psqi(signal: np.ndarray, fs: float) -> float:
    """Computes the QRS complex relative power signal quality index (pSQI)."""
    spec = _compute_psd(signal, fs)
    if spec is None:
        return 0.0
    freqs, psd = spec
    p_qrs = _integrate_band(freqs, psd, 5.0, 15.0)
    p_total = _integrate_band(freqs, psd, 5.0, 40.0)
    if p_total <= 1e-12:
        return 0.0
    return float(np.clip(p_qrs / p_total, 0.0, 1.0))


def compute_bassqi(signal: np.ndarray, fs: float) -> float:
    """Computes the baseline wander signal quality index (basSQI)."""
    spec = _compute_psd(signal, fs)
    if spec is None:
        return 1.0
    freqs, psd = spec
    p_baseline = _integrate_band(freqs, psd, 0.0, 1.0)
    p_total = _integrate_band(freqs, psd, 0.0, 40.0)
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
    return float(np.mean(z ** 4))


def compute_ssqi(signal: np.ndarray) -> float:
    """Computes the absolute third standardized moment (skewness magnitude, sSQI)."""
    x = np.asarray(signal, dtype=np.float64)
    if len(x) < 4:
        return 0.0
    std = float(np.std(x))
    if std <= 1e-12:
        return 0.0
    z = (x - float(np.mean(x))) / std
    return float(np.abs(np.mean(z ** 3)))


def evaluate_lead_quality(
    signal: np.ndarray,
    fs: float,
    conditioned_signal: np.ndarray | None = None,
) -> dict[str, Any]:
    """Evaluates Stage 1 absolute multi-metric quality parameters for an ECG lead.

    Uses at most two Welch PSD computations per lead (raw and conditioned).
    When `conditioned_signal` is provided, baseline stability (`bassqi`) and high-frequency
    noise (`snr_db`) are evaluated on the raw physical signal before stopband attenuation,
    while QRS energy concentration (`psqi`) and morphology moments (`ksqi`, `ssqi`) are
    evaluated on the conditioned trace.
    """
    raw_x = np.asarray(signal, dtype=np.float64)
    cond_x = np.asarray(conditioned_signal, dtype=np.float64) if conditioned_signal is not None else raw_x

    if len(raw_x) < 10 or float(np.std(raw_x)) <= 1e-6:
        return {
            "psqi": 0.0,
            "bassqi": 0.0,
            "ksqi": 0.0,
            "ssqi": 0.0,
            "snr_db": -20.0,
            "snr_clamped": True,
            "non_flat_ratio": 0.0,
            "passed_absolute_gate": False,
            "verdict": "POOR",
            "failed_criteria": ["flatline_or_short"],
        }

    raw_spec = _compute_psd(raw_x, fs)
    cond_spec = raw_spec if conditioned_signal is None else _compute_psd(cond_x, fs)

    if cond_spec is not None:
        cf, cp = cond_spec
        p_qrs_cond = _integrate_band(cf, cp, 5.0, 15.0)
        p_tot_cond = _integrate_band(cf, cp, 5.0, 40.0)
        psqi_val = 0.0 if p_tot_cond <= 1e-12 else float(np.clip(p_qrs_cond / p_tot_cond, 0.0, 1.0))
    else:
        psqi_val = 0.0

    if raw_spec is not None:
        rf, rp = raw_spec
        p_base = _integrate_band(rf, rp, 0.0, 1.0)
        p_tot_raw = _integrate_band(rf, rp, 0.0, 40.0)
        bassqi_val = 1.0 if p_tot_raw <= 1e-12 else float(np.clip(1.0 - (p_base / p_tot_raw), 0.0, 1.0))
        p_qrs_raw = _integrate_band(rf, rp, 5.0, 40.0)
        noise_high = min(fs / 2.0 - 1.0, 100.0)
        if fs <= 82.0 or noise_high <= 40.0:
            snr_db = 40.0
            snr_clamped = True
            noise_bypassed = True
        else:
            p_noise = _integrate_band(rf, rp, 40.0, noise_high)
            noise_bypassed = False
            if p_noise <= 1e-12:
                snr_db = 40.0
                snr_clamped = True
            else:
                ratio = p_qrs_raw / p_noise
                if ratio <= 1e-3:
                    snr_db = -30.0
                    snr_clamped = True
                else:
                    snr_db = float(10.0 * np.log10(ratio))
                    snr_clamped = False
    else:
        bassqi_val = 1.0
        snr_db = 40.0
        snr_clamped = True
        noise_bypassed = True

    ksqi_val = compute_ksqi(cond_x)
    ssqi_val = compute_ssqi(cond_x)

    diffs = np.abs(np.diff(raw_x))
    non_flat_ratio = float(np.mean(diffs > 1e-6)) if len(diffs) > 0 else 0.0

    failed_criteria: list[str] = []
    if psqi_val < 0.30:
        failed_criteria.append("psqi")
    if bassqi_val < 0.40:
        failed_criteria.append("bassqi")
    if non_flat_ratio < 0.50:
        failed_criteria.append("non_flat_ratio")
    if ksqi_val < 1.5:
        failed_criteria.append("ksqi")
    if not noise_bypassed and snr_db < 3.0:
        failed_criteria.append("snr_db")

    if (
        psqi_val >= 0.50
        and bassqi_val >= 0.70
        and non_flat_ratio >= 0.80
        and ksqi_val >= 3.0
        and (noise_bypassed or snr_db >= 10.0)
    ):
        verdict = "EXCELLENT"
    elif not failed_criteria:
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
        "snr_clamped": snr_clamped,
        "non_flat_ratio": non_flat_ratio,
        "passed_absolute_gate": passed_gate,
        "verdict": verdict,
        "failed_criteria": failed_criteria,
    }


def rank_leads_two_stage(
    lead_signals: dict[str, np.ndarray] | np.ndarray,
    fs: float,
    lead_names: list[str] | None = None,
    conditioned_leads: dict[str, np.ndarray] | np.ndarray | None = None,
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
        names = lead_names if (lead_names and len(lead_names) == n_leads) else [f"Lead_{i+1}" for i in range(n_leads)]
        signals = [arr[i] for i in range(n_leads)]

    cond_map: dict[str, np.ndarray] = {}
    if isinstance(conditioned_leads, dict):
        cond_map = {k: np.asarray(v, dtype=np.float64) for k, v in conditioned_leads.items()}
    elif conditioned_leads is not None:
        c_arr = np.asarray(conditioned_leads, dtype=np.float64)
        if c_arr.ndim == 1:
            c_arr = c_arr[None, :]
        for idx, name in enumerate(names):
            if idx < c_arr.shape[0]:
                cond_map[name] = c_arr[idx]

    per_lead: dict[str, dict[str, Any]] = {}
    passing_names: list[str] = []

    for name, sig in zip(names, signals, strict=False):
        q = evaluate_lead_quality(sig, fs, conditioned_signal=cond_map.get(name))
        q["voting_index"] = -6.0
        per_lead[name] = q
        if q["passed_absolute_gate"]:
            passing_names.append(name)

    fallback_lead = (
        max(names, key=lambda n: float(per_lead[n]["snr_db"]))
        if names
        else None
    )

    if not passing_names:
        return {
            "quorum_passed": False,
            "recommended_lead": None,
            "fallback_lead": fallback_lead,
            "selection_basis": "fallback_snr" if fallback_lead is not None else "none",
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
            "fallback_lead": fallback_lead,
            "selection_basis": "single_passing_lead",
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
        "fallback_lead": fallback_lead,
        "selection_basis": "stage2_voting",
        "passing_leads": passing_names,
        "rejected_leads": [n for n in names if n not in passing_names],
        "per_lead": per_lead,
    }
