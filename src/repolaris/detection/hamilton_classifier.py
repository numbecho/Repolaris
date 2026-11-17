"""Hamilton (2002) Open Source ECG Analysis (OSEA) Template Beat Classifier.

Reference:
- P. S. Hamilton, "Open source ECG analysis," Computers in Cardiology, 2002, pp. 101-104.
  doi: 10.1109/CIC.2002.1166717.
- P. S. Hamilton and W. J. Tompkins, "Quantitative investigation of QRS detection rules
  using the MIT/BIH arrhythmia database," IEEE Trans. Biomed. Eng., 1986.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import numpy as np

from repolaris.detection.classifier import (
    BeatClass,
    BeatFeatures,
    ClassifiedBeat,
    RhythmPattern,
    detect_rhythm_patterns,
)


@dataclass
class MorphologyTemplate:
    """A running heartbeat morphology template cluster."""
    template_id: int
    beat_class: BeatClass
    waveform: np.ndarray
    count: int = 1
    mean_width_ms: float = 85.0
    mean_amplitude_mv: float = 1.0


class HamiltonBeatClassifier:
    """Patrick Hamilton (2002) OSEA template matching and dynamic beat classification engine."""

    def __init__(
        self,
        fs: float = 500.0,
        match_threshold: float = 0.82,
        prematurity_ratio: float = 0.82,
        adaptation_rate: float = 0.125,
    ) -> None:
        self.fs = fs
        self.match_threshold = match_threshold
        self.prematurity_ratio = prematurity_ratio
        self.adaptation_rate = adaptation_rate

        self.templates: list[MorphologyTemplate] = []
        self.dominant_template_id: int = 0
        self.rr_history: list[float] = []
        self.window_samples = int(0.16 * fs)

    def classify_recording(
        self,
        signal: np.ndarray,
        r_peaks: np.ndarray,
        q_onsets: np.ndarray | None = None,
        t_ends: np.ndarray | None = None,
    ) -> tuple[list[ClassifiedBeat], dict[str, Any]]:
        """Executes Hamilton OSEA template clustering, AF entropy gating, and rhythm sequence detection."""
        n_peaks = len(r_peaks)
        if n_peaks == 0:
            return [], {
                "total_beats": 0,
                "counts": {},
                "pvc_count": 0,
                "pac_count": 0,
                "pvc_percentage": 0.0,
                "ectopic_burden_pct": 0.0,
                "template_cluster_count": 0,
                "algorithm": "Hamilton (2002) OSEA Template Matching",
                "af_stabilized": False,
            }

        if n_peaks > 8:
            all_rrs = np.diff(r_peaks) / self.fs
            counts_hist, _ = np.histogram(all_rrs, bins=16, density=False)
            probs = counts_hist / float(len(all_rrs))
            probs = probs[probs > 0]
            shannon_ent = -float(np.sum(probs * np.log2(probs))) / np.log2(16) if len(probs) > 1 else 0.0
            is_high_entropy_rhythm = shannon_ent > 0.75
        else:
            is_high_entropy_rhythm = False

        if n_peaks > 1:
            initial_rrs = np.diff(r_peaks[: min(10, n_peaks)]) / self.fs
            self.rr_history = list(initial_rrs)
            running_rr = float(np.median(initial_rrs))
        else:
            self.rr_history = [1.0]
            running_rr = 1.0

        half_w = self.window_samples // 2
        classified_beats: list[ClassifiedBeat] = []

        for i, r_idx in enumerate(r_peaks):
            start_s = max(0, int(r_idx) - half_w)
            end_s = min(len(signal), int(r_idx) + half_w)
            beat_slice = signal[start_s:end_s]

            if len(beat_slice) < self.window_samples:
                padded = np.zeros(self.window_samples, dtype=np.float32)
                p_start = max(0, half_w - (int(r_idx) - start_s))
                padded[p_start : p_start + len(beat_slice)] = beat_slice
                beat_slice = padded

            p2p = float(np.max(beat_slice) - np.min(beat_slice))
            std = float(np.std(beat_slice))
            norm_slice = (beat_slice - np.mean(beat_slice)) / (std if std > 1e-6 else 1.0)

            pre_rr = float(r_idx - r_peaks[i - 1]) / self.fs if i > 0 else running_rr
            post_rr = float(r_peaks[i + 1] - r_idx) / self.fs if i < n_peaks - 1 else running_rr
            pre_ratio = pre_rr / running_rr if running_rr > 0 else 1.0
            post_ratio = post_rr / running_rr if running_rr > 0 else 1.0
            comp_ratio = (pre_rr + post_rr) / (2.0 * running_rr) if running_rr > 0 else 1.0

            q_on = int(q_onsets[i]) if (q_onsets is not None and i < len(q_onsets)) else int(r_idx) - int(0.04 * self.fs)
            qrs_dur_ms = max(30.0, float(int(r_idx) + int(0.05 * self.fs) - q_on) / self.fs * 1000.0)

            best_match_id = -1
            best_corr = -1.0

            for tmpl in self.templates:
                if len(tmpl.waveform) == len(norm_slice):
                    corr = float(np.corrcoef(tmpl.waveform, norm_slice)[0, 1])
                    if corr > best_corr:
                        best_corr = corr
                        best_match_id = tmpl.template_id

            is_premature = pre_ratio < self.prematurity_ratio
            is_compensatory = comp_ratio >= 0.92 and post_ratio > 1.12
            is_wide = qrs_dur_ms >= 115.0

            if is_high_entropy_rhythm and not is_wide and best_corr >= 0.75:
                is_premature = False

            if best_corr >= self.match_threshold and best_match_id >= 0:
                matched_tmpl = self.templates[best_match_id]
                b_class = matched_tmpl.beat_class

                if b_class == BeatClass.NORMAL and is_premature and not is_wide:
                    b_class = BeatClass.PAC
                    confidence = 0.88
                    rationale = f"Hamilton OSEA: Premature (pre-RR {pre_ratio:.2f}) with normal template match (r={best_corr:.2f})"
                else:
                    if b_class == BeatClass.NORMAL:
                        matched_tmpl.waveform = (
                            (1.0 - self.adaptation_rate) * matched_tmpl.waveform
                            + self.adaptation_rate * norm_slice
                        )
                        matched_tmpl.count += 1
                    confidence = max(0.80, min(0.99, best_corr))
                    rationale = f"Hamilton OSEA: Matched template #{best_match_id} ({b_class}) with correlation {best_corr:.2f}"
            else:
                if is_premature and (is_wide or best_corr < 0.70):
                    b_class = BeatClass.PVC
                    confidence = 0.94 if is_compensatory else 0.88
                    rationale = f"Hamilton OSEA: Premature ectopic (pre-RR {pre_ratio:.2f}) with morph deviation (r={best_corr:.2f}, QRS={qrs_dur_ms:.1f}ms)"
                elif is_wide:
                    b_class = BeatClass.PVC
                    confidence = 0.85
                    rationale = f"Hamilton OSEA: Wide QRS ({qrs_dur_ms:.1f}ms) with unmatched morphology (r={best_corr:.2f})"
                else:
                    b_class = BeatClass.NORMAL
                    confidence = 0.82
                    rationale = f"Hamilton OSEA: New morphology cluster created (r={best_corr:.2f})"

                new_id = len(self.templates)
                self.templates.append(
                    MorphologyTemplate(
                        template_id=new_id,
                        beat_class=b_class,
                        waveform=norm_slice,
                        mean_width_ms=qrs_dur_ms,
                        mean_amplitude_mv=p2p,
                    )
                )

            if b_class == BeatClass.NORMAL:
                self.rr_history.append(pre_rr)
                if len(self.rr_history) > 8:
                    self.rr_history.pop(0)
                running_rr = float(np.median(self.rr_history))

            features = BeatFeatures(
                pre_rr_sec=pre_rr,
                post_rr_sec=post_rr,
                pre_rr_ratio=pre_ratio,
                post_rr_ratio=post_ratio,
                compensatory_ratio=comp_ratio,
                qrs_duration_ms=qrs_dur_ms,
                qrs_peak_to_peak_mv=p2p,
                qrs_energy=float(np.sum(norm_slice**2)),
                template_correlation=best_corr if best_corr >= 0 else 1.0,
                polarity=1 if signal[int(r_idx)] >= 0 else -1,
            )

            r_pattern = RhythmPattern.NORMAL_SINUS if b_class == BeatClass.NORMAL else RhythmPattern.ISOLATED_ECTOPIC

            classified_beats.append(
                ClassifiedBeat(
                    beat_index=i,
                    r_peak_sample=int(r_idx),
                    time_sec=float(r_idx / self.fs),
                    beat_class=b_class,
                    rhythm_pattern=r_pattern,
                    confidence=confidence,
                    features=features,
                    diagnostic_rationale=rationale,
                )
            )

        # Annotate coupled rhythm sequences (Bigeminy, Trigeminy, Couplets, VT runs)
        classified_beats = detect_rhythm_patterns(classified_beats)

        counts: dict[str, int] = {}
        for b in classified_beats:
            counts[b.beat_class.value] = counts.get(b.beat_class.value, 0) + 1

        total = len(classified_beats)
        pvc = counts.get(BeatClass.PVC.value, 0)
        pac = counts.get(BeatClass.PAC.value, 0)
        pvc_pct = float(pvc / total * 100.0) if total > 0 else 0.0
        burden = float((pvc + pac) / total * 100.0) if total > 0 else 0.0

        summary = {
            "total_beats": total,
            "counts": counts,
            "pvc_count": pvc,
            "pac_count": pac,
            "pvc_percentage": round(pvc_pct, 2),
            "ectopic_burden_pct": round(burden, 2),
            "template_cluster_count": len(self.templates),
            "algorithm": "Hamilton (2002) OSEA Template Matching",
            "af_stabilized": is_high_entropy_rhythm,
        }

        return classified_beats, summary
