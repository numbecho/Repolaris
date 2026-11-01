import numpy as np
from scipy.signal import find_peaks

def detect_r_peaks(filtered_signal: np.ndarray, fs: float, refractory_ms: float = 250.0) -> np.ndarray:
    """Derivative and energy-integration R-peak detection inspired by Pan-Tompkins."""
    # 1. First-order derivative
    diff = np.diff(filtered_signal, prepend=filtered_signal[0])
    
    # 2. Squaring function to accentuate steep slopes
    squared = diff ** 2
    
    # 3. Moving-window integrator
    window_len = int(0.120 * fs)
    if window_len < 3:
        window_len = 3
    kernel = np.ones(window_len) / window_len
    integrated = np.convolve(squared, kernel, mode='same')
    
    # 4. Adaptive peak finding
    min_distance = int((refractory_ms / 1000.0) * fs)
    threshold = 0.30 * np.percentile(integrated, 90)
    
    candidate_peaks, _ = find_peaks(integrated, distance=min_distance, height=threshold)
    
    # 5. Fine-tune on original filtered signal to pinpoint true local maximum
    search_radius = int(0.060 * fs)
    r_peaks = []
    n_samples = len(filtered_signal)
    
    for cp in candidate_peaks:
        start = max(0, cp - search_radius)
        end = min(n_samples, cp + search_radius + 1)
        local_max_idx = start + np.argmax(filtered_signal[start:end])
        r_peaks.append(local_max_idx)
        
    return np.unique(np.array(r_peaks, dtype=int))
