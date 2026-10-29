"""Clinical ECG Annotation Management and Physician Override module.

Provides a unified interface for recording, editing, and exchanging beat-level
and episode-level annotations across automated AI detectors and clinical reviewers:
- Automated beat labels (ANSI/AAMI EC57: N, V, S, F, Q)
- Physician manual corrections & overrides (with audit timestamps & reviewer tags)
- Free-form clinical caliper comments and diagnostic observations
- Import and export to PhysioNet WFDB annotation format (.atr table) and .pecg packages
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


@dataclass
class ECGAnnotation:
    """Represents a single fiducial or diagnostic event annotation."""
    sample: int
    timestamp_sec: float
    label: str                            # AAMI code: 'N', 'V', 'S', 'F', 'Q', or custom tag
    sublabel: str = ""                    # e.g., 'PVC', 'PAC', 'Pause', 'Artifact'
    author: str = "AI_DETECTOR"           # 'AI_DETECTOR' or physician username (e.g., 'Dr. Mercantete')
    is_manual_override: bool = False      # True if reviewed/modified by clinician
    notes: str = ""                       # Clinical rationale or caliper notes
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serializes annotation to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ECGAnnotation:
        """Instantiates an ECGAnnotation from a serialized dictionary."""
        return cls(
            sample=int(data["sample"]),
            timestamp_sec=float(data["timestamp_sec"]),
            label=str(data["label"]),
            sublabel=str(data.get("sublabel", "")),
            author=str(data.get("author", "AI_DETECTOR")),
            is_manual_override=bool(data.get("is_manual_override", False)),
            notes=str(data.get("notes", "")),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
        )


class AnnotationManager:
    """Manages collection, query, mutation, and serialization of study annotations."""

    def __init__(self, annotations: Optional[List[ECGAnnotation]] = None) -> None:
        self._annotations: List[ECGAnnotation] = list(annotations) if annotations else []

    def __len__(self) -> int:
        return len(self._annotations)

    def __iter__(self):
        return iter(self._annotations)

    @property
    def annotations(self) -> List[ECGAnnotation]:
        """Returns sorted list of annotations."""
        return sorted(self._annotations, key=lambda a: a.sample)

    def add_annotation(
        self,
        sample: int,
        timestamp_sec: float,
        label: str,
        sublabel: str = "",
        author: str = "AI_DETECTOR",
        is_manual_override: bool = False,
        notes: str = "",
    ) -> ECGAnnotation:
        """Adds a new annotation record to the study."""
        ann = ECGAnnotation(
            sample=sample,
            timestamp_sec=timestamp_sec,
            label=label.upper(),
            sublabel=sublabel,
            author=author,
            is_manual_override=is_manual_override,
            notes=notes,
        )
        self._annotations.append(ann)
        return ann

    def override_beat_label(
        self,
        sample: int,
        new_label: str,
        reviewer: str = "Physician",
        notes: str = "",
        tolerance_samples: int = 25,
    ) -> Optional[ECGAnnotation]:
        """Overrides an existing beat annotation with a manual physician diagnosis.

        Locates the nearest existing annotation within tolerance_samples and updates it,
        or creates a new override annotation if none exists nearby.
        """
        target: Optional[ECGAnnotation] = None
        min_dist = float("inf")

        for ann in self._annotations:
            dist = abs(ann.sample - sample)
            if dist < min_dist and dist <= tolerance_samples:
                min_dist = dist
                target = ann

        if target is not None:
            target.label = new_label.upper()
            target.author = reviewer
            target.is_manual_override = True
            if notes:
                target.notes = notes
            return target
        else:
            ts = float(sample) / 500.0  # default 500 Hz fallback if not calibrated
            return self.add_annotation(
                sample=sample,
                timestamp_sec=ts,
                label=new_label,
                author=reviewer,
                is_manual_override=True,
                notes=notes,
            )

    def get_by_label(self, label: str) -> List[ECGAnnotation]:
        """Filters annotations matching a specific AAMI label (e.g. 'V')."""
        l_upper = label.upper()
        return [a for a in self._annotations if a.label == l_upper]

    def get_in_time_range(self, start_sec: float, end_sec: float) -> List[ECGAnnotation]:
        """Returns annotations falling inside a specific temporal window [start_sec, end_sec]."""
        return [a for a in self._annotations if start_sec <= a.timestamp_sec <= end_sec]

    def get_manual_overrides(self) -> List[ECGAnnotation]:
        """Returns all annotations that were manually created or overridden by a clinician."""
        return [a for a in self._annotations if a.is_manual_override]

    def summary(self) -> Dict[str, Any]:
        """Generates statistical count summary of annotations."""
        counts: Dict[str, int] = {}
        override_count = 0

        for a in self._annotations:
            counts[a.label] = counts.get(a.label, 0) + 1
            if a.is_manual_override:
                override_count += 1

        return {
            "total_annotations": len(self._annotations),
            "label_counts": counts,
            "manual_overrides": override_count,
            "ai_detected": len(self._annotations) - override_count,
        }

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """Serializes all annotations into a list of dictionaries for .pecg or JSON storage."""
        return [a.to_dict() for a in self.annotations]

    @classmethod
    def from_dict_list(cls, dict_list: List[Dict[str, Any]]) -> AnnotationManager:
        """Instantiates an AnnotationManager from a list of serialized dictionaries."""
        mgr = cls()
        for d in dict_list:
            mgr._annotations.append(ECGAnnotation.from_dict(d))
        return mgr

    def to_physionet_table(self) -> str:
        """Exports annotations in tabular text format compatible with PhysioNet rdann/wrann."""
        lines = ["# Time (s)\tSample\tType\tSub\tReviewer\tNotes"]
        for a in self.annotations:
            over = "[OVERRIDE]" if a.is_manual_override else ""
            lines.append(f"{a.timestamp_sec:10.3f}\t{a.sample:10d}\t{a.label:4s}\t{a.sublabel:6s}\t{a.author:15s}\t{a.notes} {over}".strip())
        return "\n".join(lines)
