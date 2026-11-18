"""Ambulatory ST-Segment Level, Slope & Transient Ischemia Detection module.

Implements automated beat-by-beat J+60 ms / J+80 ms ST-segment deviation and slope
measurement referenced to each cardiac cycle's local PQ isoelectric baseline, paired
with SQI-gated transient ischemic episode segmentation (>= 100 uV horizontal/downsloping
depression or elevation sustained for >= 60 s) and hourly ST trend aggregation.

References:
    - Crawford M.H., Bernstein S.J., Deedwania P.C., et al. (1999). "ACC/AHA Guidelines
      for Ambulatory Electrocardiography." JACC, 34(3), 912-948.
    - Kligfield P., Gettes L.S., Bailey J.J., et al. (2007). "Recommendations for the
      Standardization and Interpretation of the Electrocardiogram." Circulation, 115(10), 1306-1324.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from repolaris.detection.q_onset import detect_j_point, detect_q_onset
from repolaris.detection.qrs import detect_r_peaks


@dataclass
class STIschemicEpisode:
    """Represents a sustained ambulatory ST-segment elevation or depression episode."""

    episode_index: int
    episode_type: str  # 'ST_DEPRESSION' or 'ST_ELEVATION'
    start_time_sec: float
    end_time_sec: float
    duration_sec: float
    mean_st_deviation_uv: float
    peak_st_deviation_uv: float
    mean_st_slope_mv_per_sec: float
    slope_morphology: str
    mean_hr_bpm: float

    def to_dict(self) -> dict[str, Any]:
        """Serializes the ischemic episode to a dictionary."""
        return asdict(self)


def evaluate_beat_st_segment(
    signal: np.ndarray,
    q_onset_sample: int,
    j_point_sample: int,
    fs: float,
    hr_bpm: float = 72.0,
) -> dict[str, Any]:
    """Computes J+60 ms and J+80 ms ST deviation (uV/mV) and ST slope relative to local PQ baseline.

    Per ACC/AHA guidelines, selects J+80 ms as the primary measurement point when heart rate
    is <= 120 BPM, and J+60 ms when heart rate exceeds 120 BPM.
    """
    n_sig = len(signal)
    if n_sig < 10 or fs <= 0:
        return {
            "pq_baseline_mv": 0.0,
            "st_j60_mv": 0.0,
            "st_j80_mv": 0.0,
            "st_j60_uv": 0.0,
            "st_j80_uv": 0.0,
            "st_level_uv": 0.0,
            "st_level_mv": 0.0,
            "st_slope_mv_per_sec": 0.0,
            "st_morphology": "ISOELECTRIC",
            "measurement_offset_ms": 80,
        }

    q_idx = int(np.clip(q_onset_sample, 0, n_sig - 1))
    j_idx = int(np.clip(j_point_sample, q_idx, n_sig - 1))

    # Local PQ isoelectric baseline: [-45 ms, -8 ms] prior to Q-onset
    pq_start = max(0, q_idx - max(3, int(round(0.045 * fs))))
    pq_end = max(pq_start + 1, q_idx - max(1, int(round(0.008 * fs))))
    pq_base_mv = float(np.median(signal[pq_start:pq_end])) if pq_end > pq_start else float(signal[q_idx])

    # Average a narrow +/- 6 ms window around J+20 ms, J+60 ms, and J+80 ms to suppress thermal noise
    half_w = max(1, int(round(0.006 * fs)))

    def _sample_window_mv(offset_sec: float) -> float:
        center = min(n_sig - 1, j_idx + int(round(offset_sec * fs)))
        w0 = max(0, center - half_w)
        w1 = min(n_sig, center + half_w + 1)
        return float(np.mean(signal[w0:w1])) - pq_base_mv

    st_j20_mv = _sample_window_mv(0.020)
    st_j60_mv = _sample_window_mv(0.060)
    st_j80_mv = _sample_window_mv(0.080)

    use_j60 = bool(np.isfinite(hr_bpm) and hr_bpm > 120.0)
    active_st_mv = st_j60_mv if use_j60 else st_j80_mv
    active_st_uv = active_st_mv * 1000.0

    # ST slope between J+20 ms and J+80 ms (60 ms span) in mV/s
    st_slope = (st_j80_mv - st_j20_mv) / 0.060

    if abs(active_st_uv) < 50.0:
        morph = "ISOELECTRIC"
    elif active_st_uv <= -100.0:
        if st_slope < -0.50:
            morph = "DOWNSLOPING_DEPRESSION"
        elif st_slope <= 0.85:
            morph = "HORIZONTAL_DEPRESSION"
        else:
            morph = "UPSLOPING_DEPRESSION"
    elif active_st_uv >= 100.0:
        morph = "ST_ELEVATION"
    else:
        morph = "BORDERLINE_SHIFT"

    return {
        "pq_baseline_mv": round(pq_base_mv, 4),
        "st_j60_mv": round(st_j60_mv, 4),
        "st_j80_mv": round(st_j80_mv, 4),
        "st_j60_uv": round(st_j60_mv * 1000.0, 2),
        "st_j80_uv": round(st_j80_mv * 1000.0, 2),
        "st_level_uv": round(active_st_uv, 2),
        "st_level_mv": round(active_st_mv, 4),
        "st_slope_mv_per_sec": round(st_slope, 3),
        "st_morphology": morph,
        "measurement_offset_ms": 60 if use_j60 else 80,
    }


def analyze_st_segment(
    signal: np.ndarray,
    fs: float = 500.0,
    beats: list[dict[str, Any]] | None = None,
    r_peaks: np.ndarray | None = None,
    threshold_uv: float = 100.0,
    min_episode_duration_sec: float = 60.0,
    sqi_passed: bool = True,
) -> dict[str, Any]:
    """Analyzes beat-by-beat ST-segment levels, detects sustained ischemic episodes, and bins hourly ST trends."""
    n_sig = len(signal)
    total_dur_sec = float(n_sig / fs) if fs > 0 else 0.0

    if beats is None:
        if r_peaks is None:
            r_peaks = detect_r_peaks(signal, fs)
        beats = []
        for idx, r_idx in enumerate(r_peaks):
            q_idx = detect_q_onset(signal, int(r_idx), fs)
            j_idx = detect_j_point(signal, int(r_idx), fs)
            rr_s = float((r_idx - r_peaks[idx - 1]) / fs) if idx > 0 else 0.85
            beats.append({
                "beat_index": idx,
                "r_peak_sample": int(r_idx),
                "time_sec": float(r_idx / fs),
                "q_onset_sample": int(q_idx),
                "j_point_sample": int(j_idx),
                "hr_bpm": 60.0 / rr_s if rr_s > 0 else 72.0,
                "beat_class": "N",
            })

    if not beats:
        return {
            "mean_st_j60_uv": 0.0,
            "mean_st_j80_uv": 0.0,
            "mean_st_level_uv": 0.0,
            "max_st_elevation_uv": 0.0,
            "max_st_depression_uv": 0.0,
            "mean_st_slope_mv_per_sec": 0.0,
            "num_episodes": 0,
            "episodes": [],
            "ischemic_burden_pct": 0.0,
            "hourly_st_trends": [],
            "verdict": "NORMAL",
        }

    beat_times: list[float] = []
    beat_st_uv: list[float] = []
    beat_j60_uv: list[float] = []
    beat_j80_uv: list[float] = []
    beat_slopes: list[float] = []
    beat_hrs: list[float] = []

    for b in beats:
        # Exclude ventricular ectopics ('V', 'F') and paced beats from primary ST ischemia tracking
        b_cls = str(b.get("beat_class", "N")).upper()
        if b_cls in ("V", "F") or b.get("is_paced", False):
            continue

        r_idx = int(b["r_peak_sample"])
        q_idx = int(b.get("q_onset_sample", detect_q_onset(signal, r_idx, fs)))
        j_idx = int(b.get("j_point_sample", detect_j_point(signal, r_idx, fs)))
        hr = float(b.get("hr_bpm", 72.0))
        if not np.isfinite(hr) or hr <= 0:
            hr = 72.0

        st_info = evaluate_beat_st_segment(signal, q_idx, j_idx, fs, hr_bpm=hr)
        b.update({
            "st_level_uv": st_info["st_level_uv"],
            "st_j60_uv": st_info["st_j60_uv"],
            "st_j80_uv": st_info["st_j80_uv"],
            "st_slope_mv_per_sec": st_info["st_slope_mv_per_sec"],
            "st_morphology": st_info["st_morphology"],
        })

        beat_times.append(float(b.get("time_sec", r_idx / fs)))
        beat_st_uv.append(float(st_info["st_level_uv"]))
        beat_j60_uv.append(float(st_info["st_j60_uv"]))
        beat_j80_uv.append(float(st_info["st_j80_uv"]))
        beat_slopes.append(float(st_info["st_slope_mv_per_sec"]))
        beat_hrs.append(hr)

    if not beat_st_uv:
        return {
            "mean_st_j60_uv": 0.0,
            "mean_st_j80_uv": 0.0,
            "mean_st_level_uv": 0.0,
            "max_st_elevation_uv": 0.0,
            "max_st_depression_uv": 0.0,
            "mean_st_slope_mv_per_sec": 0.0,
            "num_episodes": 0,
            "episodes": [],
            "ischemic_burden_pct": 0.0,
            "hourly_st_trends": [],
            "verdict": "NORMAL",
        }

    st_arr = np.asarray(beat_st_uv, dtype=np.float64)
    j60_arr = np.asarray(beat_j60_uv, dtype=np.float64)
    j80_arr = np.asarray(beat_j80_uv, dtype=np.float64)
    slope_arr = np.asarray(beat_slopes, dtype=np.float64)
    times_arr = np.asarray(beat_times, dtype=np.float64)
    hrs_arr = np.asarray(beat_hrs, dtype=np.float64)

    # Smooth beat-by-beat ST series with a 5-beat median filter to prevent single-beat motion spikes
    n_b = len(st_arr)
    smooth_st = np.copy(st_arr)
    if n_b >= 5:
        for i in range(n_b):
            w0 = max(0, i - 2)
            w1 = min(n_b, i + 3)
            smooth_st[i] = float(np.median(st_arr[w0:w1]))

    episodes: list[STIschemicEpisode] = []
    if sqi_passed:
        in_ep = False
        ep_type = ""
        ep_start_idx = 0

        for i in range(n_b):
            val = float(smooth_st[i])
            slp = float(slope_arr[i])
            # Ischemic depression requires <= -threshold_uv with horizontal or downsloping slope (<= 0.50 mV/s)
            is_dep = val <= -abs(threshold_uv) and (slp <= 0.85 or float(j60_arr[i]) <= -abs(threshold_uv))
            is_elev = val >= abs(threshold_uv)

            curr_type = "ST_DEPRESSION" if is_dep else ("ST_ELEVATION" if is_elev else "")

            if not in_ep and curr_type:
                in_ep = True
                ep_type = curr_type
                ep_start_idx = i
            elif in_ep and curr_type != ep_type:
                t0 = float(times_arr[ep_start_idx])
                t1 = float(times_arr[i - 1])
                # Add one beat duration for single/terminal beat span
                est_beat_dur = 60.0 / float(np.mean(hrs_arr[ep_start_idx:i])) if i > ep_start_idx else 0.8
                dur = (t1 - t0) + est_beat_dur
                if dur >= min_episode_duration_sec:
                    seg_st = st_arr[ep_start_idx:i]
                    seg_slp = slope_arr[ep_start_idx:i]
                    seg_hr = hrs_arr[ep_start_idx:i]
                    peak_uv = float(np.min(seg_st)) if ep_type == "ST_DEPRESSION" else float(np.max(seg_st))
                    mean_slp = float(np.mean(seg_slp))
                    s_morph = "DOWNSLOPING" if mean_slp < -0.50 else ("HORIZONTAL" if mean_slp <= 0.85 else "UPSLOPING")
                    episodes.append(
                        STIschemicEpisode(
                            episode_index=len(episodes) + 1,
                            episode_type=ep_type,
                            start_time_sec=round(t0, 2),
                            end_time_sec=round(t0 + dur, 2),
                            duration_sec=round(dur, 2),
                            mean_st_deviation_uv=round(float(np.mean(seg_st)), 2),
                            peak_st_deviation_uv=round(peak_uv, 2),
                            mean_st_slope_mv_per_sec=round(mean_slp, 3),
                            slope_morphology=s_morph,
                            mean_hr_bpm=round(float(np.mean(seg_hr)), 1),
                        )
                    )
                if curr_type:
                    in_ep = True
                    ep_type = curr_type
                    ep_start_idx = i
                else:
                    in_ep = False
                    ep_type = ""

        if in_ep:
            t0 = float(times_arr[ep_start_idx])
            t1 = float(times_arr[-1])
            est_beat_dur = 60.0 / float(np.mean(hrs_arr[ep_start_idx:]))
            dur = (t1 - t0) + est_beat_dur
            if dur >= min_episode_duration_sec:
                seg_st = st_arr[ep_start_idx:]
                seg_slp = slope_arr[ep_start_idx:]
                seg_hr = hrs_arr[ep_start_idx:]
                peak_uv = float(np.min(seg_st)) if ep_type == "ST_DEPRESSION" else float(np.max(seg_st))
                mean_slp = float(np.mean(seg_slp))
                s_morph = "DOWNSLOPING" if mean_slp < -0.50 else ("HORIZONTAL" if mean_slp <= 0.85 else "UPSLOPING")
                episodes.append(
                    STIschemicEpisode(
                        episode_index=len(episodes) + 1,
                        episode_type=ep_type,
                        start_time_sec=round(t0, 2),
                        end_time_sec=round(min(max(total_dur_sec, t0 + dur), t0 + dur), 2),
                        duration_sec=round(dur, 2),
                        mean_st_deviation_uv=round(float(np.mean(seg_st)), 2),
                        peak_st_deviation_uv=round(peak_uv, 2),
                        mean_st_slope_mv_per_sec=round(mean_slp, 3),
                        slope_morphology=s_morph,
                        mean_hr_bpm=round(float(np.mean(seg_hr)), 1),
                    )
                )

    ischemic_time = sum(ep.duration_sec for ep in episodes)
    eff_dur = max(total_dur_sec, float(times_arr[-1]) + 1.0)
    burden_pct = min(100.0, (ischemic_time / eff_dur * 100.0)) if eff_dur > 0 else 0.0

    # Hourly ST trend bins (1-hour epochs)
    n_hours = max(1, int(np.ceil(eff_dur / 3600.0)))
    hourly_st: list[dict[str, Any]] = []
    for h_idx in range(n_hours):
        h_start = h_idx * 3600.0
        h_end = (h_idx + 1) * 3600.0
        h_mask = (times_arr >= h_start) & (times_arr < h_end)
        if np.any(h_mask):
            h_vals = st_arr[h_mask]
            h_slps = slope_arr[h_mask]
            hourly_st.append({
                "hour_index": h_idx + 1,
                "mean_st_uv": round(float(np.mean(h_vals)), 2),
                "min_st_uv": round(float(np.min(h_vals)), 2),
                "max_st_uv": round(float(np.max(h_vals)), 2),
                "mean_slope_mv_per_sec": round(float(np.mean(h_slps)), 3),
            })
        else:
            hourly_st.append({
                "hour_index": h_idx + 1,
                "mean_st_uv": 0.0,
                "min_st_uv": 0.0,
                "max_st_uv": 0.0,
                "mean_slope_mv_per_sec": 0.0,
            })

    max_elev = max(0.0, float(np.max(st_arr)))
    max_dep = min(0.0, float(np.min(st_arr)))
    mean_st = float(np.mean(st_arr))

    if episodes:
        verdict = "ISCHEMIC_EPISODES_DETECTED"
    elif abs(mean_st) >= abs(threshold_uv):
        verdict = "ST_SHIFT_DETECTED"
    else:
        verdict = "NORMAL"

    return {
        "mean_st_j60_uv": round(float(np.mean(j60_arr)), 2),
        "mean_st_j80_uv": round(float(np.mean(j80_arr)), 2),
        "mean_st_level_uv": round(mean_st, 2),
        "max_st_elevation_uv": round(max_elev, 2),
        "max_st_depression_uv": round(max_dep, 2),
        "mean_st_slope_mv_per_sec": round(float(np.mean(slope_arr)), 3),
        "num_episodes": len(episodes),
        "episodes": [ep.to_dict() for ep in episodes],
        "ischemic_burden_pct": round(float(burden_pct), 2),
        "hourly_st_trends": hourly_st,
        "verdict": verdict,
    }
