"""
Clinical ECG Event Detection Engine
Scans cardiac beat series to identify and classify salient clinical events:
- Repolarization: Severe QTc Prolongation (>500 ms), Borderline Prolongation (>480 ms), Short QT (<340 ms)
- Conduction / Rhythm: Sinus Pauses (RR > 2.0s / 2.5s)
- Rate Extremes: Severe Bradycardia (<45 BPM), Severe Tachycardia (>120 BPM), Study Min/Max HR
- Ectopics: Premature Ventricular Contractions (PVCs)
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import numpy as np


@dataclass
class ECGEvent:
    timestamp_sec: float
    event_type: str                     # 'CRITICAL_QTC', 'BORDERLINE_QTC', 'SHORT_QT', 'PAUSE', 'MAX_HR', 'MIN_HR', 'TACHYCARDIA', 'BRADYCARDIA', 'PVC'
    severity: str                       # 'CRITICAL', 'WARNING', 'INFO'
    metric_value: float                 # e.g., 532.0 ms, 2.6 s, 142.0 BPM
    unit: str                           # 'ms', 's', 'BPM'
    beat_index: int
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def detect_clinical_events(
    beats: List[Dict[str, Any]],
    fs: float = 500.0,
    qtc_critical_thresh_ms: float = 500.0,
    qtc_warning_thresh_ms: float = 480.0,
    short_qt_thresh_ms: float = 340.0,
    pause_thresh_sec: float = 2.0,
    tachy_thresh_bpm: float = 120.0,
    brady_thresh_bpm: float = 45.0
) -> List[ECGEvent]:
    """
    Scans a list of analyzed beats and flags all clinically salient episodes.
    """
    if not beats:
        return []

    events: List[ECGEvent] = []

    hrs = []
    valid_hr_beats = []

    for i, beat in enumerate(beats):
        t_sec = beat["time_sec"]
        rr_sec = beat.get("rr_sec", 0.0)
        hr = beat.get("hr_bpm", np.nan)
        qt_ms = beat.get("qt_ms", 0.0)
        qtc_b = beat.get("qtc", {}).get("bazett_ms", np.nan)

        if not np.isnan(hr) and hr > 0:
            hrs.append(hr)
            valid_hr_beats.append(i)

        # 1. Sinus Pauses / Asystole (RR > threshold)
        if rr_sec >= pause_thresh_sec:
            sev = "CRITICAL" if rr_sec >= 2.5 else "WARNING"
            events.append(ECGEvent(
                timestamp_sec=float(t_sec),
                event_type="PAUSE",
                severity=sev,
                metric_value=float(rr_sec),
                unit="s",
                beat_index=i,
                description=f"Sinus pause of {rr_sec:.2f} s"
            ))

        # 2. Severe QTc Prolongation (Torsades de Pointes risk)
        if not np.isnan(qtc_b):
            if qtc_b >= qtc_critical_thresh_ms:
                events.append(ECGEvent(
                    timestamp_sec=float(t_sec),
                    event_type="CRITICAL_QTC",
                    severity="CRITICAL",
                    metric_value=float(qtc_b),
                    unit="ms",
                    beat_index=i,
                    description=f"Severe QTc prolongation: {qtc_b:.1f} ms"
                ))
            elif qtc_b >= qtc_warning_thresh_ms:
                events.append(ECGEvent(
                    timestamp_sec=float(t_sec),
                    event_type="BORDERLINE_QTC",
                    severity="WARNING",
                    metric_value=float(qtc_b),
                    unit="ms",
                    beat_index=i,
                    description=f"Prolonged QTc: {qtc_b:.1f} ms"
                ))
            elif qtc_b <= short_qt_thresh_ms:
                events.append(ECGEvent(
                    timestamp_sec=float(t_sec),
                    event_type="SHORT_QT",
                    severity="WARNING",
                    metric_value=float(qtc_b),
                    unit="ms",
                    beat_index=i,
                    description=f"Abnormally short QTc: {qtc_b:.1f} ms"
                ))

        # 3. Tachycardia & Bradycardia runs
        if not np.isnan(hr):
            if hr >= tachy_thresh_bpm:
                events.append(ECGEvent(
                    timestamp_sec=float(t_sec),
                    event_type="TACHYCARDIA",
                    severity="WARNING",
                    metric_value=float(hr),
                    unit="BPM",
                    beat_index=i,
                    description=f"Tachycardia episode: {hr:.1f} BPM"
                ))
            elif hr <= brady_thresh_bpm:
                events.append(ECGEvent(
                    timestamp_sec=float(t_sec),
                    event_type="BRADYCARDIA",
                    severity="WARNING",
                    metric_value=float(hr),
                    unit="BPM",
                    beat_index=i,
                    description=f"Bradycardia episode: {hr:.1f} BPM"
                ))

        # 4. Premature Ventricular Contractions (PVCs)
        # Marked by premature timing (RR < 0.8 * previous RR)
        if i >= 2:
            prev_rr = beats[i-1].get("rr_sec", 1.0)
            if rr_sec < 0.75 * prev_rr and hr > 80:
                events.append(ECGEvent(
                    timestamp_sec=float(t_sec),
                    event_type="PVC",
                    severity="INFO",
                    metric_value=float(rr_sec),
                    unit="s",
                    beat_index=i,
                    description="Premature ventricular ectopic beat"
                ))

    # 5. Flag Study Extremes (Max HR and Min HR of the entire recording)
    if hrs:
        max_idx = int(np.argmax(hrs))
        min_idx = int(np.argmin(hrs))
        max_beat = valid_hr_beats[max_idx]
        min_beat = valid_hr_beats[min_idx]

        events.append(ECGEvent(
            timestamp_sec=float(beats[max_beat]["time_sec"]),
            event_type="MAX_HR",
            severity="INFO",
            metric_value=float(hrs[max_idx]),
            unit="BPM",
            beat_index=max_beat,
            description=f"Maximum Heart Rate: {hrs[max_idx]:.1f} BPM"
        ))

        events.append(ECGEvent(
            timestamp_sec=float(beats[min_beat]["time_sec"]),
            event_type="MIN_HR",
            severity="INFO",
            metric_value=float(hrs[min_idx]),
            unit="BPM",
            beat_index=min_beat,
            description=f"Minimum Heart Rate: {hrs[min_idx]:.1f} BPM"
        ))

    # Sort chronologically by timestamp
    events.sort(key=lambda ev: ev.timestamp_sec)
    return events
