"""ECG Pulse Metrics and Clinical Interval Rate-Correction module.

Formulas:
- Bazett: QTc = QT / sqrt(RR)
- Fridericia: QTc = QT / cbrt(RR)
- Framingham: QTc = QT + 0.154 * (1 - RR)
- Hodges: QTc = QT + 1.75 * (HR - 60)
"""

from __future__ import annotations

import math
from typing import Any, Dict, List
import numpy as np


def compute_qtc(qt_sec: float, rr_sec: float) -> Dict[str, float]:
    """Computes rate-corrected QT intervals across all standard clinical formulas.

    Args:
        qt_sec: QT interval duration in seconds.
        rr_sec: RR interval duration in seconds.

    Returns:
        Dictionary mapping formula names to rate-corrected QTc in milliseconds (ms).
    """
    if rr_sec <= 0 or qt_sec <= 0:
        return {}

    qt_ms = qt_sec * 1000.0
    hr_bpm = 60.0 / rr_sec

    # 1. Bazett (1920): QTc = QT / sqrt(RR)
    qtc_bazett = qt_ms / math.sqrt(rr_sec)

    # 2. Fridericia (1920): QTc = QT / (RR^(1/3))
    qtc_fridericia = qt_ms / (rr_sec ** (1.0 / 3.0))

    # 3. Framingham (Sagie et al., 1992): QTc = QT + 154 * (1 - RR) [in ms]
    qtc_framingham = qt_ms + 154.0 * (1.0 - rr_sec)

    # 4. Hodges (1983): QTc = QT + 1.75 * (HR - 60) [in ms]
    qtc_hodges = qt_ms + 1.75 * (hr_bpm - 60.0)

    return {
        "bazett_ms": round(qtc_bazett, 2),
        "fridericia_ms": round(qtc_fridericia, 2),
        "framingham_ms": round(qtc_framingham, 2),
        "hodges_ms": round(qtc_hodges, 2),
    }


def summarize_beats(beats: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes summary statistics across detected beats, safely handling None and NaN values."""
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

    hrs = [b["hr_bpm"] for b in beats if b.get("hr_bpm") is not None and not np.isnan(b["hr_bpm"])]
    qts = [b["qt_ms"] for b in beats if b.get("qt_ms") is not None and not np.isnan(b["qt_ms"])]
    qtc_b = [
        b["qtc"]["bazett_ms"]
        for b in beats
        if b.get("qtc") and b["qtc"].get("bazett_ms") is not None and not np.isnan(b["qtc"]["bazett_ms"])
    ]
    qtc_f = [
        b["qtc"]["fridericia_ms"]
        for b in beats
        if b.get("qtc") and b["qtc"].get("fridericia_ms") is not None and not np.isnan(b["qtc"]["fridericia_ms"])
    ]
    qtc_fram = [
        b["qtc"]["framingham_ms"]
        for b in beats
        if b.get("qtc") and b["qtc"].get("framingham_ms") is not None and not np.isnan(b["qtc"]["framingham_ms"])
    ]
    qtc_hodg = [
        b["qtc"]["hodges_ms"]
        for b in beats
        if b.get("qtc") and b["qtc"].get("hodges_ms") is not None and not np.isnan(b["qtc"]["hodges_ms"])
    ]

    return {
        "mean_hr_bpm": float(np.mean(hrs)) if hrs else 0.0,
        "mean_qt_ms": float(np.mean(qts)) if qts else 0.0,
        "mean_qtc_bazett_ms": float(np.mean(qtc_b)) if qtc_b else 0.0,
        "mean_qtc_fridericia_ms": float(np.mean(qtc_f)) if qtc_f else 0.0,
        "mean_qtc_framingham_ms": float(np.mean(qtc_fram)) if qtc_fram else 0.0,
        "mean_qtc_hodges_ms": float(np.mean(qtc_hodg)) if qtc_hodg else 0.0,
        "total_beats": len(beats),
    }
