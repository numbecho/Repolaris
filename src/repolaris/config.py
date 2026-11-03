from dataclasses import dataclass, field


@dataclass
class FilterConfig:
    """Zero-phase conditioning parameters following AHA/ACC/HRS (Kligfield et al., 2007).

    Pairs a 0.05 Hz low-cutoff zero-phase Butterworth passband (preserving ST-segment and
    T-wave low-frequency energy) with a narrow Q=30 powerline notch filter and the cascaded
    two-stage median filter (200 ms / 600 ms; de Chazal et al., 2004) in baseline.py.
    """

    lowcut: float = 0.05
    highcut: float = 45.0
    filter_order: int = 3
    notch_freq: float = 50.0
    notch_quality: float = 30.0


@dataclass
class DetectionConfig:
    """Fiducial delineation and QT-RR restitution modeling configuration."""

    refractory_period_ms: float = 250.0
    qrs_integration_window_ms: float = 120.0
    q_search_window_ms: float = 100.0
    t_search_window_ms: float = 450.0
    t_end_threshold_ratio: float = 0.15
    t_end_method: str = "hybrid"  # 'hybrid', 'tangent', 'zhang_area', 'threshold'
    qtrr_model: str = "linear"  # Any of the 10 Pueyo (2004) models or 'auto_best'
    enable_hysteresis: bool = True
    hysteresis_kernel: str = "exponential"  # 'exponential' (EW) or 'linear' (LW)


@dataclass
class ECGConfig:
    sampling_rate: float = 500.0
    filter_cfg: FilterConfig = field(default_factory=FilterConfig)
    detection_cfg: DetectionConfig = field(default_factory=DetectionConfig)
