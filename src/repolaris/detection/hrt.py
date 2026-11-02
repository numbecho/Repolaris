"""Heart Rate Turbulence (HRT) Baroreflex Analysis module.

Evaluates the biphasic ventriculophasic autonomic baroreflex response of the sinoatrial
node following solitary Premature Ventricular Contractions (PVCs / Class 'V'):
1. Turbulence Onset (TO): Early post-extrasystolic sinus acceleration (%).
2. Turbulence Slope (TS): Late post-extrasystolic sinus deceleration (ms/beat).
3. Three-tier ISHNE clinical mortality risk stratification (Category 0, 1, and 2).

References:
    - Schmidt, G., Malik, M., Barthel, P., et al. (1999). Heart-rate turbulence after
      ventricular premature beats as a predictor of mortality after acute myocardial
      infarction. The Lancet, 353(9162), 1390-1396.
    - Bauer, A., Malik, M., Schmidt, G., et al. (2008). Heart rate turbulence: standards
      of measurement, physiological interpretation, and clinical use: International Society
      for Holter and Noninvasive Electrophysiology Consensus. JACC, 52(17), 1353-1365.
"""

from __future__ import annotations

from typing import Any
import numpy as np


def _extract_label(beat: Any) -> str:
    """Normalizes beat classification representation to uppercase AAMI character code."""
    if isinstance(beat, str):
        return beat.strip().upper()
    if isinstance(beat, dict):
        val = beat.get("beat_class", beat.get("label", "N"))
        return str(getattr(val, "value", val)).strip().upper()
    if hasattr(beat, "beat_class"):
        bc = getattr(beat, "beat_class")
        return str(getattr(bc, "value", bc)).strip().upper()
    return "N"


def compute_heart_rate_turbulence(
    classified_beats: list[Any],
    r_peaks: np.ndarray,
    fs: float = 500.0,
    min_post_sinus_beats: int = 15,
    max_post_sinus_beats: int = 20,
    prematurity_threshold: float = 0.85,
    compensatory_threshold: float = 1.15,
) -> dict[str, Any]:
    """Computes Turbulence Onset (TO), Turbulence Slope (TS), and ISHNE risk category.

    Args:
        classified_beats: Sequence of ClassifiedBeat objects, beat dicts, or AAMI label strings.
        r_peaks: 1D array of R-peak sample indices.
        fs: Sampling frequency in Hz (default: 500.0).
        min_post_sinus_beats: Minimum consecutive post-PVC sinus intervals required (default: 15;
            automatically adapts down to 6 for short synthetic/resting strips if needed).
        max_post_sinus_beats: Maximum post-PVC sinus intervals for ensemble averaging (default: 20).
        prematurity_threshold: Maximum ratio of coupling interval to reference sinus RR (default: 0.85).
        compensatory_threshold: Minimum ratio of compensatory pause to reference sinus RR (default: 1.15).

    Returns:
        Dictionary containing:
            - 'turbulence_onset': Mean/ensemble TO in percent (normal < 0.0%).
            - 'turbulence_slope': Ensemble TS in ms/beat (normal > 2.5 ms/beat).
            - 'category': ISHNE risk category (0 = Normal, 1 = Intermediate, 2 = High Risk,
              or None if no qualifying solitary PVCs exist).
            - 'valid_pvc_count': Number of solitary PVCs passing purity filtering.
            - 'ensemble_tachogram_ms': 1D array of averaged [NN_-2, NN_-1, coupling, pause, NN_1..NN_K].
            - 'episodes': List of individual PVC turbulence dictionaries.
    """
    peaks = np.asarray(r_peaks, dtype=np.float64)
    n_peaks = len(peaks)
    if n_peaks < 8 or len(classified_beats) != n_peaks:
        return {
            "turbulence_onset": None,
            "turbulence_slope": None,
            "category": None,
            "valid_pvc_count": 0,
            "ensemble_tachogram_ms": np.zeros(0, dtype=np.float64),
            "episodes": [],
        }

    labels = [_extract_label(b) for b in classified_beats]
    # rr_ms[i] is the interval between peak i and peak i+1 (length n_peaks - 1)
    rr_ms = (np.diff(peaks) / float(fs)) * 1000.0

    # Determine effective post-sinus requirement (allow >= 6 on short strips < 35 beats)
    eff_post = min_post_sinus_beats if n_peaks >= (min_post_sinus_beats + 6) else min(6, max(5, n_peaks - 5))

    episodes: list[dict[str, Any]] = []
    aligned_profiles: list[np.ndarray] = []

    # Beat p is the PVC R-peak index:
    # - Preceding sinus intervals: NN_{-2} = rr_ms[p-3], NN_{-1} = rr_ms[p-2] (beats p-3->p-2 and p-2->p-1 are 'N')
    # - Coupling interval: rr_ms[p-1] (beat p-1 -> PVC p)
    # - Compensatory pause: rr_ms[p] (PVC p -> beat p+1)
    # - Post-PVC sinus intervals: NN_1..NN_K = rr_ms[p+1 : p+1+K] (beats p+1..p+1+K are all 'N')
    for p in range(3, n_peaks - eff_post - 1):
        if labels[p] != "V":
            continue

        # Check sinus purity of preceding 3 beats (p-3, p-2, p-1)
        if not all(labels[idx] == "N" for idx in (p - 3, p - 2, p - 1)):
            continue

        # Determine how many pure sinus beats follow the PVC (up to max_post_sinus_beats + 1)
        avail_post = min(max_post_sinus_beats, n_peaks - 2 - p)
        if avail_post < eff_post:
            continue

        post_beat_labels = labels[p + 1 : p + 2 + eff_post]
        if not all(lbl == "N" for lbl in post_beat_labels):
            continue

        nn_minus_2 = float(rr_ms[p - 3])
        nn_minus_1 = float(rr_ms[p - 2])
        coupling_ms = float(rr_ms[p - 1])
        pause_ms = float(rr_ms[p])

        ref_nn = 0.5 * (nn_minus_2 + nn_minus_1)
        if ref_nn <= 200.0 or ref_nn >= 2500.0:
            continue

        # Verify coupling prematurity and post-extrasystolic compensatory pause
        if coupling_ms >= prematurity_threshold * ref_nn:
            continue
        if pause_ms <= compensatory_threshold * ref_nn:
            continue

        post_nn = rr_ms[p + 1 : p + 1 + eff_post].astype(np.float64)
        # physiological artifact filter on post_nn (200 ms < NN < 2500 ms)
        if np.any(post_nn < 200.0) or np.any(post_nn > 2500.0):
            continue

        nn_1 = float(post_nn[0])
        nn_2 = float(post_nn[1])
        to_pct = ((nn_1 + nn_2) - (nn_minus_2 + nn_minus_1)) / (nn_minus_2 + nn_minus_1) * 100.0

        # Individual episode TS across consecutive 5-beat windows
        ep_slopes: list[float] = []
        x_vec = np.arange(5, dtype=np.float64)
        for start_k in range(len(post_nn) - 4):
            seg = post_nn[start_k : start_k + 5]
            slope = float(np.polyfit(x_vec, seg, 1)[0])
            ep_slopes.append(slope)
        ep_ts = max(ep_slopes) if ep_slopes else 0.0

        profile = np.concatenate([[nn_minus_2, nn_minus_1, coupling_ms, pause_ms], post_nn])
        aligned_profiles.append(profile)
        episodes.append(
            {
                "pvc_beat_index": int(p),
                "pvc_sample": int(peaks[p]),
                "timestamp_sec": float(peaks[p] / fs),
                "to_percent": float(to_pct),
                "ts_ms_per_beat": float(ep_ts),
                "coupling_ms": coupling_ms,
                "compensatory_pause_ms": pause_ms,
            }
        )

    if not episodes:
        return {
            "turbulence_onset": None,
            "turbulence_slope": None,
            "category": None,
            "valid_pvc_count": 0,
            "ensemble_tachogram_ms": np.zeros(0, dtype=np.float64),
            "episodes": [],
        }

    # Mean TO across all valid PVC episodes (ISHNE standard)
    mean_to = float(np.mean([ep["to_percent"] for ep in episodes]))

    # Ensemble-averaged tachogram for Turbulence Slope (TS) calculation (ISHNE standard)
    min_prof_len = min(len(prof) for prof in aligned_profiles)
    ensemble_mat = np.vstack([prof[:min_prof_len] for prof in aligned_profiles])
    ensemble_tachogram = np.mean(ensemble_mat, axis=0)
    ensemble_post_nn = ensemble_tachogram[4:]

    x_vec = np.arange(5, dtype=np.float64)
    ts_candidates: list[float] = []
    for start_k in range(len(ensemble_post_nn) - 4):
        seg = ensemble_post_nn[start_k : start_k + 5]
        slope = float(np.polyfit(x_vec, seg, 1)[0])
        ts_candidates.append(slope)
    ensemble_ts = max(ts_candidates) if ts_candidates else 0.0

    # Three-tier ISHNE Risk Stratification:
    # Normal: TO < 0% and TS > 2.5 ms/beat -> Category 0
    # 1 abnormal parameter -> Category 1
    # Both abnormal (TO >= 0% and TS <= 2.5 ms/beat) -> Category 2
    to_abnormal = mean_to >= 0.0
    ts_abnormal = ensemble_ts <= 2.5
    if not to_abnormal and not ts_abnormal:
        category = 0
    elif to_abnormal and ts_abnormal:
        category = 2
    else:
        category = 1

    return {
        "turbulence_onset": mean_to,
        "turbulence_slope": float(ensemble_ts),
        "category": category,
        "valid_pvc_count": len(episodes),
        "ensemble_tachogram_ms": ensemble_tachogram,
        "episodes": episodes,
    }
