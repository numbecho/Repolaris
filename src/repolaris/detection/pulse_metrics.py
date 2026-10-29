import numpy as np

def compute_qtc(qt_sec: float, rr_sec: float) -> dict[str, float]:
    """Calculates heart-rate corrected QT intervals using Bazett, Fridericia, and Framingham formulas."""
    if rr_sec <= 0:
        return {"bazett_ms": np.nan, "fridericia_ms": np.nan, "framingham_ms": np.nan}
        
    qt_ms = qt_sec * 1000.0
    bazett_ms = qt_ms / np.sqrt(rr_sec)
    fridericia_ms = qt_ms / (rr_sec ** (1.0 / 3.0))
    framingham_ms = qt_ms + 154.0 * (1.0 - rr_sec)
    
    return {
        "bazett_ms": float(bazett_ms),
        "fridericia_ms": float(fridericia_ms),
        "framingham_ms": float(framingham_ms)
    }

def summarize_beats(beats: list[dict]) -> dict:
    """Computes summary statistics across detected beats."""
    if not beats:
        return {
            "mean_hr_bpm": 0.0,
            "mean_qt_ms": 0.0,
            "mean_qtc_bazett_ms": 0.0,
            "mean_qtc_fridericia_ms": 0.0,
            "total_beats": 0
        }
        
    hrs = [b["hr_bpm"] for b in beats if not np.isnan(b["hr_bpm"])]
    qts = [b["qt_ms"] for b in beats if not np.isnan(b["qt_ms"])]
    qtc_b = [b["qtc"]["bazett_ms"] for b in beats if not np.isnan(b["qtc"]["bazett_ms"])]
    qtc_f = [b["qtc"]["fridericia_ms"] for b in beats if not np.isnan(b["qtc"]["fridericia_ms"])]
    
    return {
        "mean_hr_bpm": float(np.mean(hrs)) if hrs else 0.0,
        "mean_qt_ms": float(np.mean(qts)) if qts else 0.0,
        "mean_qtc_bazett_ms": float(np.mean(qtc_b)) if qtc_b else 0.0,
        "mean_qtc_fridericia_ms": float(np.mean(qtc_f)) if qtc_f else 0.0,
        "total_beats": len(beats)
    }
