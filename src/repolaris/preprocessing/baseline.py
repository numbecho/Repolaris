import numpy as np
from scipy.ndimage import median_filter

def remove_baseline_wander(data: np.ndarray, fs: float) -> np.ndarray:
    """Removes baseline drift via two-stage median filtering (QRS suppression + P/T suppression)."""
    # First stage: 200ms median filter suppresses QRS
    w1 = int(0.200 * fs)
    if w1 % 2 == 0:
        w1 += 1
    # Second stage: 600ms median filter suppresses P and T waves
    w2 = int(0.600 * fs)
    if w2 % 2 == 0:
        w2 += 1
    
    baseline = median_filter(data, size=w1, mode='reflect')
    baseline = median_filter(baseline, size=w2, mode='reflect')
    return data - baseline
