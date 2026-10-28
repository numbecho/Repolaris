"""QT-RR Restitution and Repolarization Dynamics Regression module.

Provides multi-model regression fitting for the physiological relationship
between ventricular repolarization (QT interval) and heart rate cycle length
(RR interval), supporting Linear, Hyperbolic, Parabolic-Log, Logarithmic,
Exponential, and Arcus-Tangent formulations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from scipy.stats import pearsonr


SUPPORTED_QTRR_MODELS: List[str] = [
    "linear",
    "hyperbolic",
    "parabolic_log",
    "logarithmic",
    "exponential",
    "arctan",
]


def fit_qtrr_model(
    rr_intervals: np.ndarray,
    qt_intervals: np.ndarray,
    model: str = "linear",
) -> Dict[str, Any]:
    """Fits an empirical QT-RR restitution model to paired beat observations.

    Args:
        rr_intervals: 1D array of RR interval measurements (in seconds or ms).
        qt_intervals: 1D array of QT interval measurements (in matching units).
        model: Regression model specification ('linear', 'hyperbolic',
            'parabolic_log', 'logarithmic', 'exponential', 'arctan').

    Returns:
        A dictionary containing:
            - 'model': Selected model name.
            - 'slope': Estimated slope parameter (a).
            - 'intercept': Estimated intercept parameter (b).
            - 'pearson_r': Linear correlation coefficient between transformed variables.
            - 'p_value': Two-sided p-value for hypothesis test of zero correlation.
            - 'predict_fn': Callable mapping arbitrary RR inputs to predicted QT values.

    Raises:
        ValueError: If input arrays are mismatched, empty, or an unsupported model is requested.
    """
    model_lower = model.lower()
    if model_lower not in SUPPORTED_QTRR_MODELS:
        raise ValueError(
            f"Unsupported QT-RR model '{model}'. Choose from: {SUPPORTED_QTRR_MODELS}"
        )

    rr = np.asarray(rr_intervals, dtype=np.float64)
    qt = np.asarray(qt_intervals, dtype=np.float64)

    if len(rr) != len(qt):
        min_len = min(len(rr), len(qt))
        rr = rr[:min_len]
        qt = qt[:min_len]

    if len(rr) < 3:
        raise ValueError("At least 3 valid QT-RR pairs are required for model fitting.")

    # Remove non-positive entries for logarithmic/inverse models
    if model_lower in ["hyperbolic", "parabolic_log", "logarithmic"]:
        valid = (rr > 0) & (qt > 0)
        rr = rr[valid]
        qt = qt[valid]
        if len(rr) < 3:
            raise ValueError("Insufficient positive data points for selected model.")

    if model_lower == "linear":
        x = rr
        y = qt
        poly = np.polyfit(x, y, 1)
        slope, intercept = float(poly[0]), float(poly[1])
        predict_fn = lambda r_in: slope * np.asarray(r_in) + intercept

    elif model_lower == "hyperbolic":
        x = 1.0 / rr
        y = qt
        poly = np.polyfit(x, y, 1)
        slope, intercept = float(poly[0]), float(poly[1])
        predict_fn = lambda r_in: slope / np.asarray(r_in) + intercept

    elif model_lower == "parabolic_log":
        x = np.log(rr)
        y = np.log(qt)
        poly = np.polyfit(x, y, 1)
        slope, intercept_log = float(poly[0]), float(poly[1])
        intercept = float(np.exp(intercept_log))
        predict_fn = lambda r_in: intercept * (np.asarray(r_in) ** slope)

    elif model_lower == "logarithmic":
        x = np.log(rr)
        y = qt
        poly = np.polyfit(x, y, 1)
        slope, intercept = float(poly[0]), float(poly[1])
        predict_fn = lambda r_in: slope * np.log(np.asarray(r_in)) + intercept

    elif model_lower == "exponential":
        x = np.exp(-rr)
        y = qt
        poly = np.polyfit(x, y, 1)
        slope, intercept = float(poly[0]), float(poly[1])
        predict_fn = lambda r_in: slope * np.exp(-np.asarray(r_in)) + intercept

    elif model_lower == "arctan":
        x = np.arctan(rr)
        y = qt
        poly = np.polyfit(x, y, 1)
        slope, intercept = float(poly[0]), float(poly[1])
        predict_fn = lambda r_in: slope * np.arctan(np.asarray(r_in)) + intercept

    r_val, p_val = pearsonr(x, y)

    return {
        "model": model_lower,
        "slope": slope,
        "intercept": intercept,
        "pearson_r": float(r_val),
        "p_value": float(p_val),
        "predict_fn": predict_fn,
    }
