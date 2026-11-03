"""QT-RR Restitution and Repolarization Dynamics Regression module.

Implements all 10 empirical biparametric QT-RR regression models investigated by
Pueyo, Smetana, Caminal, Bayés de Luna, Malik & Laguna (IEEE Trans. Biomed. Eng.
51(9):1511-1520, 2004) and Suárez-León et al. (RIELAC 39(2):54-69, 2018), wrapped
in strict domain and Jacobian conditioning guards to prevent numerical instability:

1.  'linear':              QT = a * RR + b
2.  'hyperbolic':          QT = a / RR + b
3.  'parabolic_log':       QT = b * (RR ** a)               (alias: 'parabolic')
4.  'logarithmic':         QT = a * ln(RR) + b
5.  'shifted_log':         QT = ln(a * RR + b)              (domain-guarded: a*RR + b > 0)
6.  'exponential':         QT = a * exp(-RR) + b
7.  'inverse_exponential': QT = a * exp(-1 / RR) + b
8.  'arctan':              QT = a * arctan(RR) + b
9.  'tanh':                QT = a * tanh(RR) + b
10. 'arcsinh':             QT = a * arcsinh(RR) + b
11. 'arccosh':             QT = a * arccosh(RR + 1) + b     (domain-guarded: RR >= 0)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union
import warnings
import numpy as np
from scipy.stats import pearsonr


SUPPORTED_QTRR_MODELS: List[str] = [
    "linear",
    "hyperbolic",
    "parabolic_log",
    "logarithmic",
    "shifted_log",
    "exponential",
    "arctan",
    "tanh",
    "arcsinh",
    "arccosh",
]

QTRR_MODEL_METADATA: Dict[str, Dict[str, str]] = {
    "linear": {
        "label": "Linear (QT = α·RR + β)",
        "equation": "QT = α·RR + β",
        "latex": r"\mathrm{QT} = \alpha\,\mathrm{RR} + \beta",
    },
    "hyperbolic": {
        "label": "Hyperbolic (QT = α/RR + β)",
        "equation": "QT = α/RR + β",
        "latex": r"\mathrm{QT} = \alpha/\mathrm{RR} + \beta",
    },
    "parabolic_log": {
        "label": "Parabolic Power-Law (QT = β·RR^α)",
        "equation": "QT = β·RR^α",
        "latex": r"\mathrm{QT} = \beta\,\mathrm{RR}^{\alpha}",
    },
    "logarithmic": {
        "label": "Logarithmic (QT = α·ln(RR) + β)",
        "equation": "QT = α·ln(RR) + β",
        "latex": r"\mathrm{QT} = \alpha\ln(\mathrm{RR}) + \beta",
    },
    "shifted_log": {
        "label": "Shifted Logarithmic (QT = ln(α·RR + β))",
        "equation": "QT = ln(α·RR + β)",
        "latex": r"\mathrm{QT} = \ln(\alpha\,\mathrm{RR} + \beta)",
    },
    "exponential": {
        "label": "Exponential (QT = α·exp(-RR) + β)",
        "equation": "QT = α·exp(-RR) + β",
        "latex": r"\mathrm{QT} = \alpha\,e^{-\mathrm{RR}} + \beta",
    },
    "inverse_exponential": {
        "label": "Inverse Exponential (QT = α·exp(-1/RR) + β)",
        "equation": "QT = α·exp(-1/RR) + β",
        "latex": r"\mathrm{QT} = \alpha\,e^{-1/\mathrm{RR}} + \beta",
    },
    "arctan": {
        "label": "Arctangent (QT = α·arctan(RR) + β)",
        "equation": "QT = α·arctan(RR) + β",
        "latex": r"\mathrm{QT} = \alpha\arctan(\mathrm{RR}) + \beta",
    },
    "tanh": {
        "label": "Hyperbolic Tangent (QT = α·tanh(RR) + β)",
        "equation": "QT = α·tanh(RR) + β",
        "latex": r"\mathrm{QT} = \alpha\tanh(\mathrm{RR}) + \beta",
    },
    "arcsinh": {
        "label": "Arc-Hyperbolic Sine (QT = α·arcsinh(RR) + β)",
        "equation": "QT = α·arcsinh(RR) + β",
        "latex": r"\mathrm{QT} = \alpha\operatorname{arcsinh}(\mathrm{RR}) + \beta",
    },
    "arccosh": {
        "label": "Arc-Hyperbolic Cosine (QT = α·arccosh(RR+1) + β)",
        "equation": "QT = α·arccosh(RR+1) + β",
        "latex": r"\mathrm{QT} = \alpha\operatorname{arccosh}(\mathrm{RR}+1) + \beta",
    },
}


def _safe_linear_fit(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, bool]:
    """Performs a 1st-degree least-squares fit with Vandermonde conditioning checks."""
    if len(x) < 2 or float(np.std(x)) <= 1e-9:
        return 0.0, float(np.mean(y)) if len(y) > 0 else 0.0, False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        poly = np.polyfit(x, y, 1)
    slope, intercept = float(poly[0]), float(poly[1])
    ok = bool(np.isfinite(slope) and np.isfinite(intercept))
    return slope, intercept, ok


def fit_qtrr_model(
    rr_intervals: np.ndarray,
    qt_intervals: np.ndarray,
    model: str = "linear",
) -> Dict[str, Any]:
    """Fits an empirical QT-RR restitution model to paired beat observations with domain guards."""
    model_lower = model.lower().strip()
    if model_lower == "parabolic":
        model_lower = "parabolic_log"

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

    valid_finite = np.isfinite(rr) & np.isfinite(qt)
    rr = rr[valid_finite]
    qt = qt[valid_finite]

    if len(rr) < 3:
        raise ValueError("At least 3 valid QT-RR pairs are required for model fitting.")

    if model_lower in (
        "hyperbolic",
        "parabolic_log",
        "logarithmic",
        "shifted_log",
        "inverse_exponential",
        "arccosh",
    ):
        valid = (rr > 1e-6) & (qt > 1e-6)
        rr = rr[valid]
        qt = qt[valid]
        if len(rr) < 3:
            raise ValueError("Insufficient positive data points for selected model.")

    well_conditioned = True

    if model_lower == "linear":
        x = rr
        y = qt
        slope, intercept, ok = _safe_linear_fit(x, y)
        well_conditioned = well_conditioned and ok

        def predict_fn(r_in):
            return slope * np.asarray(r_in, dtype=np.float64) + intercept

    elif model_lower == "hyperbolic":
        x = 1.0 / rr
        y = qt
        slope, intercept, ok = _safe_linear_fit(x, y)
        well_conditioned = well_conditioned and ok

        def predict_fn(r_in):
            r_arr = np.maximum(np.asarray(r_in, dtype=np.float64), 1e-6)
            return slope / r_arr + intercept

    elif model_lower == "parabolic_log":
        x = np.log(rr)
        y = np.log(qt)
        slope, intercept_log, ok = _safe_linear_fit(x, y)
        well_conditioned = well_conditioned and ok
        intercept = float(np.exp(np.clip(intercept_log, -50.0, 50.0)))

        def predict_fn(r_in):
            r_arr = np.maximum(np.asarray(r_in, dtype=np.float64), 1e-6)
            return intercept * (r_arr ** slope)

    elif model_lower == "logarithmic":
        x = np.log(rr)
        y = qt
        slope, intercept, ok = _safe_linear_fit(x, y)
        well_conditioned = well_conditioned and ok

        def predict_fn(r_in):
            r_arr = np.maximum(np.asarray(r_in, dtype=np.float64), 1e-6)
            return slope * np.log(r_arr) + intercept

    elif model_lower == "shifted_log":
        x = rr
        y = np.exp(np.clip(qt, -20.0, 20.0))
        slope, intercept, ok = _safe_linear_fit(x, y)
        well_conditioned = well_conditioned and ok
        inside = slope * rr + intercept
        if np.any(inside <= 1e-9):
            well_conditioned = False

        def predict_fn(r_in):
            arg = np.maximum(slope * np.asarray(r_in, dtype=np.float64) + intercept, 1e-9)
            return np.log(arg)

    elif model_lower == "exponential":
        x = np.exp(-rr)
        y = qt
        slope, intercept, ok = _safe_linear_fit(x, y)
        well_conditioned = well_conditioned and ok

        def predict_fn(r_in):
            return slope * np.exp(-np.asarray(r_in, dtype=np.float64)) + intercept

    elif model_lower == "inverse_exponential":
        x = np.exp(-1.0 / rr)
        y = qt
        slope, intercept, ok = _safe_linear_fit(x, y)
        well_conditioned = well_conditioned and ok

        def predict_fn(r_in):
            r_arr = np.maximum(np.asarray(r_in, dtype=np.float64), 1e-6)
            return slope * np.exp(-1.0 / r_arr) + intercept

    elif model_lower == "arctan":
        x = np.arctan(rr)
        y = qt
        slope, intercept, ok = _safe_linear_fit(x, y)
        well_conditioned = well_conditioned and ok

        def predict_fn(r_in):
            return slope * np.arctan(np.asarray(r_in, dtype=np.float64)) + intercept

    elif model_lower == "tanh":
        x = np.tanh(rr)
        y = qt
        slope, intercept, ok = _safe_linear_fit(x, y)
        well_conditioned = well_conditioned and ok

        def predict_fn(r_in):
            return slope * np.tanh(np.asarray(r_in, dtype=np.float64)) + intercept

    elif model_lower == "arcsinh":
        x = np.arcsinh(rr)
        y = qt
        slope, intercept, ok = _safe_linear_fit(x, y)
        well_conditioned = well_conditioned and ok

        def predict_fn(r_in):
            return slope * np.arcsinh(np.asarray(r_in, dtype=np.float64)) + intercept

    elif model_lower == "arccosh":
        x = np.arccosh(np.maximum(rr + 1.0, 1.0))
        y = qt
        slope, intercept, ok = _safe_linear_fit(x, y)
        well_conditioned = well_conditioned and ok

        def predict_fn(r_in):
            arg = np.maximum(np.asarray(r_in, dtype=np.float64) + 1.0, 1.0)
            return slope * np.arccosh(arg) + intercept

    if np.std(x) <= 1e-9 or np.std(y) <= 1e-9:
        r_val, p_val = 0.0, 1.0
        well_conditioned = False
    else:
        r_raw, p_raw = pearsonr(x, y)
        r_val = float(r_raw) if np.isfinite(r_raw) else 0.0
        p_val = float(p_raw) if np.isfinite(p_raw) else 1.0

    qt_pred = np.asarray(predict_fn(rr), dtype=np.float64)
    residuals = qt - qt_pred
    sse = float(np.sum(residuals ** 2))
    sst = float(np.sum((qt - np.mean(qt)) ** 2))
    r_squared = float(np.clip(1.0 - sse / sst, 0.0, 1.0)) if sst > 1e-12 else float(r_val ** 2)

    scale_to_ms = 1000.0 if float(np.median(qt)) < 5.0 else 1.0
    rmse_ms = float(np.sqrt(np.mean(residuals ** 2)) * scale_to_ms)

    n_obs = len(qt)
    mse = max(sse / float(n_obs), 1e-18)
    aic = float(n_obs * np.log(mse) + 2.0 * 2.0)

    ref_rr = 1.0 if float(np.median(rr)) < 10.0 else 1000.0
    qt_at_ref = float(np.asarray(predict_fn([ref_rr]))[0]) * scale_to_ms

    if not np.isfinite(rmse_ms) or not np.isfinite(qt_at_ref) or qt_at_ref <= 50.0 or qt_at_ref >= 1200.0:
        well_conditioned = False

    meta = QTRR_MODEL_METADATA.get(
        model_lower,
        {"label": model_lower, "equation": model_lower, "latex": model_lower},
    )

    return {
        "model": model_lower,
        "label": meta["label"],
        "equation": meta["equation"],
        "latex": meta["latex"],
        "slope": slope,
        "intercept": intercept,
        "pearson_r": float(r_val),
        "r_squared": r_squared,
        "p_value": float(p_val),
        "rmse_ms": rmse_ms,
        "aic": aic,
        "qtc_individual_ms": qt_at_ref,
        "well_conditioned": well_conditioned,
        "predict_fn": predict_fn,
    }


def fit_all_qtrr_models(
    rr_intervals: np.ndarray,
    qt_intervals: np.ndarray,
    preferred_model: str = "linear",
) -> Dict[str, Any]:
    """Fits all 10 Pueyo et al. (2004) biparametric QT-RR models with domain guards."""
    models_dict: Dict[str, Dict[str, Any]] = {}
    for m_name in SUPPORTED_QTRR_MODELS:
        try:
            res = fit_qtrr_model(rr_intervals, qt_intervals, model=m_name)
            models_dict[m_name] = res
        except ValueError:
            continue

    if not models_dict:
        raise ValueError("Unable to fit any QT-RR restitution model on the provided intervals.")

    ranking = sorted(
        models_dict.values(),
        key=lambda d: (bool(d["well_conditioned"]), float(d["r_squared"]), -float(d["rmse_ms"])),
        reverse=True,
    )
    best_fit = ranking[0]

    pref_clean = preferred_model.lower().strip()
    if pref_clean == "parabolic":
        pref_clean = "parabolic_log"

    if pref_clean == "auto_best" or pref_clean not in models_dict:
        active_fit = best_fit
    else:
        cand = models_dict[pref_clean]
        active_fit = cand if cand["well_conditioned"] else best_fit

    return {
        "active_model": active_fit["model"],
        "active_fit": active_fit,
        "best_model": best_fit["model"],
        "best_fit": best_fit,
        "models": models_dict,
        "ranking": [
            {
                "model": item["model"],
                "label": item["label"],
                "equation": item["equation"],
                "slope": item["slope"],
                "intercept": item["intercept"],
                "pearson_r": item["pearson_r"],
                "r_squared": item["r_squared"],
                "rmse_ms": item["rmse_ms"],
                "aic": item["aic"],
                "qtc_individual_ms": item["qtc_individual_ms"],
                "well_conditioned": item["well_conditioned"],
            }
            for item in ranking
        ],
    }
