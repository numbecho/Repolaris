from __future__ import annotations

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
) -> list[int]:
    """Causal SPKI/NPKI adaptive thresholding with search-back and rate-adaptive T-wave guard."""
    n_samples = len(envelope)
    if n_samples < 4 or fs <= 0:
        return []

    init_n = min(n_samples, max(10, int(round(4.0 * fs))))
    init_seg = envelope[:init_n]
    med = float(np.median(init_seg))
    mad = float(np.median(np.abs(init_seg - med)))
    clip_hi = med + 10.0 * max(mad, 1e-9)
    clipped = np.clip(init_seg, 0.0, clip_hi)
    p99 = float(np.percentile(clipped, 99))
    spki = max(0.85 * p99, 1e-9)
    init_spki = spki
    npki = max(med, 1e-12)

    min_cand_dist = max(1, int(round(0.080 * fs)))
    cand_kwargs: dict[str, float | int] = {"distance": min_cand_dist}
    if candidate_min_height > 0.0:
        cand_kwargs["height"] = candidate_min_height
    candidates, _ = find_peaks(envelope, **cand_kwargs)

    hard_ref_samples = max(1, int(round((refractory_ms / 1000.0) * fs)))
    rad40 = max(1, int(round(0.040 * fs)))

    accepted: list[int] = []
    rr_history: list[float] = []
    mean_rr = 0.8 * fs
    prev_r_slope = 0.0
    refractory_rejected = 0
    t_wave_rejected = 0
    init_silence_samples = int(round(4.0 * fs))

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
                npki = 0.125 * val + 0.875 * npki
                continue

        if accepted and (cp - accepted[-1]) < hard_ref_samples:
            refractory_rejected += 1
            continue

        thr1 = npki + 0.32 * (spki - npki)
        thr2 = max(0.5 * thr1, npki + 0.10 * (spki - npki))
        soft_zone_end = int(round(np.clip(0.45 * mean_rr, 0.280 * fs, 0.480 * fs)))
        cand_slope = float(np.max(abs_diff[max(0, cp - rad40) : min(n_samples, cp + rad40 + 1)]))

        if val >= thr1:
            if accepted and (cp - accepted[-1]) <= soft_zone_end and prev_r_slope > 0.0:
                if cand_slope < t_wave_slope_ratio * prev_r_slope:
                    t_wave_rejected += 1
                    npki = 0.125 * val + 0.875 * npki
                    continue

            if accepted:
                rr_history.append(float(cp - accepted[-1]))
                if len(rr_history) > 8:
                    rr_history.pop(0)
                mean_rr = float(np.mean(rr_history))
            # Clamp outlier spikes only after initial real beats establish spki (protects flat/microvolt lead-ins)
            val_capped = min(val, 3.0 * spki) if (len(accepted) >= 3 and spki > max(2.5 * npki, 1e-6)) else val
            accepted.append(cp)
            spki = 0.125 * val_capped + 0.875 * spki
            prev_r_slope = cand_slope if prev_r_slope <= 0.0 else (0.5 * cand_slope + 0.5 * prev_r_slope)
        else:
            npki = 0.125 * val + 0.875 * npki
            if accepted and (cp - accepted[-1]) > 1.66 * mean_rr:
                max_sb_samples = max(hard_ref_samples + 1, int(round(max(2.5 * mean_rr, 3.0 * fs))))
                min_sb_sample = max(accepted[-1] + hard_ref_samples, cp - max_sb_samples)
                sb_best_cp = -1
                sb_best_val = -1.0
                for j in range(idx_i - 1, -1, -1):
                    cand_j = int(candidates[j])
                    if cand_j <= min_sb_sample:
                        break
                    v_j = float(envelope[cand_j])
                    if v_j >= thr2 and v_j > sb_best_val:
                        sb_best_val = v_j
                        sb_best_cp = cand_j
                sb_accepted = False
                if sb_best_cp >= 0:
                    sb_slope = float(
                        np.max(abs_diff[max(0, sb_best_cp - rad40) : min(n_samples, sb_best_cp + rad40 + 1)])
                    )
                    if not (
                        (sb_best_cp - accepted[-1]) <= soft_zone_end
                        and prev_r_slope > 0.0
                        and sb_slope < t_wave_slope_ratio * prev_r_slope
                    ):
                        rr_history.append(float(sb_best_cp - accepted[-1]))
                        if len(rr_history) > 8:
                            rr_history.pop(0)
                        mean_rr = float(np.mean(rr_history))
                        sb_capped = min(sb_best_val, 3.0 * spki) if (len(accepted) >= 3 and spki > max(2.5 * npki, 1e-6)) else sb_best_val
                        accepted.append(sb_best_cp)
                        spki = 0.25 * sb_capped + 0.75 * spki
                        prev_r_slope = sb_slope if prev_r_slope <= 0.0 else (0.5 * sb_slope + 0.5 * prev_r_slope)
                        sb_accepted = True
                if not sb_accepted:
                    # Decay spki with a noise-safe floor to prevent latch-up without collapsing into background noise
                    spki_floor = max(6.0 * npki, 0.05 * init_spki, 1e-6)
                    spki = max(spki_floor, 0.90 * spki + 0.10 * val)
            elif not accepted and cp > init_silence_samples:
                spki_floor = max(6.0 * npki, 0.05 * init_spki, 1e-6)
                spki = max(spki_floor, 0.90 * spki + 0.10 * val)

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
    )
    return _refine_r_peaks_polarity_locked(sig, candidates, fs)
