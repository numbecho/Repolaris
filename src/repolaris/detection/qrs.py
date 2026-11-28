from __future__ import annotations

from collections import deque

import numpy as np
from scipy.signal import find_peaks


def _refine_r_peaks_polarity_locked(
    signal: np.ndarray,
    candidates: list[int],
    fs: float,
) -> np.ndarray:
    """Refines each candidate within +/-40 ms locked to dominant beat polarity."""
    if not candidates:
        return np.array([], dtype=int)
    n_samples = len(signal)
    rad40 = max(1, int(round(0.040 * fs)))
    dominant_sign = 0
    refined: list[int] = []

    for cp in candidates:
        start = max(0, int(cp) - rad40)
        end = min(n_samples, int(cp) + rad40 + 1)
        win = signal[start:end]
        if win.size == 0:
            continue
        pos_rel = int(np.argmax(win))
        neg_rel = int(np.argmin(win))
        pos_val = float(win[pos_rel])
        neg_mag = float(-win[neg_rel])

        if dominant_sign == 0:
            if pos_val >= neg_mag:
                dominant_sign = 1
                chosen = start + pos_rel
            else:
                dominant_sign = -1
                chosen = start + neg_rel
        elif dominant_sign > 0:
            if neg_mag > 1.5 * max(pos_val, 0.0):
                dominant_sign = -1
                chosen = start + neg_rel
            else:
                chosen = start + pos_rel
        else:
            if pos_val > 1.5 * max(neg_mag, 0.0):
                dominant_sign = 1
                chosen = start + pos_rel
            else:
                chosen = start + neg_rel

        refined.append(chosen)

    return np.unique(np.asarray(refined, dtype=int))


def _apply_adaptive_threshold_and_t_guard(
    envelope: np.ndarray,
    abs_diff: np.ndarray,
    fs: float,
    refractory_ms: float,
    t_wave_slope_ratio: float,
    candidate_min_height: float = 0.0,
    max_half_width_samples: int | None = None,
    diagnostics_out: dict[str, int] | None = None,
    signal: np.ndarray | None = None,
    min_qrs_amp_mv: float = 0.15,
) -> list[int]:
    """Causal 8-peak median adaptive thresholding with pause-safe silence recovery and T-wave guard."""
    n_samples = len(envelope)
    if n_samples < 4 or fs <= 0:
        return []
    if not np.all(np.isfinite(envelope)):
        envelope = np.nan_to_num(envelope, nan=0.0, posinf=0.0, neginf=0.0)
    if not np.all(np.isfinite(abs_diff)):
        abs_diff = np.nan_to_num(abs_diff, nan=0.0, posinf=0.0, neginf=0.0)

    hard_ref_samples = max(1, int(round((refractory_ms / 1000.0) * fs)))
    rad40 = max(1, int(round(0.040 * fs)))

    def _passes_amp_floor(sample_idx: int) -> bool:
        if signal is None or min_qrs_amp_mv <= 0.0:
            return True
        win = signal[max(0, sample_idx - rad40) : min(n_samples, sample_idx + rad40 + 1)]
        if win.size == 0:
            return False
        return float(np.max(win) - np.min(win)) >= min_qrs_amp_mv

    # Refractory-separated peak seeding over initial <=4s window (immune to both single spikes and MAD-clipping)
    init_n = min(n_samples, max(10, int(round(4.0 * fs))))
    init_seg = envelope[:init_n]
    raw_med = float(np.median(init_seg))
    med = raw_med if np.isfinite(raw_med) else 0.0
    npki_seed = max(med, 1e-12)

    init_pk_kwargs: dict[str, float | int] = {"distance": hard_ref_samples}
    if candidate_min_height > 0.0:
        init_pk_kwargs["height"] = candidate_min_height
    init_peaks, _ = find_peaks(init_seg, **init_pk_kwargs)
    if len(init_peaks) >= 2:
        top_vals = np.sort(init_seg[init_peaks])[-4:]
        seed_spki = float(np.median(top_vals))
    elif len(init_peaks) == 1:
        seed_spki = float(init_seg[init_peaks[0]])
    else:
        max_init = float(np.max(init_seg)) if init_seg.size > 0 else 0.0
        seed_spki = max_init / 3.0 if max_init > 0.0 else 1e-6

    spki_seed = max(seed_spki, 4.0 * npki_seed, 1e-6)
    qrs_peaks_buf: deque[float] = deque([spki_seed], maxlen=8)
    noise_peaks_buf: deque[float] = deque([npki_seed], maxlen=8)

    min_cand_dist = max(1, int(round(0.080 * fs)))
    cand_kwargs: dict[str, float | int] = {"distance": min_cand_dist}
    if candidate_min_height > 0.0:
        cand_kwargs["height"] = candidate_min_height
    candidates, _ = find_peaks(envelope, **cand_kwargs)

    accepted: list[int] = []
    rr_history: list[float] = []
    mean_rr = 0.8 * fs
    prev_r_slope = 0.0
    refractory_rejected = 0
    t_wave_rejected = 0
    init_silence_samples = int(round(4.0 * fs))
    last_decay_sample = 0

    for idx_i, cp_raw in enumerate(candidates):
        cp = int(cp_raw)
        val = float(envelope[cp])

        if max_half_width_samples is not None:
            half_lvl = med + 0.5 * (val - med)
            left = cp
            while left > 0 and envelope[left - 1] >= half_lvl:
                left -= 1
            right = cp
            while right + 1 < n_samples and envelope[right + 1] >= half_lvl:
                right += 1
            if (right - left + 1) > max_half_width_samples:
                noise_peaks_buf.append(val)
                continue

        if accepted and (cp - accepted[-1]) < hard_ref_samples:
            refractory_rejected += 1
            continue

        npki = float(np.median(noise_peaks_buf))
        spki = max(float(np.median(qrs_peaks_buf)), 2.0 * npki, 1e-6)
        thr1 = npki + 0.25 * (spki - npki)
        thr2 = max(0.4 * thr1, npki + 0.10 * (spki - npki))
        soft_zone_end = int(round(np.clip(0.45 * mean_rr, 0.280 * fs, 0.480 * fs)))
        cand_slope = float(np.max(abs_diff[max(0, cp - rad40) : min(n_samples, cp + rad40 + 1)]))

        if val >= thr1 and _passes_amp_floor(cp):
            if accepted and (cp - accepted[-1]) <= soft_zone_end and prev_r_slope > 0.0:
                if cand_slope < t_wave_slope_ratio * prev_r_slope:
                    t_wave_rejected += 1
                    noise_peaks_buf.append(val)
                    continue

            if accepted:
                rr_history.append(float(cp - accepted[-1]))
                if len(rr_history) > 8:
                    rr_history.pop(0)
                mean_rr = float(np.mean(rr_history))
            accepted.append(cp)
            qrs_peaks_buf.append(val)
            prev_r_slope = cand_slope if prev_r_slope <= 0.0 else (0.5 * cand_slope + 0.5 * prev_r_slope)
            last_decay_sample = cp
        else:
            noise_peaks_buf.append(val)
            silence_limit = max(1.4 * fs, 1.66 * mean_rr)
            in_searchback = bool(accepted and (cp - accepted[-1]) > 1.66 * mean_rr)
            in_lead_in_silence = bool(not accepted and cp > init_silence_samples)

            if in_searchback or in_lead_in_silence:
                max_sb_samples = max(hard_ref_samples + 1, int(round(max(2.5 * mean_rr, 3.0 * fs))))
                min_sb_sample = (
                    max(accepted[-1] + hard_ref_samples, cp - max_sb_samples)
                    if accepted
                    else max(0, cp - max_sb_samples)
                )

                # Standard thr2 search-back
                sb_best_cp = -1
                sb_best_val = -1.0
                for j in range(idx_i - 1, -1, -1):
                    cand_j = int(candidates[j])
                    if cand_j <= min_sb_sample:
                        break
                    v_j = float(envelope[cand_j])
                    if v_j >= thr2 and v_j > sb_best_val and _passes_amp_floor(cand_j):
                        sb_best_val = v_j
                        sb_best_cp = cand_j

                sb_accepted = False
                if sb_best_cp >= 0:
                    sb_slope = float(
                        np.max(abs_diff[max(0, sb_best_cp - rad40) : min(n_samples, sb_best_cp + rad40 + 1)])
                    )
                    t_guard_blocked = bool(
                        accepted
                        and (sb_best_cp - accepted[-1]) <= soft_zone_end
                        and prev_r_slope > 0.0
                        and sb_slope < t_wave_slope_ratio * prev_r_slope
                    )
                    if not t_guard_blocked:
                        if accepted:
                            rr_history.append(float(sb_best_cp - accepted[-1]))
                            if len(rr_history) > 8:
                                rr_history.pop(0)
                            mean_rr = float(np.mean(rr_history))
                        accepted.append(sb_best_cp)
                        qrs_peaks_buf.append(sb_best_val)
                        prev_r_slope = sb_slope if prev_r_slope <= 0.0 else (0.5 * sb_slope + 0.5 * prev_r_slope)
                        last_decay_sample = sb_best_cp
                        sb_accepted = True

                # 1.4s silence fallback (Pan-Tompkins++ Rule-2 analogue: 1-beat median re-seed on sudden drops)
                if not sb_accepted and (
                    (accepted and (cp - accepted[-1]) > silence_limit) or in_lead_in_silence
                ):
                    # Use baseline npki_seed (not missed-beat-polluted npki) when signal-domain 150 uV floor is active
                    fb_noise_guard = 2.0 * npki_seed if signal is not None else 6.0 * npki
                    fb_thr = max(0.2 * thr2, fb_noise_guard, 1e-6)
                    fb_best_cp = -1
                    fb_best_val = -1.0
                    for j in range(idx_i, -1, -1):
                        cand_j = int(candidates[j])
                        if cand_j <= min_sb_sample:
                            break
                        v_j = float(envelope[cand_j])
                        if v_j >= fb_thr and v_j > fb_best_val and _passes_amp_floor(cand_j):
                            fb_best_val = v_j
                            fb_best_cp = cand_j

                    if fb_best_cp >= 0:
                        fb_slope = float(
                            np.max(abs_diff[max(0, fb_best_cp - rad40) : min(n_samples, fb_best_cp + rad40 + 1)])
                        )
                        fb_t_blocked = bool(
                            accepted
                            and (fb_best_cp - accepted[-1]) <= soft_zone_end
                            and prev_r_slope > 0.0
                            and fb_slope < t_wave_slope_ratio * prev_r_slope
                        )
                        if not fb_t_blocked:
                            if accepted:
                                rr_history.append(float(fb_best_cp - accepted[-1]))
                                if len(rr_history) > 8:
                                    rr_history.pop(0)
                                mean_rr = float(np.mean(rr_history))
                            accepted.append(fb_best_cp)
                            qrs_peaks_buf = deque([fb_best_val], maxlen=8)
                            noise_peaks_buf = deque([npki_seed], maxlen=8)
                            prev_r_slope = fb_slope if prev_r_slope <= 0.0 else (0.5 * fb_slope + 0.5 * prev_r_slope)
                            last_decay_sample = fb_best_cp
                            sb_accepted = True

                    # Rate-limited halving during prolonged silence with no valid candidate
                    if not sb_accepted and (cp - last_decay_sample) >= silence_limit:
                        floor_val = max(6.0 * npki, 1e-6)
                        qrs_peaks_buf = deque(
                            (max(floor_val, 0.5 * v) for v in qrs_peaks_buf),
                            maxlen=8,
                        )
                        last_decay_sample = cp

    if diagnostics_out is not None:
        diagnostics_out["refractory_rejected"] = refractory_rejected
        diagnostics_out["t_wave_rejected"] = t_wave_rejected

    return accepted


def detect_r_peaks_phasor_adaptive(
    filtered_signal: np.ndarray,
    fs: float,
    refractory_ms: float = 200.0,
    t_wave_slope_ratio: float = 0.50,
    diagnostics_out: dict[str, int] | None = None,
) -> np.ndarray:
    """Adaptive-scale, slope-conditioned Phasor Transform R-peak detector for ablation studies."""
    sig = np.asarray(filtered_signal, dtype=np.float64)
    n_samples = len(sig)
    if n_samples < 4 or fs <= 0:
        return np.array([], dtype=int)
    if not np.all(np.isfinite(sig)):
        sig = np.nan_to_num(sig, nan=0.0, posinf=0.0, neginf=0.0)

    diff = np.diff(sig, prepend=sig[0])
    abs_diff = np.abs(diff)
    squared = diff ** 2
    win_len = max(3, int(round(0.080 * fs)))
    e_slope = np.convolve(squared, np.ones(win_len) / win_len, mode="same")

    block_len = max(1, int(round(fs)))
    n_blocks = max(1, (n_samples + block_len - 1) // block_len)
    block_mads = np.empty(n_blocks, dtype=np.float64)
    for b in range(n_blocks):
        b_start = b * block_len
        b_end = min(n_samples, b_start + block_len)
        seg = e_slope[b_start:b_end]
        med = float(np.median(seg))
        block_mads[b] = float(np.median(np.abs(seg - med)))

    rv_blocks = np.empty(n_blocks, dtype=np.float64)
    block_meds = np.empty(n_blocks, dtype=np.float64)
    for b in range(n_blocks):
        b_start = b * block_len
        b_end = min(n_samples, b_start + block_len)
        block_meds[b] = float(np.median(e_slope[b_start:b_end]))

    med_blocks = np.empty(n_blocks, dtype=np.float64)
    for b in range(n_blocks):
        w0 = max(0, b - 2)
        w1 = min(n_blocks, b + 3)
        med_blocks[b] = float(np.median(block_meds[w0:w1]))
        rv_blocks[b] = max(1.5 * float(np.median(block_mads[w0:w1])), 1e-6)

    block_centers = np.minimum(n_samples - 1, (np.arange(n_blocks) * block_len) + (block_len // 2))
    if n_blocks == 1:
        rv = np.full(n_samples, rv_blocks[0], dtype=np.float64)
        base_e = np.full(n_samples, med_blocks[0], dtype=np.float64)
    else:
        x_idx = np.arange(n_samples, dtype=np.float64)
        c_idx = block_centers.astype(np.float64)
        rv = np.interp(x_idx, c_idx, rv_blocks)
        base_e = np.interp(x_idx, c_idx, med_blocks)

    phi = np.arctan(np.maximum(0.0, e_slope - base_e) / rv)
    max_width_samples = max(1, int(round(0.180 * fs)))
    candidates = _apply_adaptive_threshold_and_t_guard(
        phi,
        abs_diff,
        fs=fs,
        refractory_ms=refractory_ms,
        t_wave_slope_ratio=t_wave_slope_ratio,
        candidate_min_height=float(np.deg2rad(15.0)),
        max_half_width_samples=max_width_samples,
        diagnostics_out=diagnostics_out,
        signal=sig,
    )
    return _refine_r_peaks_polarity_locked(sig, candidates, fs)


def detect_r_peaks(
    filtered_signal: np.ndarray,
    fs: float,
    refractory_ms: float = 200.0,
    *,
    backend: str = "adaptive_derivative",
    t_wave_slope_ratio: float = 0.50,
    diagnostics_out: dict[str, int] | None = None,
) -> np.ndarray:
    """Adaptive derivative-energy or slope-conditioned Phasor R-peak detection."""
    sig = np.asarray(filtered_signal, dtype=np.float64)
    if len(sig) < 4 or fs <= 0:
        return np.array([], dtype=int)
    if not np.all(np.isfinite(sig)):
        sig = np.nan_to_num(sig, nan=0.0, posinf=0.0, neginf=0.0)

    if backend == "phasor_slope_adaptive":
        return detect_r_peaks_phasor_adaptive(
            sig,
            fs=fs,
            refractory_ms=refractory_ms,
            t_wave_slope_ratio=t_wave_slope_ratio,
            diagnostics_out=diagnostics_out,
        )

    diff = np.diff(sig, prepend=sig[0])
    abs_diff = np.abs(diff)
    squared = diff ** 2
    window_len = max(3, int(round(0.120 * fs)))
    integrated = np.convolve(squared, np.ones(window_len) / window_len, mode="same")

    candidates = _apply_adaptive_threshold_and_t_guard(
        integrated,
        abs_diff,
        fs=fs,
        refractory_ms=refractory_ms,
        t_wave_slope_ratio=t_wave_slope_ratio,
        diagnostics_out=diagnostics_out,
        signal=sig,
    )
    return _refine_r_peaks_polarity_locked(sig, candidates, fs)
