import numpy as np

def generate_synthetic_ecg(duration_sec: float = 10.0, fs: float = 500.0, heart_rate_bpm: float = 72.0, noise_std: float = 0.02):
    """Generates a realistic synthetic ECG lead using asymmetric Gaussian wave components."""
    total_samples = int(duration_sec * fs)
    t = np.linspace(0, duration_sec, total_samples, endpoint=False)
    signal = np.zeros(total_samples)

    rr_interval_sec = 60.0 / heart_rate_bpm
    beat_times = np.arange(0.5 * rr_interval_sec, duration_sec - 0.2, rr_interval_sec)
    r_peak_indices = (beat_times * fs).astype(int)

    # Gaussian wave parameters: (amplitude, time_offset_sec, width_sec)
    waves = [
        (0.15, -0.16, 0.035),   # P-wave
        (-0.15, -0.04, 0.015),  # Q-wave
        (1.20, 0.00, 0.025),    # R-peak
        (-0.25, 0.04, 0.020),   # S-wave
        (0.30, 0.22, 0.070),    # T-wave
    ]

    for bt in beat_times:
        for amp, offset, width in waves:
            mu = bt + offset
            signal += amp * np.exp(-0.5 * ((t - mu) / width) ** 2)

    if noise_std > 0:
        rng = np.random.default_rng(42)
        signal += rng.normal(0, noise_std, total_samples)

    return t, signal, r_peak_indices
