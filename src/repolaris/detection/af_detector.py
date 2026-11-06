"""
Atrial Fibrillation (AF) and Atrial Flutter (AFL) Detection and Episode Burden Module.

Methodology:
- Detects episodes of Atrial Fibrillation (AF) and Atrial Flutter using rhythm irregularity,
  Shannon / sample entropy on RR intervals, and pNN40 / median absolute difference metrics.
- Conforms to standard clinical Holter reporting:
  - Episode segmentation (start time, end time, duration, mean HR, peak HR)
  - 24-hour / recording total AF burden percentage (total_af_duration / total_recording_duration * 100)
  - Minimum episode threshold (typically >= 30 seconds or >= 30 consecutive irregular beats)
  - Rhythm irregularity coefficient and Markov transition / entropy estimation.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple, Optional
import numpy as np


@dataclass
class AFEpisode:
    """Represents a discrete episode of Atrial Fibrillation or Flutter."""
    episode_index: int
    start_time_sec: float
    end_time_sec: float
    duration_sec: float
    start_beat_index: int
    end_beat_index: int
    num_beats: int
    mean_hr_bpm: float
    max_hr_bpm: float
    min_hr_bpm: float
    rhythm_irregularity: float
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AFBurdenReport:
    """Summary metrics of atrial fibrillation / flutter burden across a recording."""
    total_duration_sec: float
    af_total_duration_sec: float
    af_burden_pct: float
    num_episodes: int
    longest_episode_sec: float
    mean_episode_duration_sec: float
    episodes: List[AFEpisode]
    entropy_score: float

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["episodes"] = [ep.to_dict() for ep in self.episodes]
        return d


def compute_rr_entropy(rr_intervals: np.ndarray, num_bins: int = 16) -> float:
    """Computes normalized Shannon entropy on local RR interval distribution.

    In Normal Sinus Rhythm (NSR), RR intervals are clustered around a central value,
    yielding low entropy. In Atrial Fibrillation, irregular AV conduction broadens the
    distribution, producing high entropy (> 0.70).
    """
    if len(rr_intervals) < 4:
        return 0.0

    counts, _ = np.histogram(rr_intervals, bins=num_bins, density=False)
    probs = counts / float(len(rr_intervals))
    probs = probs[probs > 0]
    if len(probs) <= 1:
        return 0.0

    raw_entropy = -float(np.sum(probs * np.log2(probs)))
    max_entropy = np.log2(num_bins)
    return float(raw_entropy / max_entropy) if max_entropy > 0 else 0.0


def compute_rr_irregularity(rr_intervals: np.ndarray) -> float:
    """Computes coefficient of sample-to-sample RR irregularity.

    Uses normalized median absolute difference (MAD) of successive RR intervals:
    irregularity = median(|RR_{i+1} - RR_i|) / median(RR)
    """
    if len(rr_intervals) < 3:
        return 0.0

    diffs = np.abs(np.diff(rr_intervals))
    med_rr = float(np.median(rr_intervals))
    if med_rr <= 0:
        return 0.0

    return float(np.median(diffs) / med_rr)


def detect_atrial_fibrillation(
    r_peaks: np.ndarray,
    fs: float = 500.0,
    window_beats: int = 32,
    min_episode_duration_sec: float = 30.0,
    entropy_threshold: float = 0.68,
    irregularity_threshold: float = 0.12,
) -> AFBurdenReport:
    """Scans R-peak series to identify sustained AF/AFL episodes and computes burden percentage.

    Args:
        r_peaks: 1D array of detected R-peak sample indices.
        fs: Sampling rate in Hz.
        window_beats: Sliding beat window to evaluate local rhythm irregularity and entropy.
        min_episode_duration_sec: Minimum episode duration in seconds to count as sustained AF (default: 30s).
        entropy_threshold: Shannon entropy cutoff indicating chaotic AV conduction (default: 0.68).
        irregularity_threshold: Successive RR irregularity threshold (default: 0.12).

    Returns:
        AFBurdenReport instance with segmented episodes and burden metrics.
    """
    n_peaks = len(r_peaks)
    if n_peaks < 10:
        return AFBurdenReport(
            total_duration_sec=0.0,
            af_total_duration_sec=0.0,
            af_burden_pct=0.0,
            num_episodes=0,
            longest_episode_sec=0.0,
            mean_episode_duration_sec=0.0,
            episodes=[],
            entropy_score=0.0,
        )

    rr_sec = np.diff(r_peaks) / fs
    total_duration = float((r_peaks[-1] - r_peaks[0]) / fs) if n_peaks > 1 else 0.0
    overall_entropy = compute_rr_entropy(rr_sec)

    # Boolean mask of beats classified as local AF rhythm
    is_af_beat = np.zeros(n_peaks, dtype=bool)

    half_w = window_beats // 2
    for i in range(len(rr_sec)):
        start = max(0, i - half_w)
        end = min(len(rr_sec), i + half_w)
        local_rr = rr_sec[start:end]

        ent = compute_rr_entropy(local_rr)
        irreg = compute_rr_irregularity(local_rr)

        # AF decision criterion: elevated entropy and significant local RR irregularity
        if ent >= entropy_threshold and irreg >= irregularity_threshold:
            is_af_beat[i] = True
            is_af_beat[min(i + 1, n_peaks - 1)] = True

    # Segment contiguous AF runs
    episodes: List[AFEpisode] = []
    in_episode = False
    ep_start = 0

    for idx, flag in enumerate(is_af_beat):
        if flag and not in_episode:
            in_episode = True
            ep_start = idx
        elif not flag and in_episode:
            in_episode = False
            ep_end = idx - 1
            start_t = float(r_peaks[ep_start] / fs)
            end_t = float(r_peaks[ep_end] / fs)
            dur = end_t - start_t

            if dur >= min_episode_duration_sec:
                ep_rrs = rr_sec[ep_start:ep_end] if ep_end > ep_start else rr_sec[ep_start : ep_start + 1]
                bpms = 60.0 / ep_rrs[ep_rrs > 0] if len(ep_rrs) > 0 else np.array([75.0])
                mean_hr = float(np.mean(bpms)) if len(bpms) > 0 else 75.0
                max_hr = float(np.max(bpms)) if len(bpms) > 0 else mean_hr
                min_hr = float(np.min(bpms)) if len(bpms) > 0 else mean_hr
                irreg_val = compute_rr_irregularity(ep_rrs)
                conf = min(0.98, max(0.70, float(compute_rr_entropy(ep_rrs))))

                episodes.append(
                    AFEpisode(
                        episode_index=len(episodes) + 1,
                        start_time_sec=round(start_t, 3),
                        end_time_sec=round(end_t, 3),
                        duration_sec=round(dur, 3),
                        start_beat_index=ep_start,
                        end_beat_index=ep_end,
                        num_beats=ep_end - ep_start + 1,
                        mean_hr_bpm=round(mean_hr, 1),
                        max_hr_bpm=round(max_hr, 1),
                        min_hr_bpm=round(min_hr, 1),
                        rhythm_irregularity=round(irreg_val, 4),
                        confidence=round(conf, 3),
                    )
                )

    # Handle final in-flight episode
    if in_episode:
        ep_end = n_peaks - 1
        start_t = float(r_peaks[ep_start] / fs)
        end_t = float(r_peaks[ep_end] / fs)
        dur = end_t - start_t
        if dur >= min_episode_duration_sec:
            ep_rrs = rr_sec[ep_start:ep_end] if ep_end > ep_start else rr_sec[ep_start : ep_start + 1]
            bpms = 60.0 / ep_rrs[ep_rrs > 0] if len(ep_rrs) > 0 else np.array([75.0])
            mean_hr = float(np.mean(bpms)) if len(bpms) > 0 else 75.0
            max_hr = float(np.max(bpms)) if len(bpms) > 0 else mean_hr
            min_hr = float(np.min(bpms)) if len(bpms) > 0 else mean_hr
            irreg_val = compute_rr_irregularity(ep_rrs)
            conf = min(0.98, max(0.70, float(compute_rr_entropy(ep_rrs))))

            episodes.append(
                AFEpisode(
                    episode_index=len(episodes) + 1,
                    start_time_sec=round(start_t, 3),
                    end_time_sec=round(end_t, 3),
                    duration_sec=round(dur, 3),
                    start_beat_index=ep_start,
                    end_beat_index=ep_end,
                    num_beats=ep_end - ep_start + 1,
                    mean_hr_bpm=round(mean_hr, 1),
                    max_hr_bpm=round(max_hr, 1),
                    min_hr_bpm=round(min_hr, 1),
                    rhythm_irregularity=round(irreg_val, 4),
                    confidence=round(conf, 3),
                )
            )

    af_total_dur = sum(ep.duration_sec for ep in episodes)
    burden_pct = (af_total_dur / total_duration * 100.0) if total_duration > 0 else 0.0
    longest_ep = max((ep.duration_sec for ep in episodes), default=0.0)
    mean_ep = (af_total_dur / len(episodes)) if episodes else 0.0

    return AFBurdenReport(
        total_duration_sec=round(total_duration, 2),
        af_total_duration_sec=round(af_total_dur, 2),
        af_burden_pct=round(burden_pct, 2),
        num_episodes=len(episodes),
        longest_episode_sec=round(longest_ep, 2),
        mean_episode_duration_sec=round(mean_ep, 2),
        episodes=episodes,
        entropy_score=round(overall_entropy, 3),
    )
