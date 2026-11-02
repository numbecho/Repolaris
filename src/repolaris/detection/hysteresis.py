"""Multi-Beat QT-RR Hysteresis and Lag-Weighted Memory Modeling module.

Models the physiological adaptation lag of ventricular repolarization behind heart rate
transitions (1 to 3 minutes / 60 to 180 cardiac cycles) using state-space Exponential
Weighting (EW) and Linear Weighting (LW) kernels, optimizing patient-specific decay
constants (lambda*) and 90% adaptation latency (t_90) to collapse open QT-RR hysteresis loops.

References:
    - Pueyo, E., Smetana, P., Caminal, P., de Luna, A. B., Malik, M., & Laguna, P. (2004).
      Characterization of QT interval adaptation to RR interval changes and its use as a
      risk-stratifier of arrhythmic mortality in amiodarone-treated survivors of acute
      myocardial infarction. IEEE Transactions on Biomedical Engineering, 51(9), 1511-1520.
    - Malik, M., Hnatkova, K., Novotny, T., & Schmidt, G. (2008). Subject-specific profiles
      of QT/RR hysteresis. American Journal of Physiology-Heart and Circulatory Physiology,
      295(6), H2356-H2363.
"""

from __future__ import annotations

from typing import Any
import numpy as np

from repolaris.detection.qtrr import fit_qtrr_model


def compute_effective_rr_exponential(
    rr_intervals_sec: np.ndarray | list[float],
    lambda_param: float = 0.04,
    window_beats: int = 180,
) -> np.ndarray:
    """Calculates memory-weighted effective cycle length (RR_eff) via Exponential Weighting (EW).

    Implements the state-space recursive filter:
        RR_eff[i] = (1 - alpha) * RR_eff[i-1] + alpha * RR[i],  where alpha = 1 - exp(-lambda)
    which matches normalized exponential lag weights w_k = exp(-lambda * k) / sum(exp(-lambda * j)).

    Args:
        rr_intervals_sec: 1D array of RR intervals in seconds.
        lambda_param: Exponential decay constant per beat (lambda > 0).
        window_beats: Historical memory horizon N in beats (default: 180).

    Returns:
        1D array of exponentially weighted effective RR intervals (seconds).
    """
    rr = np.asarray(rr_intervals_sec, dtype=np.float64)
    n = len(rr)
    if n == 0:
        return np.zeros(0, dtype=np.float64)

    lam = max(float(lambda_param), 1e-5)
    alpha = 1.0 - float(np.exp(-lam))
    alpha = float(np.clip(alpha, 1e-5, 1.0))

    rr_eff = np.empty(n, dtype=np.float64)
    rr_eff[0] = rr[0]
    for i in range(1, n):
        rr_eff[i] = (1.0 - alpha) * rr_eff[i - 1] + alpha * rr[i]
    return rr_eff


def compute_effective_rr_linear(
    rr_intervals_sec: np.ndarray | list[float],
    memory_beats: int = 60,
) -> np.ndarray:
    """Calculates memory-weighted effective cycle length (RR_eff) via Linear Weighting (LW).

    Applies normalized linear weights:
        w_k(M) = 2 * (M - k) / (M * (M + 1)),  for k = 0, ..., M - 1.

    Args:
        rr_intervals_sec: 1D array of RR intervals in seconds.
        memory_beats: Number of historical beats M included in linear kernel (default: 60).

    Returns:
        1D array of linearly weighted effective RR intervals (seconds).
    """
    rr = np.asarray(rr_intervals_sec, dtype=np.float64)
    n = len(rr)
    if n == 0:
        return np.zeros(0, dtype=np.float64)

    m_win = max(2, int(memory_beats))
    rr_eff = np.empty(n, dtype=np.float64)

    for i in range(n):
        eff_m = min(i + 1, m_win)
        k_idx = np.arange(eff_m, dtype=np.float64)
        weights = 2.0 * (eff_m - k_idx) / float(eff_m * (eff_m + 1))
        # Reverse slice of most recent eff_m beats: [RR_i, RR_{i-1}, ..., RR_{i-eff_m+1}]
        recent_rr = rr[i - eff_m + 1 : i + 1][::-1]
        rr_eff[i] = float(np.dot(weights, recent_rr))

    return rr_eff


def optimize_hysteresis_parameter(
    qt_intervals_sec: np.ndarray | list[float],
    rr_intervals_sec: np.ndarray | list[float],
    model_type: str = "linear",
    lambda_grid: np.ndarray | None = None,
) -> dict[str, Any]:
    """Optimizes patient-specific memory decay constant (lambda*) minimizing restitution residuals.

    Args:
        qt_intervals_sec: 1D array of QT intervals in seconds (or ms; auto-scaled).
        rr_intervals_sec: 1D array of RR intervals in seconds (or ms; auto-scaled).
        model_type: Restitution regression model ('linear', 'hyperbolic', 'parabolic_log', etc.).
        lambda_grid: Optional 1D search grid of candidate lambda values.

    Returns:
        Dictionary containing:
            - 'optimal_lambda': Optimal exponential decay constant lambda* (1/beat).
            - 't90_beats': 90% adaptation lag in cardiac cycles (-ln(0.1) / lambda*).
            - 't90_sec': 90% adaptation latency in seconds.
            - 'half_life_sec': 50% adaptation half-life t_{1/2} in seconds.
            - 'rr_eff_ew_sec': Exponentially weighted effective RR series (seconds).
            - 'rr_eff_lw_sec': Linearly weighted effective RR series (seconds).
            - 'qtc_hysteresis_ms': Hysteresis-corrected Fridericia QTc series in ms.
            - 'raw_residual_rmse_ms': Uncorrected instantaneous QT-RR restitution RMSE (ms).
            - 'hysteresis_residual_rmse_ms': Memory-compensated QT-RR_eff restitution RMSE (ms).
            - 'loop_reduction_percent': Percentage reduction in restitution loop residual error.
            - 'restitution_fit': Fitted restitution parameters on (RR_eff, QT).
    """
    qt = np.asarray(qt_intervals_sec, dtype=np.float64)
    rr = np.asarray(rr_intervals_sec, dtype=np.float64)

    min_len = min(len(qt), len(rr))
    qt = qt[:min_len]
    rr = rr[:min_len]

    if min_len < 5:
        raise ValueError("At least 5 paired QT-RR observations are required for hysteresis modeling.")

    # Convert to seconds if passed in milliseconds
    qt_sec = qt / 1000.0 if float(np.median(qt)) > 10.0 else qt.copy()
    rr_sec = rr / 1000.0 if float(np.median(rr)) > 10.0 else rr.copy()

    if lambda_grid is None:
        lambda_grid = np.geomspace(0.005, 1.5, 45)

    # Evaluate raw instantaneous residual error
    raw_fit = fit_qtrr_model(rr_sec, qt_sec, model=model_type)
    raw_pred = raw_fit["predict_fn"](rr_sec)
    raw_rmse_ms = float(np.sqrt(np.mean(((qt_sec - raw_pred) * 1000.0) ** 2)))

    best_lambda = 0.05
    best_sse = float("inf")
    best_rr_eff = rr_sec.copy()
    best_fit = raw_fit

    for lam in lambda_grid:
        cand_rr_eff = compute_effective_rr_exponential(rr_sec, lambda_param=float(lam))
        try:
            cand_fit = fit_qtrr_model(cand_rr_eff, qt_sec, model=model_type)
            pred_qt = cand_fit["predict_fn"](cand_rr_eff)
            sse = float(np.sum((qt_sec - pred_qt) ** 2))
            if sse < best_sse:
                best_sse = sse
                best_lambda = float(lam)
                best_rr_eff = cand_rr_eff
                best_fit = cand_fit
        except ValueError:
            continue

    hyst_rmse_ms = float(np.sqrt(best_sse / float(min_len)) * 1000.0)
    mean_rr_sec = float(np.mean(rr_sec))

    t90_beats = float(-np.log(0.1) / best_lambda)
    t90_sec = float(t90_beats * mean_rr_sec)
    half_life_sec = float((np.log(2.0) / best_lambda) * mean_rr_sec)

    # Compute corresponding linear weighting memory window matching t90_beats
    lw_window = max(3, int(round(t90_beats)))
    rr_eff_lw = compute_effective_rr_linear(rr_sec, memory_beats=lw_window)

    # Hysteresis-compensated Fridericia QTc in milliseconds: QT / (RR_eff)^(1/3)
    safe_rr_eff = np.maximum(best_rr_eff, 0.2)
    qtc_hyst_ms = (qt_sec * 1000.0) / (safe_rr_eff ** (1.0 / 3.0))

    loop_reduction = (
        float(max(0.0, (raw_rmse_ms - hyst_rmse_ms) / raw_rmse_ms * 100.0))
        if raw_rmse_ms > 1e-9
        else 0.0
    )

    return {
        "optimal_lambda": best_lambda,
        "t90_beats": t90_beats,
        "t90_sec": t90_sec,
        "half_life_sec": half_life_sec,
        "rr_eff_ew_sec": best_rr_eff,
        "rr_eff_lw_sec": rr_eff_lw,
        "qtc_hysteresis_ms": qtc_hyst_ms,
        "raw_residual_rmse_ms": raw_rmse_ms,
        "hysteresis_residual_rmse_ms": hyst_rmse_ms,
        "loop_reduction_percent": loop_reduction,
        "restitution_fit": {
            "model": best_fit["model"],
            "slope": best_fit["slope"],
            "intercept": best_fit["intercept"],
            "pearson_r": best_fit["pearson_r"],
            "p_value": best_fit["p_value"],
        },
    }
