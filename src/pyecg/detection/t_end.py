import numpy as np

def detect_t_end(signal: np.ndarray, r_peak: int, fs: float, search_window_ms: float = 450.0, threshold_ratio: float = 0.15) -> tuple[int, int]:
    """Locates the T-wave peak and T-wave offset using the slope/amplitude threshold method."""
    start_offset = int(0.100 * fs)  # Skip QRS recovery
    max_search = int((search_window_ms / 1000.0) * fs)
    
    start_idx = r_peak + start_offset
    end_idx = min(len(signal), r_peak + max_search)
    
    if start_idx >= end_idx or (end_idx - start_idx) < 10:
        return r_peak + start_offset, r_peak + start_offset + 5
        
    segment = signal[start_idx:end_idx]
    t_peak_rel = np.argmax(segment)
    t_peak_idx = start_idx + t_peak_rel
    
    # Analyze descending slope after T-peak
    descending = segment[t_peak_rel:]
    if len(descending) < 4:
        return t_peak_idx, min(len(signal) - 1, t_peak_idx + int(0.08 * fs))
        
    # Baseline threshold criterion: when signal returns within threshold_ratio of post-T level
    t_amp = segment[t_peak_rel]
    baseline_level = np.median(segment[-int(len(segment)*0.2):]) if len(segment) > 10 else 0.0
    cutoff = baseline_level + threshold_ratio * (t_amp - baseline_level)
    
    below_thresh = np.where(descending <= cutoff)[0]
    if len(below_thresh) > 0:
        t_end_rel = t_peak_rel + below_thresh[0]
    else:
        # Fallback to minimum gradient
        grad = np.abs(np.gradient(descending))
        t_end_rel = t_peak_rel + np.argmin(grad)
        
    t_end_idx = min(len(signal) - 1, start_idx + t_end_rel)
    return t_peak_idx, t_end_idx
