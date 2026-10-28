from dataclasses import dataclass, field

@dataclass
class FilterConfig:
    lowcut: float = 0.5
    highcut: float = 45.0
    filter_order: int = 3
    notch_freq: float = 50.0
    notch_quality: float = 30.0

@dataclass
class DetectionConfig:
    refractory_period_ms: float = 250.0
    qrs_integration_window_ms: float = 120.0
    q_search_window_ms: float = 100.0
    t_search_window_ms: float = 450.0
    t_end_threshold_ratio: float = 0.15

@dataclass
class ECGConfig:
    sampling_rate: float = 500.0
    filter_cfg: FilterConfig = field(default_factory=FilterConfig)
    detection_cfg: DetectionConfig = field(default_factory=DetectionConfig)
