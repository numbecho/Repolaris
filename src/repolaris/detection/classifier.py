"""Abnormal Heartbeat Classifier and Arrhythmia Pattern Detection module.

Implements heartbeat morphology and interval feature extraction to classify
cardiac cycles into standard ANSI/AAMI EC57 diagnostic categories:
- N: Normal Sinus & Bundle Branch Block beats
- V: Premature Ventricular Contractions (PVC / VEB)
- S: Premature Atrial Contractions (PAC / SVEB)
- F: Fusion beats (ventricular + normal fusion)
- Q: Unknown / unclassifiable / artifact beats

Also detects structural ectopic rhythm sequences:
- Bigeminy (alternating Normal - Ectopic)
- Trigeminy (Normal - Normal - Ectopic)
- Ventricular Couplets (consecutive PVC pair)
- Ventricular Runs / Non-sustained VT (>= 3 consecutive PVCs)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


class BeatClass(str, Enum):
    """Standard ANSI/AAMI EC57 heartbeat classification codes."""
    NORMAL = "N"          # Normal, LBBB, RBBB, nodal escape
    PVC = "V"             # Premature Ventricular Contraction / Ventricular Ectopic
    PAC = "S"             # Premature Atrial Contraction / Supraventricular Ectopic
    FUSION = "F"          # Fusion of normal and ventricular beat
    UNKNOWN = "Q"         # Unclassifiable / Paced / Artifact


class RhythmPattern(str, Enum):
    """Repetitive cardiac rhythm and ectopic coupling sequences."""
    NORMAL_SINUS = "NSR"
    BIGEMINY = "BIGEMINY"
    TRIGEMINY = "TRIGEMINY"
    COUPLET = "COUPLET"
    VT_RUN = "VT_RUN"
    TACHYCARDIA = "TACHYCARDIA"
    BRADYCARDIA = "BRADYCARDIA"
    PAUSE = "PAUSE"
    ISOLATED_ECTOPIC = "ISOLATED"


@dataclass
class BeatFeatures:
    """Quantitative morphological and timing features for a single heartbeat."""
    pre_rr_sec: float
    post_rr_sec: float
    pre_rr_ratio: float           # RR_i / median(RR) - measures prematurity (<0.8 = premature)
    post_rr_ratio: float          # RR_{i+1} / median(RR) - measures compensatory pause (>1.1 = pause)
    compensatory_ratio: float     # (RR_i + RR_{i+1}) / (2 * median(RR)) - ~1.0 for full compensatory pause
    qrs_duration_ms: float        # Width of depolarization complex (>120 ms suggests ventricular origin)
    qrs_peak_to_peak_mv: float    # Peak-to-peak voltage within QRS window
    qrs_energy: float             # Sum of squared derivative/voltage samples
    template_correlation: float   # Pearson correlation with patient's dominant median normal template
    polarity: int                 # Dominant polarity (+1 positive R, -1 negative QS)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes features to a dictionary."""
        return asdict(self)


@dataclass
class ClassifiedBeat:
    """Enriched diagnostic beat record containing classifications and metrics."""
    beat_index: int
    r_peak_sample: int
    time_sec: float
    beat_class: BeatClass
    rhythm_pattern: RhythmPattern
    confidence: float
    features: BeatFeatures
    diagnostic_rationale: str

    def to_dict(self) -> Dict[str, Any]:
        """Serializes classified beat to a JSON-compatible dictionary."""
        d = asdict(self)
        d["beat_class"] = self.beat_class.value
        d["rhythm_pattern"] = self.rhythm_pattern.value
        return d


def compute_median_template(
    signal: np.ndarray,
    r_peaks: np.ndarray,
    fs: float,
    window_ms: float = 120.0,
) -> np.ndarray:
    """Computes a median baseline QRS template representing the patient's dominant normal beat.

    Args:
        signal: 1D filtered ECG voltage trace.
        r_peaks: 1D array of detected R-peak sample indices.
        fs: Sampling rate in Hertz.
        window_ms: Half-window duration around each R-peak (default: 120 ms).

    Returns:
        1D array containing the point-by-point median normal QRS waveform.
    """
    half_samples = int((window_ms / 1000.0) * fs)
    sig_len = len(signal)
    segments = []

    for r in r_peaks:
        start = r - half_samples
        end = r + half_samples
        if start >= 0 and end <= sig_len:
            segments.append(signal[start:end])

    if not segments:
        return np.zeros(2 * half_samples, dtype=np.float64)

    stacked = np.array(segments, dtype=np.float64)
    return np.median(stacked, axis=0)


def extract_beat_features(
    signal: np.ndarray,
    beat_idx: int,
    r_peaks: np.ndarray,
    q_onsets: np.ndarray,
    t_ends: np.ndarray,
    fs: float,
    median_template: np.ndarray,
    median_rr_sec: float,
) -> BeatFeatures:
    """Extracts electrophysiological and dynamic timing features for a specific heartbeat.

    Args:
        signal: 1D filtered ECG signal array.
        beat_idx: Index of current beat in r_peaks.
        r_peaks: 1D array of all R-peak sample indices.
        q_onsets: 1D array of Q-onset sample indices.
        t_ends: 1D array of T-end sample indices.
        fs: Sampling frequency in Hz.
        median_template: Patient's median QRS template waveform.
        median_rr_sec: Global median RR interval across the study.

    Returns:
        Populated BeatFeatures instance.
    """
    n_beats = len(r_peaks)
    r_curr = r_peaks[beat_idx]

    # 1. Preceding and succeeding RR intervals
    if beat_idx > 0:
        pre_rr_sec = float(r_curr - r_peaks[beat_idx - 1]) / fs
    else:
        pre_rr_sec = median_rr_sec

    if beat_idx < n_beats - 1:
        post_rr_sec = float(r_peaks[beat_idx + 1] - r_curr) / fs
    else:
        post_rr_sec = median_rr_sec

    norm_rr = max(median_rr_sec, 0.2)
    pre_rr_ratio = pre_rr_sec / norm_rr
    post_rr_ratio = post_rr_sec / norm_rr
    compensatory_ratio = (pre_rr_sec + post_rr_sec) / (2.0 * norm_rr)

    # 2. QRS morphology features
    q_on = q_onsets[beat_idx] if beat_idx < len(q_onsets) else r_curr - int(0.04 * fs)
    t_end = t_ends[beat_idx] if beat_idx < len(t_ends) else r_curr + int(0.3 * fs)

    # Estimate QRS offset as inflection ~40-60ms after R peak
    qrs_off_est = min(len(signal) - 1, r_curr + int(0.06 * fs))
    qrs_dur_ms = max(20.0, float(qrs_off_est - q_on) / fs * 1000.0)

    qrs_segment = signal[max(0, q_on): min(len(signal), qrs_off_est + 1)]
    if len(qrs_segment) > 1:
        p2p = float(np.max(qrs_segment) - np.min(qrs_segment))
        energy = float(np.sum(qrs_segment ** 2))
        polarity = 1 if signal[r_curr] >= np.mean(qrs_segment) else -1
    else:
        p2p = 1.0
        energy = 1.0
        polarity = 1

    # 3. Cross-correlation with dominant normal template
    template_len = len(median_template)
    half_t = template_len // 2
    t_start = r_curr - half_t
    t_end_samp = t_start + template_len

    if t_start >= 0 and t_end_samp <= len(signal) and np.std(median_template) > 1e-6:
        candidate = signal[t_start:t_end_samp]
        cand_std = np.std(candidate)
        if cand_std > 1e-6:
            corr = float(np.corrcoef(median_template, candidate)[0, 1])
        else:
            corr = 0.0
    else:
        corr = 1.0

    return BeatFeatures(
        pre_rr_sec=pre_rr_sec,
        post_rr_sec=post_rr_sec,
        pre_rr_ratio=pre_rr_ratio,
        post_rr_ratio=post_rr_ratio,
        compensatory_ratio=compensatory_ratio,
        qrs_duration_ms=qrs_dur_ms,
        qrs_peak_to_peak_mv=p2p,
        qrs_energy=energy,
        template_correlation=corr,
        polarity=polarity,
    )


def classify_heartbeat(
    features: BeatFeatures,
    pvc_pre_rr_threshold: float = 0.82,
    pvc_width_threshold_ms: float = 110.0,
    pvc_corr_threshold: float = 0.75,
) -> Tuple[BeatClass, float, str]:
    """Classifies a heartbeat using AAMI EC57 diagnostic criteria.

    Decision Rules:
    - PVC (V): Early prematurity (pre_rr_ratio < 0.82) combined with abnormal morphology
      (template_correlation < 0.75 or wide QRS > 110 ms) and compensatory pause.
    - PAC (S): Premature timing (pre_rr_ratio < 0.85) but normal narrow QRS morphology
      (template_correlation >= 0.80 and narrow QRS < 105 ms).
    - Fusion (F): Intermediate correlation (0.65 <= corr < 0.82) and moderately prolonged QRS.
    - Normal (N): Preserved cycle rhythm and high correlation with patient template.

    Args:
        features: Quantitative BeatFeatures instance.
        pvc_pre_rr_threshold: Prematurity ratio cutoff for ectopics (default: 0.82).
        pvc_width_threshold_ms: QRS duration boundary in ms (default: 110 ms).
        pvc_corr_threshold: Template correlation threshold (default: 0.75).

    Returns:
        Tuple of (BeatClass, confidence_score [0.0-1.0], diagnostic_rationale).
    """
    is_premature = features.pre_rr_ratio < pvc_pre_rr_threshold
    has_compensatory_pause = features.compensatory_ratio >= 0.92 and features.post_rr_ratio > 1.10
    is_wide_qrs = features.qrs_duration_ms >= pvc_width_threshold_ms
    is_morph_altered = features.template_correlation < pvc_corr_threshold

    # Rule 1: Premature Ventricular Contraction (PVC)
    if is_premature and (is_morph_altered or is_wide_qrs):
        conf = 0.85
        if has_compensatory_pause:
            conf += 0.10
        if is_morph_altered and is_wide_qrs:
            conf = min(0.99, conf + 0.04)
        rationale = (
            f"Premature beat (pre-RR {features.pre_rr_ratio:.2f}) with abnormal morphology "
            f"(corr: {features.template_correlation:.2f}, QRS: {features.qrs_duration_ms:.1f}ms)"
        )
        return BeatClass.PVC, conf, rationale

    # Rule 2: Premature Atrial Contraction (PAC / APB)
    if is_premature and not is_wide_qrs and features.template_correlation >= 0.80:
        conf = 0.85
        rationale = (
            f"Premature supraventricular beat (pre-RR {features.pre_rr_ratio:.2f}) with "
            f"preserved narrow QRS morphology (corr: {features.template_correlation:.2f})"
        )
        return BeatClass.PAC, conf, rationale

    # Rule 3: Fusion Beat (F)
    if is_premature and (0.60 <= features.template_correlation < 0.80):
        conf = 0.70
        rationale = (
            f"Fusion beat candidate with intermediate morphology "
            f"(corr: {features.template_correlation:.2f}, QRS: {features.qrs_duration_ms:.1f}ms)"
        )
        return BeatClass.FUSION, conf, rationale

    # Rule 4: Severely corrupted / unclassifiable beat (Q)
    if features.template_correlation < 0.30 and not is_premature:
        conf = 0.60
        rationale = f"Unclassifiable waveform or artifact (corr: {features.template_correlation:.2f})"
        return BeatClass.UNKNOWN, conf, rationale

    # Rule 5: Normal Sinus Beat (N)
    conf = min(0.99, max(0.70, features.template_correlation))
    rationale = f"Dominant sinus morphology (corr: {features.template_correlation:.2f}, RR: {features.pre_rr_sec:.2f}s)"
    return BeatClass.NORMAL, conf, rationale


def detect_rhythm_patterns(classified_beats: List[ClassifiedBeat]) -> List[ClassifiedBeat]:
    """Identifies multi-beat rhythm structures (Bigeminy, Trigeminy, Couplets, VT runs).

    Args:
        classified_beats: List of ClassifiedBeat instances with beat_class already assigned.

    Returns:
        List of ClassifiedBeat instances with rhythm_pattern updated.
    """
    n = len(classified_beats)
    if n == 0:
        return []

    classes = [b.beat_class for b in classified_beats]

    # Pass 1: Identify PVC Couplets and VT Runs
    i = 0
    while i < n:
        if classes[i] == BeatClass.PVC:
            # Count consecutive PVCs
            run_len = 1
            while i + run_len < n and classes[i + run_len] == BeatClass.PVC:
                run_len += 1

            if run_len >= 3:
                for k in range(i, i + run_len):
                    classified_beats[k].rhythm_pattern = RhythmPattern.VT_RUN
                    classified_beats[k].diagnostic_rationale += f" [VT Run of {run_len} beats]"
                i += run_len
                continue
            elif run_len == 2:
                classified_beats[i].rhythm_pattern = RhythmPattern.COUPLET
                classified_beats[i + 1].rhythm_pattern = RhythmPattern.COUPLET
                classified_beats[i].diagnostic_rationale += " [PVC Couplet 1/2]"
                classified_beats[i + 1].diagnostic_rationale += " [PVC Couplet 2/2]"
                i += 2
                continue
            else:
                classified_beats[i].rhythm_pattern = RhythmPattern.ISOLATED_ECTOPIC
                i += 1
                continue
        i += 1

    # Pass 2: Detect Bigeminy (N - V - N - V - N - V ...)
    for idx in range(1, n - 2):
        if (
            classes[idx - 1] == BeatClass.NORMAL
            and classes[idx] == BeatClass.PVC
            and classes[idx + 1] == BeatClass.NORMAL
            and classes[idx + 2] == BeatClass.PVC
        ):
            classified_beats[idx].rhythm_pattern = RhythmPattern.BIGEMINY
            classified_beats[idx + 2].rhythm_pattern = RhythmPattern.BIGEMINY

    # Pass 3: Detect Trigeminy (N - N - V - N - N - V ...)
    for idx in range(2, n - 3):
        if (
            classes[idx - 2] == BeatClass.NORMAL
            and classes[idx - 1] == BeatClass.NORMAL
            and classes[idx] == BeatClass.PVC
            and classes[idx + 1] == BeatClass.NORMAL
            and classes[idx + 2] == BeatClass.NORMAL
            and classes[idx + 3] == BeatClass.PVC
        ):
            classified_beats[idx].rhythm_pattern = RhythmPattern.TRIGEMINY
            classified_beats[idx + 3].rhythm_pattern = RhythmPattern.TRIGEMINY

    return classified_beats


def classify_all_beats(
    signal: np.ndarray,
    r_peaks: np.ndarray,
    q_onsets: np.ndarray,
    t_ends: np.ndarray,
    fs: float,
) -> Tuple[List[ClassifiedBeat], Dict[str, Any]]:
    """Master workflow: extracts features, classifies every beat, and detects rhythm patterns.

    Args:
        signal: 1D filtered ECG signal array.
        r_peaks: 1D array of detected R-peak sample indices.
        q_onsets: 1D array of Q-onset sample indices.
        t_ends: 1D array of T-end sample indices.
        fs: Sampling frequency in Hertz.

    Returns:
        A tuple of:
            - List of enriched ClassifiedBeat instances.
            - Statistical summary dictionary detailing beat counts and percentages per class.
    """
    n_peaks = len(r_peaks)
    if n_peaks == 0:
        return [], {"total_beats": 0, "counts": {}, "ectopic_burden_pct": 0.0}

    # 1. Study-wide normal template and median RR
    rr_intervals = np.diff(r_peaks) / fs if n_peaks > 1 else np.array([1.0])
    median_rr = float(np.median(rr_intervals))
    median_template = compute_median_template(signal, r_peaks, fs)

    classified_beats: List[ClassifiedBeat] = []

    # 2. Extract features and classify each beat
    for idx in range(n_peaks):
        features = extract_beat_features(
            signal=signal,
            beat_idx=idx,
            r_peaks=r_peaks,
            q_onsets=q_onsets,
            t_ends=t_ends,
            fs=fs,
            median_template=median_template,
            median_rr_sec=median_rr,
        )

        b_class, conf, rationale = classify_heartbeat(features)
        r_pattern = RhythmPattern.NORMAL_SINUS if b_class == BeatClass.NORMAL else RhythmPattern.ISOLATED_ECTOPIC

        classified_beats.append(
            ClassifiedBeat(
                beat_index=idx,
                r_peak_sample=int(r_peaks[idx]),
                time_sec=float(r_peaks[idx] / fs),
                beat_class=b_class,
                rhythm_pattern=r_pattern,
                confidence=float(conf),
                features=features,
                diagnostic_rationale=rationale,
            )
        )

    # 3. Scan sequence patterns across the classified beats
    classified_beats = detect_rhythm_patterns(classified_beats)

    # 4. Generate epidemiological burden summary
    counts: Dict[str, int] = {
        BeatClass.NORMAL.value: 0,
        BeatClass.PVC.value: 0,
        BeatClass.PAC.value: 0,
        BeatClass.FUSION.value: 0,
        BeatClass.UNKNOWN.value: 0,
    }
    rhythm_counts: Dict[str, int] = {
        RhythmPattern.BIGEMINY.value: 0,
        RhythmPattern.TRIGEMINY.value: 0,
        RhythmPattern.COUPLET.value: 0,
        RhythmPattern.VT_RUN.value: 0,
    }

    for b in classified_beats:
        counts[b.beat_class.value] = counts.get(b.beat_class.value, 0) + 1
        if b.rhythm_pattern.value in rhythm_counts:
            rhythm_counts[b.rhythm_pattern.value] += 1

    total = len(classified_beats)
    pvc_count = counts.get(BeatClass.PVC.value, 0)
    pac_count = counts.get(BeatClass.PAC.value, 0)
    ectopic_burden = float((pvc_count + pac_count) / total * 100.0) if total > 0 else 0.0

    summary = {
        "total_beats": total,
        "counts": counts,
        "pvc_count": pvc_count,
        "pac_count": pac_count,
        "ectopic_burden_pct": round(ectopic_burden, 2),
        "rhythm_patterns": rhythm_counts,
        "couplet_episodes": rhythm_counts.get(RhythmPattern.COUPLET.value, 0) // 2,
        "vt_runs": rhythm_counts.get(RhythmPattern.VT_RUN.value, 0) > 0,
    }

    return classified_beats, summary
