"""AF-Gated P-Wave Delineation, PR Interval, AV Block Screening & High-Rate Pacemaker Spike Guard module.

Implements:
1. AF-gated diastolic P-wave delineation (`P_onset`, `P_peak`, `P_end`) and beat-to-beat `PR`
   interval calculation on sinus beats.
2. Automated Atrioventricular (AV) conduction block screening:
   - First-Degree AV Block (`PR > 200 ms`).
   - Second-Degree AV Block Type I (Mobitz I / Wenckebach: progressive PR prolongation prior to a
     non-conducted P-wave pause, with post-pause PR shortening).
   - Second-Degree AV Block Type II (Mobitz II: constant PR intervals preceding and following a
     sudden non-conducted P-wave pause).
3. High-Rate Pacemaker Spike Guard (`detect_pacemaker_spikes`):
   - Strictly gated to `fs >= 1000.0 Hz` for raw waveform slew-rate (`dV/dt`) narrow-impulse
     ($0.5\text{–}2.5\text{ ms}$) detection so 250–500 Hz Holter EMG artifacts never trigger
     false pacing flags, while ingesting file metadata pacing flags at all sampling rates.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from repolaris.detection.q_onset import detect_q_onset
from repolaris.detection.qrs import detect_r_peaks


def detect_pacemaker_spikes(
    raw_signal: np.ndarray,
    fs: float,
    r_peaks: np.ndarray | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Detects narrow cardiac pacemaker impulses when fs >= 1000 Hz and reconciles metadata pacing status.

    At standard Holter sampling rates (250–500 Hz, 2–4 ms per sample), 0.5–1.5 ms bipolar
    pacing spikes alias into muscle/EMG noise. Therefore, raw voltage spike detection is
    strictly gated to `fs >= 1000.0 Hz`.
    """
    meta = metadata or {}
    pm_meta_raw = str(meta.get("pacemaker") or (meta.get("patient") or {}).get("pacemaker") or "NO").strip().upper()
    metadata_paced = pm_meta_raw not in ("", "NO", "NONE", "FALSE", "0", "ABSENT", "UNSPECIFIED")

    if fs < 1000.0 or len(raw_signal) < 10:
        return {
            "raw_spike_detection_enabled": False,
            "gating_reason": f"Sampling rate {fs:.0f} Hz < 1000 Hz minimum Nyquist pacing spike guard",
            "metadata_pacemaker_flag": metadata_paced,
            "metadata_pacemaker_mode": pm_meta_raw if metadata_paced else "NO",
            "spike_samples": [],
            "spike_count": 0,
            "paced_beat_indices": [],
            "paced_beat_count": 0,
            "pacing_detected": metadata_paced,
        }

    sig = np.asarray(raw_signal, dtype=np.float64)
    # First derivative slew rate in mV/ms
    dt_ms = 1000.0 / fs
    dv_dt = np.abs(np.diff(sig, prepend=sig[0])) / dt_ms

    laplacian = np.zeros_like(sig)
    laplacian[1:-1] = np.abs(2.0 * sig[1:-1] - sig[:-2] - sig[2:])
    med_dv = float(np.median(dv_dt))
    mad_dv = float(np.median(np.abs(dv_dt - med_dv))) + 1e-6
    # Require narrow-impulse slew rate >= 0.75 mV/ms and >= 10x MAD above background slew
    slew_thresh = max(0.75, med_dv + 10.0 * mad_dv)

    candidate_indices = np.where((dv_dt >= slew_thresh) & (laplacian >= 0.40))[0]
    spike_samples: list[int] = []
    max_pulse_samples = max(2, int(round(0.003 * fs)))  # <= 3 ms impulse return
    min_refractory = max(5, int(round(0.030 * fs)))     # 30 ms between distinct spikes

    for idx in candidate_indices:
        c_idx = int(idx)
        if spike_samples and (c_idx - spike_samples[-1]) < min_refractory:
            continue
        # Verify narrow impulse: derivative must reverse or return to baseline within 3 ms
        pre_idx = max(0, c_idx - 2)
        post_idx = min(len(sig) - 1, c_idx + max_pulse_samples)
        peak_win = sig[pre_idx : post_idx + 1]
        if len(peak_win) < 3:
            continue
        amp_excursion = float(np.max(np.abs(peak_win - sig[pre_idx])))
        return_diff = abs(float(sig[post_idx]) - float(sig[pre_idx]))
        # A true pacing spike has a sharp excursion (>= 0.25 mV) and returns near pre-spike voltage within 3 ms
        if amp_excursion >= 0.25 and return_diff <= 0.45 * amp_excursion:
            spike_samples.append(c_idx)

    paced_beat_indices: list[int] = []
    if r_peaks is not None and len(r_peaks) > 0 and spike_samples:
        spike_arr = np.asarray(spike_samples, dtype=np.int64)
        pre_r_window = int(round(0.085 * fs))  # Spike within 85 ms prior to R-peak
        for b_idx, r_samp in enumerate(r_peaks):
            r_int = int(r_samp)
            in_win = np.any((spike_arr >= (r_int - pre_r_window)) & (spike_arr <= r_int))
            if in_win:
                paced_beat_indices.append(int(b_idx))

    return {
        "raw_spike_detection_enabled": True,
        "gating_reason": f"Active high-rate slew guard (fs={fs:.0f} Hz >= 1000 Hz)",
        "metadata_pacemaker_flag": metadata_paced,
        "metadata_pacemaker_mode": pm_meta_raw if metadata_paced else "NO",
        "spike_samples": spike_samples,
        "spike_count": len(spike_samples),
        "paced_beat_indices": paced_beat_indices,
        "paced_beat_count": len(paced_beat_indices),
        "pacing_detected": bool(metadata_paced or len(spike_samples) > 0),
    }


def delineate_p_wave_single_beat(
    signal: np.ndarray,
    q_onset_sample: int,
    fs: float,
    rr_sec: float = 0.85,
) -> dict[str, Any]:
    """Searches the pre-Q diastolic window for the P-wave apex, onset, and offset."""
    n_sig = len(signal)
    q_idx = int(np.clip(q_onset_sample, 0, max(0, n_sig - 1)))
    min_pre_q = max(3, int(round(0.016 * fs)))
    max_lookback_ms = min(280.0, max(130.0, rr_sec * 1000.0 * 0.48))
    max_pre_q = max(min_pre_q + 6, int(round((max_lookback_ms / 1000.0) * fs)))

    w_start = max(0, q_idx - max_pre_q)
    w_end = max(w_start + 1, q_idx - min_pre_q)

    if (w_end - w_start) < 6 or fs <= 0:
        return {
            "p_detected": False,
            "p_onset_sample": None,
            "p_peak_sample": None,
            "p_end_sample": None,
            "pr_interval_ms": None,
            "p_duration_ms": None,
            "p_amplitude_mv": 0.0,
        }

    seg = np.asarray(signal[w_start:w_end], dtype=np.float64)
    # Smooth with a 16 ms moving average to emphasize P-wave energy (5-18 Hz) over EMG noise
    k_len = max(3, int(round(0.016 * fs)) | 1)
    if len(seg) > k_len:
        kernel = np.ones(k_len, dtype=np.float64) / float(k_len)
        smooth_seg = np.convolve(seg, kernel, mode="same")
    else:
        smooth_seg = seg

    iso_ref = float(np.percentile(smooth_seg, 25))
    dev = smooth_seg - iso_ref
    p_peak_rel = int(np.argmax(dev))
    p_amp = float(dev[p_peak_rel])

    if p_amp < 0.015:  # Require >= 15 uV P-wave deflection above diastolic baseline
        return {
            "p_detected": False,
            "p_onset_sample": None,
            "p_peak_sample": None,
            "p_end_sample": None,
            "pr_interval_ms": None,
            "p_duration_ms": None,
            "p_amplitude_mv": round(p_amp, 4),
        }

    thresh = 0.20 * p_amp
    # Locate P-onset before P-peak
    left_branch = dev[: p_peak_rel + 1]
    below_left = np.where(left_branch <= thresh)[0]
    p_on_rel = int(below_left[-1]) if len(below_left) > 0 else max(0, p_peak_rel - int(round(0.045 * fs)))

    # Locate P-end after P-peak
    right_branch = dev[p_peak_rel:]
    below_right = np.where(right_branch <= thresh)[0]
    p_end_rel = p_peak_rel + int(below_right[0]) if len(below_right) > 0 else min(len(seg) - 1, p_peak_rel + int(round(0.045 * fs)))

    p_on_samp = w_start + p_on_rel
    p_pk_samp = w_start + p_peak_rel
    p_end_samp = max(p_on_samp + 1, w_start + p_end_rel)

    pr_ms = float(q_idx - p_on_samp) / fs * 1000.0
    p_dur_ms = float(p_end_samp - p_on_samp) / fs * 1000.0

    if pr_ms < 70.0 or pr_ms > 480.0:
        return {
            "p_detected": False,
            "p_onset_sample": None,
            "p_peak_sample": None,
            "p_end_sample": None,
            "pr_interval_ms": None,
            "p_duration_ms": None,
            "p_amplitude_mv": round(p_amp, 4),
        }

    return {
        "p_detected": True,
        "p_onset_sample": int(p_on_samp),
        "p_peak_sample": int(p_pk_samp),
        "p_end_sample": int(p_end_samp),
        "pr_interval_ms": round(pr_ms, 2),
        "p_duration_ms": round(p_dur_ms, 2),
        "p_amplitude_mv": round(p_amp, 4),
    }


def analyze_p_waves_and_av_block(
    signal: np.ndarray,
    fs: float = 500.0,
    beats: list[dict[str, Any]] | None = None,
    r_peaks: np.ndarray | None = None,
    af_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Delineates P-waves (gated off during AF) and screens for 1st- and 2nd-degree (Mobitz I/II) AV block."""
    af_episodes = (af_report or {}).get("episodes", [])
    af_burden = float((af_report or {}).get("af_burden_pct", 0.0))

    if beats is None:
        if r_peaks is None:
            r_peaks = detect_r_peaks(signal, fs)
        beats = []
        for idx, r_idx in enumerate(r_peaks):
            q_idx = detect_q_onset(signal, int(r_idx), fs)
            rr_s = float((r_idx - r_peaks[idx - 1]) / fs) if idx > 0 else 0.85
            beats.append({
                "beat_index": idx,
                "r_peak_sample": int(r_idx),
                "time_sec": float(r_idx / fs),
                "q_onset_sample": int(q_idx),
                "rr_sec": rr_s,
                "beat_class": "N",
            })

    if not beats:
        return {
            "af_gated": False,
            "p_wave_detection_rate_pct": 0.0,
            "mean_pr_ms": 0.0,
            "max_pr_ms": 0.0,
            "mean_p_duration_ms": 0.0,
            "first_degree_av_block": False,
            "second_degree_av_block": "NONE",
            "dropped_p_wave_count": 0,
            "av_conduction_verdict": "NORMAL_AV_CONDUCTION",
        }

    def _in_af_episode(t_sec: float) -> bool:
        for ep in af_episodes:
            s_t = float(ep.get("start_time_sec", 0.0) if isinstance(ep, dict) else getattr(ep, "start_time_sec", 0.0))
            e_t = float(ep.get("end_time_sec", 0.0) if isinstance(ep, dict) else getattr(ep, "end_time_sec", 0.0))
            if s_t <= t_sec <= e_t:
                return True
        return False

    pr_values: list[float] = []
    p_durs: list[float] = []
    p_amps: list[float] = []
    sinus_evaluated = 0
    p_found_cnt = 0

    for b in beats:
        t_sec = float(b.get("time_sec", b["r_peak_sample"] / fs))
        b_cls = str(b.get("beat_class", "N")).upper()
        if af_burden >= 80.0 or _in_af_episode(t_sec) or b_cls in ("V", "F"):
            b["p_detected"] = False
            b["pr_ms"] = None
            continue

        sinus_evaluated += 1
        q_idx = int(b.get("q_onset_sample", detect_q_onset(signal, int(b["r_peak_sample"]), fs)))
        rr_s = float(b.get("rr_sec", 0.85) or 0.85)
        p_info = delineate_p_wave_single_beat(signal, q_idx, fs, rr_sec=rr_s)

        b["p_detected"] = bool(p_info["p_detected"])
        b["p_onset_sample"] = p_info["p_onset_sample"]
        b["p_peak_sample"] = p_info["p_peak_sample"]
        b["p_end_sample"] = p_info["p_end_sample"]
        b["pr_ms"] = p_info["pr_interval_ms"]

        if p_info["p_detected"] and p_info["pr_interval_ms"] is not None:
            p_found_cnt += 1
            pr_values.append(float(p_info["pr_interval_ms"]))
            if p_info["p_duration_ms"] is not None:
                p_durs.append(float(p_info["p_duration_ms"]))
            p_amps.append(float(p_info["p_amplitude_mv"]))

    if af_burden >= 80.0 and p_found_cnt == 0:
        return {
            "af_gated": True,
            "p_wave_detection_rate_pct": 0.0,
            "mean_pr_ms": 0.0,
            "max_pr_ms": 0.0,
            "mean_p_duration_ms": 0.0,
            "first_degree_av_block": False,
            "second_degree_av_block": "NONE",
            "dropped_p_wave_count": 0,
            "av_conduction_verdict": "AF_GATED_NO_SINUS_P",
        }

    mean_pr = float(np.mean(pr_values)) if pr_values else 0.0
    max_pr = float(np.max(pr_values)) if pr_values else 0.0
    mean_p_dur = float(np.mean(p_durs)) if p_durs else 0.0
    med_p_amp = float(np.median(p_amps)) if p_amps else 0.04
    det_rate = (p_found_cnt / sinus_evaluated * 100.0) if sinus_evaluated > 0 else 0.0

    # 1. First-degree AV block: mean PR > 200 ms and >= 50% of detected PR intervals > 200 ms
    prolonged_cnt = sum(1 for pr in pr_values if pr > 200.0)
    first_deg = bool(pr_values and mean_pr > 200.0 and (prolonged_cnt / len(pr_values)) >= 0.50)

    # 2. Second-degree AV block screening across RR pauses (RR_i >= 1.65 * median_RR)
    rr_all = [float(b.get("rr_sec", 0.0)) for b in beats if float(b.get("rr_sec", 0.0)) > 0.25]
    med_rr = float(np.median(rr_all)) if rr_all else 0.85

    dropped_p_cnt = 0
    mobitz_i_episodes = 0
    mobitz_ii_episodes = 0

    for idx in range(2, len(beats)):
        b_curr = beats[idx]
        rr_curr = float(b_curr.get("rr_sec", 0.0))
        if rr_curr < 1.65 * med_rr:
            continue

        # Search the mid-diastolic pause between beat idx-1 and beat idx for a non-conducted P-wave
        r_prev = int(beats[idx - 1]["r_peak_sample"])
        r_curr = int(b_curr["r_peak_sample"])
        gap_start = min(len(signal) - 1, r_prev + int(round(0.35 * med_rr * fs)))
        gap_end = max(gap_start + 1, r_curr - int(round(0.32 * med_rr * fs)))

        has_blocked_p = False
        if (gap_end - gap_start) >= int(round(0.08 * fs)):
            gap_seg = np.asarray(signal[gap_start:gap_end], dtype=np.float64)
            gap_amp = float(np.max(gap_seg) - np.median(gap_seg))
            if gap_amp >= max(0.025, 0.40 * med_p_amp):
                has_blocked_p = True
                dropped_p_cnt += 1

        if has_blocked_p:
            pr_prev2 = beats[idx - 2].get("pr_ms")
            pr_prev1 = beats[idx - 1].get("pr_ms")
            pr_post = b_curr.get("pr_ms")

            if pr_prev1 is not None and pr_post is not None:
                # Wenckebach (Mobitz I): pre-pause PR is prolonged relative to post-pause recovery PR by >= 18 ms
                # or progressive PR lengthening (pr_prev1 > pr_prev2 + 12 ms)
                prog_lengthen = (pr_prev2 is not None and (float(pr_prev1) - float(pr_prev2)) >= 12.0)
                post_shorten = (float(pr_prev1) - float(pr_post)) >= 18.0
                if prog_lengthen or post_shorten:
                    mobitz_i_episodes += 1
                else:
                    mobitz_ii_episodes += 1
            else:
                mobitz_ii_episodes += 1

    if mobitz_ii_episodes > 0:
        second_deg = "MOBITZ_TYPE_II"
    elif mobitz_i_episodes > 0:
        second_deg = "MOBITZ_TYPE_I_WENCKEBACH"
    else:
        second_deg = "NONE"

    if second_deg == "MOBITZ_TYPE_II":
        verdict = "SECOND_DEGREE_AV_BLOCK_MOBITZ_II"
    elif second_deg == "MOBITZ_TYPE_I_WENCKEBACH":
        verdict = "SECOND_DEGREE_AV_BLOCK_MOBITZ_I"
    elif first_deg:
        verdict = "FIRST_DEGREE_AV_BLOCK"
    else:
        verdict = "NORMAL_AV_CONDUCTION"

    return {
        "af_gated": False,
        "p_wave_detection_rate_pct": round(det_rate, 2),
        "mean_pr_ms": round(mean_pr, 2),
        "max_pr_ms": round(max_pr, 2),
        "mean_p_duration_ms": round(mean_p_dur, 2),
        "first_degree_av_block": first_deg,
        "second_degree_av_block": second_deg,
        "dropped_p_wave_count": int(dropped_p_cnt),
        "mobitz_i_count": int(mobitz_i_episodes),
        "mobitz_ii_count": int(mobitz_ii_episodes),
        "av_conduction_verdict": verdict,
    }
