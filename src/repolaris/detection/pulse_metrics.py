"""Heart-rate corrected QT (QTc) formulations and beat summary statistics.

Implements the four primary clinical and regulatory QTc rate-correction formulas:
- Bazett (1920): QTc = QT / sqrt(RR)
- Fridericia (1932): QTc = QT / cbrt(RR)
- Framingham (Sagie et al., 1992): QTc = QT + 154 * (1 - RR) [in ms]
- Hodges (1983): QTc = QT + 1.75 * (HR - 60) [in ms]
"""

from __future__ import annotations

from typing import Any
import numpy as np


def compute_qtc(qt_sec: float, rr_sec: float) -> dict[str, float]:
    """Calculates heart-rate corrected QT intervals using Bazett, Fridericia, Framingham, and Hodges formulas."""
    if rr_sec <= 0:
        return {
            "bazett_ms": np.nan,
            "fridericia_ms": np.nan,
            "framingham_ms": np.nan,
            "hodges_ms": np.nan,
        }

    qt_ms = qt_sec * 1000.0
    hr_bpm = 60.0 / rr_sec
    bazett_ms = qt_ms / np.sqrt(rr_sec)
    fridericia_ms = qt_ms / (rr_sec ** (1.0 / 3.0))
    framingham_ms = qt_ms + 154.0 * (1.0 - rr_sec)
    hodges_ms = qt_ms + 1.75 * (hr_bpm - 60.0)

    return {
        "bazett_ms": float(bazett_ms),
        "fridericia_ms": float(fridericia_ms),
        "framingham_ms": float(framingham_ms),
        "hodges_ms": float(hodges_ms),
    }


def summarize_beats(beats: list[dict[str, Any]]) -> dict[str, Any]:
    """Computes summary statistics across detected beats."""
    if not beats:
        return {
            "mean_hr_bpm": 0.0,
            "mean_qt_ms": 0.0,
            "mean_qtc_bazett_ms": 0.0,
            "mean_qtc_fridericia_ms": 0.0,
            "mean_qtc_framingham_ms": 0.0,
            "mean_qtc_hodges_ms": 0.0,
            "total_beats": 0,
        }

    hrs = [b["hr_bpm"] for b in beats if not np.isnan(b["hr_bpm"])]
    qts = [b["qt_ms"] for b in beats if not np.isnan(b["qt_ms"])]
    qtc_b = [b["qtc"]["bazett_ms"] for b in beats if not np.isnan(b["qtc"].get("bazett_ms", np.nan))]
    qtc_f = [b["qtc"]["fridericia_ms"] for b in beats if not np.isnan(b["qtc"].get("fridericia_ms", np.nan))]
    qtc_fram = [b["qtc"]["framingham_ms"] for b in beats if not np.isnan(b["qtc"].get("framingham_ms", np.nan))]
    qtc_hodg = [b["qtc"].get("hodges_ms", np.nan) for b in beats if not np.isnan(b["qtc"].get("hodges_ms", np.nan))]

    return {
        "mean_hr_bpm": float(np.mean(hrs)) if hrs else 0.0,
        "mean_qt_ms": float(np.mean(qts)) if qts else 0.0,
        "mean_qtc_bazett_ms": float(np.mean(qtc_b)) if qtc_b else 0.0,
        "mean_qtc_fridericia_ms": float(np.mean(qtc_f)) if qtc_f else 0.0,
        "mean_qtc_framingham_ms": float(np.mean(qtc_fram)) if qtc_fram else 0.0,
        "mean_qtc_hodges_ms": float(np.mean(qtc_hodg)) if qtc_hodg else 0.0,
        "total_beats": len(beats),
    }
