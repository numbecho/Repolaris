import numpy as np

def detect_q_onset(signal: np.ndarray, r_peak: int, fs: float, search_window_ms: float = 100.0) -> int:
    """Finds the Q-wave trough and Q-onset (inflection point prior to depolarization)."""
    window_samples = int((search_window_ms / 1000.0) * fs)
    start_idx = max(0, r_peak - window_samples)
    
    segment = signal[start_idx:r_peak]
    if len(segment) < 4:
        return max(0, r_peak - 1)
        
    # Q-trough is the minimum voltage immediately before the R-peak
    q_trough_rel = np.argmin(segment)
    
    # Find onset before Q-trough by searching for flat baseline derivative
    pre_q = segment[:q_trough_rel] if q_trough_rel > 2 else segment
    grad = np.abs(np.gradient(pre_q))
    onset_rel = np.argmin(grad) if len(grad) > 0 else 0
    
    return start_idx + onset_rel
