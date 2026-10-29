import numpy as np
from scipy import signal
from repolaris.config import FilterConfig

def bandpass_filter(data: np.ndarray, fs: float, cfg: FilterConfig = FilterConfig()) -> np.ndarray:
    """Zero-phase Butterworth bandpass filter."""
    nyq = 0.5 * fs
    low = max(cfg.lowcut / nyq, 1e-4)
    high = min(cfg.highcut / nyq, 0.999)
    b, a = signal.butter(cfg.filter_order, [low, high], btype='bandpass')
    return signal.filtfilt(b, a, data)

def notch_filter(data: np.ndarray, fs: float, freq: float = 50.0, q: float = 30.0) -> np.ndarray:
    """IIR Notch filter to eliminate 50Hz or 60Hz powerline hum."""
    nyq = 0.5 * fs
    w0 = freq / nyq
    if w0 >= 1.0 or w0 <= 0.0:
        return data
    b, a = signal.iirnotch(w0, q)
    return signal.filtfilt(b, a, data)
