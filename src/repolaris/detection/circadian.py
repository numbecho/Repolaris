"""Circadian Day/Night (Diurnal vs. Nocturnal) Repolarization & Autonomic Stratification module.

Partitions ambulatory Holter beats into Daytime (Awake) and Nighttime (Asleep) epochs to
quantify:
1. Nocturnal Heart Rate Dipping percentage (`hr_dip_pct`) and dipping phenotype
   (`NORMAL_DIPPER` >= 10%, `BLUNTED_NON_DIPPER` 0-10%, `REVERSE_DIPPER` < 0%).
2. Diurnal vs. Nocturnal rate-corrected repolarization intervals (`QTcF`, `J-Tpeakc`,
   `Tpe`, `STV_QT`) and nocturnal-to-diurnal QTcF lengthening (`delta_qtcf_night_minus_day_ms`,
   flagging >= +15.0 ms nocturnal prolongation characteristic of LQT2/LQT3 vs. LQT1).
3. Separate Daytime vs. Nighttime linear QT-RR restitution slopes (`day_qtrr_slope`,
   `night_qtrr_slope`, and the Page/Tsukakoshi et al. 2021 LQT2 >= 0.211 slope discriminator).
4. Diurnal vs. Nocturnal ectopic beat distribution (`day_pvc_count`, `night_pvc_count`).

References:
    - Page A., Aktas M.K., Soyata T., Zareba W., Couderc J.P. (2016). "QT clock to
      improve gender- and gene-specific QT-prolongation monitoring." Heart Rhythm, 13(1), 190-198.
    - Tsukakoshi M., et al. (2021). "Differential diagnosis between LQT1 and LQT2 by QT/RR
      relationships using 24-hour Holter monitoring." Annals of Noninvasive Electrocardiology,
      26(5), e12878.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from repolaris.detection.pulse_metrics import compute_stv_qt


def _parse_start_hour(metadata: dict[str, Any] | None) -> float | None:
    """Extracts the decimal clock start hour [0.0, 24.0) from recording metadata if present."""
    if not metadata:
        return None

    for key in ("start_hour", "recording_start_hour"):
        val = metadata.get(key)
        if isinstance(val, (int, float)) and np.isfinite(val):
            return float(val) % 24.0

    for key in ("start_time", "recording_start_time", "acquisition_datetime", "timestamp"):
        raw = metadata.get(key)
        if not raw:
            continue
        match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", str(raw))
        if match:
            hh = int(match.group(1))
            mm = int(match.group(2))
            ss = int(match.group(3) or 0)
            if 0 <= hh < 24 and 0 <= mm < 60:
                return float(hh) + (mm / 60.0) + (ss / 3600.0)

    return None


def _fit_epoch_qtrr_slope(epoch_beats: list[dict[str, Any]]) -> float:
    """Computes the linear QT (sec) vs. RR (sec) regression slope beta on sinus beats."""
    rr_s: list[float] = []
    qt_s: list[float] = []
    for b in epoch_beats:
        qt_ms = float(b.get("qt_ms", 0.0) or 0.0)
        hr_bpm = float(b.get("hr_bpm", 0.0) or 0.0)
        rr_val = float(b.get("rr_sec", (60.0 / hr_bpm) if hr_bpm > 0 else 0.0) or 0.0)
        if 200.0 <= qt_ms <= 750.0 and 0.30 <= rr_val <= 2.20:
            rr_s.append(rr_val)
            qt_s.append(qt_ms / 1000.0)

    if len(rr_s) < 4:
        return 0.0

    x = np.asarray(rr_s, dtype=np.float64)
    y = np.asarray(qt_s, dtype=np.float64)
    x_var = float(np.var(x))
    if x_var < 1e-7:
        return 0.0
    cov_xy = float(np.mean((x - np.mean(x)) * (y - np.mean(y))))
    return float(cov_xy / (x_var + 1e-6))


def analyze_circadian_repolarization(
    beats: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    total_duration_sec: float = 0.0,
    day_window_hours: tuple[int, int] = (7, 22),
    allow_two_epoch_split: bool = False,
) -> dict[str, Any]:
    """Stratifies Holter repolarization, QT-RR slope, and chronotropic dipping across Day and Night epochs."""
    if not beats:
        return {
            "status": "NO_BEATS",
            "epoch_partition_method": "NONE",
            "day_beat_count": 0,
            "night_beat_count": 0,
            "day_hr_bpm": 0.0,
            "night_hr_bpm": 0.0,
            "hr_dip_pct": 0.0,
            "dipping_category": "INSUFFICIENT_DATA",
            "day_qtcf_ms": 0.0,
            "night_qtcf_ms": 0.0,
            "delta_qtcf_night_minus_day_ms": 0.0,
            "nocturnal_qtc_lengthening_flag": False,
            "day_j_tpeakc_ms": 0.0,
            "night_j_tpeakc_ms": 0.0,
            "day_tpe_ms": 0.0,
            "night_tpe_ms": 0.0,
            "day_stv_qt_ms": 0.0,
            "night_stv_qt_ms": 0.0,
            "day_qtrr_slope": 0.0,
            "night_qtrr_slope": 0.0,
            "steep_day_qtrr_lqt2_pattern": False,
            "day_pvc_count": 0,
            "night_pvc_count": 0,
            "verdict": "INSUFFICIENT_DATA",
        }

    start_hour = _parse_start_hour(metadata)
    day_start, day_end = int(day_window_hours[0]), int(day_window_hours[1])

    times = [float(b.get("time_sec", 0.0) or 0.0) for b in beats]
    span_sec = max(float(total_duration_sec), (max(times) - min(times)) if times else 0.0)

    day_all: list[dict[str, Any]] = []
    night_all: list[dict[str, Any]] = []
    partition_method = "WALL_CLOCK"

    if start_hour is not None:
        for b in beats:
            t_sec = float(b.get("time_sec", 0.0) or 0.0)
            clock_hr = (start_hour + (t_sec / 3600.0)) % 24.0
            if day_start <= clock_hr < day_end:
                day_all.append(b)
            else:
                night_all.append(b)
    elif span_sec >= 7200.0 or allow_two_epoch_split:
        # Multi-hour recording without explicit clock header or forced two-phase evaluation:
        # split into first half (Diurnal/Active) vs. second half (Nocturnal/Rest)
        partition_method = "TEMPORAL_HALVES"
        mid_t = min(times) + 0.5 * (max(times) - min(times))
        for b in beats:
            t_sec = float(b.get("time_sec", 0.0) or 0.0)
            if t_sec <= mid_t:
                day_all.append(b)
            else:
                night_all.append(b)
    else:
        partition_method = "SINGLE_DAY_EPOCH"
        day_all = list(beats)

    def _sinus_only(b_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            b for b in b_list
            if str(b.get("beat_class", "N")).upper() == "N" and not b.get("is_paced", False)
        ]

    day_sinus = _sinus_only(day_all)
    night_sinus = _sinus_only(night_all)

    def _mean_key(b_list: list[dict[str, Any]], key: str) -> float:
        vals = [
            float(b[key]) for b in b_list
            if b.get(key) is not None and np.isfinite(float(b[key])) and float(b[key]) > 0
        ]
        return float(np.mean(vals)) if vals else 0.0

    day_hr = _mean_key(day_sinus, "hr_bpm")
    night_hr = _mean_key(night_sinus, "hr_bpm")

    day_qtcf = _mean_key(day_sinus, "qtc_fridericia_ms")
    night_qtcf = _mean_key(night_sinus, "qtc_fridericia_ms")

    day_jtpc = _mean_key(day_sinus, "j_tpeakc_ms")
    night_jtpc = _mean_key(night_sinus, "j_tpeakc_ms")

    day_tpe = _mean_key(day_sinus, "tpe_ms")
    night_tpe = _mean_key(night_sinus, "tpe_ms")

    day_qts = [float(b["qt_ms"]) for b in day_sinus if b.get("qt_ms") and float(b["qt_ms"]) > 0]
    night_qts = [float(b["qt_ms"]) for b in night_sinus if b.get("qt_ms") and float(b["qt_ms"]) > 0]

    day_stv = float(compute_stv_qt(day_qts)["stv_qt_ms"]) if len(day_qts) >= 2 else 0.0
    night_stv = float(compute_stv_qt(night_qts)["stv_qt_ms"]) if len(night_qts) >= 2 else 0.0

    day_slope = _fit_epoch_qtrr_slope(day_sinus)
    night_slope = _fit_epoch_qtrr_slope(night_sinus)

    day_pvc = sum(1 for b in day_all if str(b.get("beat_class", "N")).upper() == "V")
    night_pvc = sum(1 for b in night_all if str(b.get("beat_class", "N")).upper() == "V")

    both_epochs = len(day_sinus) >= 3 and len(night_sinus) >= 3
    if both_epochs and day_hr > 0:
        hr_dip_pct = (day_hr - night_hr) / day_hr * 100.0
        if hr_dip_pct >= 10.0:
            dip_cat = "NORMAL_DIPPER"
        elif hr_dip_pct >= 0.0:
            dip_cat = "BLUNTED_NON_DIPPER"
        else:
            dip_cat = "REVERSE_DIPPER"
        delta_qtcf = night_qtcf - day_qtcf
    else:
        hr_dip_pct = 0.0
        dip_cat = "SINGLE_EPOCH"
        delta_qtcf = 0.0

    nocturnal_lengthening = bool(both_epochs and delta_qtcf >= 15.0)
    steep_day_lqt2 = bool(day_slope >= 0.211)

    if not both_epochs:
        verdict = "SINGLE_EPOCH_RECORDING"
    elif nocturnal_lengthening:
        verdict = "NOCTURNAL_QTC_PROLONGATION"
    elif steep_day_lqt2:
        verdict = "STEEP_DIURNAL_QTRR_SLOPE"
    elif dip_cat == "REVERSE_DIPPER":
        verdict = "REVERSE_HR_DIPPING"
    else:
        verdict = "NORMAL_CIRCADIAN_DYNAMICS"

    return {
        "status": "DUAL_EPOCH" if both_epochs else "SINGLE_EPOCH",
        "epoch_partition_method": partition_method,
        "day_beat_count": len(day_all),
        "night_beat_count": len(night_all),
        "day_hr_bpm": round(day_hr, 2),
        "night_hr_bpm": round(night_hr, 2),
        "hr_dip_pct": round(hr_dip_pct, 2),
        "dipping_category": dip_cat,
        "day_qtcf_ms": round(day_qtcf, 2),
        "night_qtcf_ms": round(night_qtcf, 2),
        "delta_qtcf_night_minus_day_ms": round(delta_qtcf, 2),
        "nocturnal_qtc_lengthening_flag": nocturnal_lengthening,
        "day_j_tpeakc_ms": round(day_jtpc, 2),
        "night_j_tpeakc_ms": round(night_jtpc, 2),
        "day_tpe_ms": round(day_tpe, 2),
        "night_tpe_ms": round(night_tpe, 2),
        "day_stv_qt_ms": round(day_stv, 3),
        "night_stv_qt_ms": round(night_stv, 3),
        "day_qtrr_slope": round(day_slope, 4),
        "night_qtrr_slope": round(night_slope, 4),
        "steep_day_qtrr_lqt2_pattern": steep_day_lqt2,
        "day_pvc_count": int(day_pvc),
        "night_pvc_count": int(night_pvc),
        "verdict": verdict,
    }
