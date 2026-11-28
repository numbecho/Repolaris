"""Hamilton (2002) Open Source ECG Analysis (OSEA) Template Beat Classifier.

Reference:
- P. S. Hamilton, "Open source ECG analysis," Computers in Cardiology, 2002, pp. 101-104.
  doi: 10.1109/CIC.2002.1166717.
- P. S. Hamilton and W. J. Tompkins, "Quantitative investigation of QRS detection rules
  using the MIT/BIH arrhythmia database," IEEE Trans. Biomed. Eng., 1986.
"""

from __future__ import annotations

from collections import Counter, deque
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
    last_seen_beat_idx: int = 0


class HamiltonBeatClassifier:
    """Patrick Hamilton (2002) OSEA template matching and dynamic beat classification engine."""

    def __init__(
        self,
        fs: float = 500.0,
        match_threshold: float = 0.82,
        prematurity_ratio: float = 0.82,
        adaptation_rate: float = 0.125,
        max_templates: int = 24,
    ) -> None:
        self.fs = fs
        self.match_threshold = match_threshold
        self.prematurity_ratio = prematurity_ratio
        self.adaptation_rate = adaptation_rate
        self.max_templates = max(2, int(max_templates))

        self.templates: list[MorphologyTemplate] = []
        self.dominant_template_id: int = 0
        self._next_template_id: int = 0
        self.rr_history: list[float] = []
        self.recent_template_ids: deque[int] = deque(maxlen=180)
        self.recent_rr_irregular: deque[bool] = deque(maxlen=180)
        self._beats_since_normal: int = 0
        self._global_beat_idx: int = 0
        self.window_samples = int(0.16 * fs)

    def _update_dominant_template(self) -> MorphologyTemplate | None:
        """Selects the dominant NORMAL template over the last 180 beats (Hamilton 2002 Sec. 3.5)."""
        if not self.templates:
            return None
        recent_counts = Counter(self.recent_template_ids)
        normal_pool = [t for t in self.templates if t.beat_class == BeatClass.NORMAL]
        pool = normal_pool if normal_pool else self.templates
        dom = max(
            pool,
            key=lambda t: (recent_counts.get(t.template_id, 0), t.count, t.last_seen_beat_idx),
        )
        self.dominant_template_id = dom.template_id
        return dom

    def classify_recording(
        self,
        signal: np.ndarray,
        r_peaks: np.ndarray,
        q_onsets: np.ndarray | None = None,
        t_ends: np.ndarray | None = None,
        reset_state: bool = True,
    ) -> tuple[list[ClassifiedBeat], dict[str, Any]]:
        """Executes Hamilton OSEA template clustering, AF entropy gating, and rhythm sequence detection."""
        if reset_state:
            self.templates = []
            self.dominant_template_id = 0
            self._next_template_id = 0
            self.rr_history = []
            self.recent_template_ids.clear()
            self.recent_rr_irregular.clear()
            self._beats_since_normal = 0
            self._global_beat_idx = 0
        elif self.templates:
            max_existing_id = max(t.template_id for t in self.templates)
            if self._next_template_id <= max_existing_id:
                self._next_template_id = max_existing_id + 1

        n_peaks = len(r_peaks)
        if n_peaks == 0:
            return [], {
                "total_beats": 0,
                "counts": {},
                "pvc_count": 0,
                "pac_count": 0,
                "pvc_percentage": 0.0,
                "ectopic_burden_pct": 0.0,
                "template_cluster_count": len(self.templates),
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

        if not self.rr_history:
            if n_peaks > 1:
                initial_rrs = np.diff(r_peaks[: min(10, n_peaks)]) / self.fs
                self.rr_history = list(initial_rrs[-8:])
                running_rr = float(np.median(self.rr_history))
            else:
                self.rr_history = [1.0]
                running_rr = 1.0
        else:
            running_rr = float(np.median(self.rr_history))

        half_w = self.window_samples // 2
        classified_beats: list[ClassifiedBeat] = []
        beat_template_ids: list[int] = []
        any_af_stabilized = is_high_entropy_rhythm

        for i, r_idx in enumerate(r_peaks):
            self._global_beat_idx += 1
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

            is_measured_rr = i > 0
            pre_rr = float(r_idx - r_peaks[i - 1]) / self.fs if is_measured_rr else running_rr
            post_rr = float(r_peaks[i + 1] - r_idx) / self.fs if i < n_peaks - 1 else running_rr
            pre_ratio = pre_rr / running_rr if running_rr > 0 else 1.0
            post_ratio = post_rr / running_rr if running_rr > 0 else 1.0
            comp_ratio = (pre_rr + post_rr) / (2.0 * running_rr) if running_rr > 0 else 1.0

            q_on = int(q_onsets[i]) if (q_onsets is not None and i < len(q_onsets)) else int(r_idx) - int(0.04 * self.fs)
            qrs_dur_ms = max(30.0, float(int(r_idx) + int(0.05 * self.fs) - q_on) / self.fs * 1000.0)

            if is_measured_rr:
                rr_irreg = abs(pre_rr - running_rr) / max(running_rr, 1e-3) > 0.125
                self.recent_rr_irregular.append(rr_irreg)

            dom_tmpl = self._update_dominant_template()
            dom_width_ms = dom_tmpl.mean_width_ms if dom_tmpl is not None else 100.0

            best_match_tmpl: MorphologyTemplate | None = None
            best_corr = -1.0

            for tmpl in self.templates:
                if len(tmpl.waveform) == len(norm_slice):
                    corr = float(np.corrcoef(tmpl.waveform, norm_slice)[0, 1])
                    if corr > best_corr:
                        best_corr = corr
                        best_match_tmpl = tmpl

            is_irregular_rhythm = is_high_entropy_rhythm or (
                len(self.recent_rr_irregular) >= 12
                and (sum(self.recent_rr_irregular) / len(self.recent_rr_irregular)) >= (1.0 / 3.0)
            )
            if is_irregular_rhythm:
                any_af_stabilized = True

            is_premature = pre_ratio < self.prematurity_ratio
            is_compensatory = comp_ratio >= 0.92 and post_ratio > 1.12
            is_wide = qrs_dur_ms >= 115.0
            is_relatively_wide = (qrs_dur_ms > dom_width_ms + 20.0) and (qrs_dur_ms >= 110.0)


            assigned_tmpl_id = -1
            if best_corr >= self.match_threshold and best_match_tmpl is not None:
                assigned_tmpl_id = best_match_tmpl.template_id
                best_match_tmpl.count += 1
                best_match_tmpl.last_seen_beat_idx = self._global_beat_idx
                b_class = best_match_tmpl.beat_class

                if b_class == BeatClass.NORMAL and is_premature and not is_wide and not is_irregular_rhythm:
                    b_class = BeatClass.PAC
                    confidence = 0.88
                    rationale = (
                        f"Hamilton OSEA: Premature (pre-RR {pre_ratio:.2f}) with normal template match (r={best_corr:.2f})"
                    )
                else:
                    if b_class == BeatClass.NORMAL:
                        best_match_tmpl.waveform = (
                            (1.0 - self.adaptation_rate) * best_match_tmpl.waveform
                            + self.adaptation_rate * norm_slice
                        )
                        best_match_tmpl.mean_width_ms = (
                            (1.0 - self.adaptation_rate) * best_match_tmpl.mean_width_ms
                            + self.adaptation_rate * qrs_dur_ms
                        )
                    confidence = max(0.80, min(0.99, best_corr))
                    rationale = (
                        f"Hamilton OSEA: Matched template #{best_match_tmpl.template_id} ({b_class}) "
                        f"with correlation {best_corr:.2f}"
                    )
            else:
                if len(self.templates) == 0:
                    # Never seed the initial rhythm template as PVC (protects dominant BBB / wide-QRS rhythms)
                    b_class = BeatClass.NORMAL
                    confidence = 0.85
                    rationale = "Hamilton OSEA: Seeded initial dominant morphology template"
                elif is_irregular_rhythm:
                    # Hamilton 2002 Sec. 3.5-3.6: irregular/AFib rhythms require relative widening or severe divergence
                    if is_relatively_wide or best_corr < 0.45:
                        b_class = BeatClass.PVC
                        confidence = 0.88 if is_relatively_wide else 0.84
                        rationale = (
                            f"Hamilton OSEA: AFib-gated ventricular ectopic "
                            f"(r={best_corr:.2f}, QRS={qrs_dur_ms:.1f}ms vs dom={dom_width_ms:.1f}ms)"
                        )
                    else:
                        b_class = BeatClass.NORMAL
                        confidence = 0.82
                        rationale = f"Hamilton OSEA: AFib-gated morphology drift cluster (r={best_corr:.2f})"
                elif is_premature and (is_wide or best_corr < 0.70):
                    b_class = BeatClass.PVC
                    confidence = 0.94 if is_compensatory else 0.88
                    rationale = (
                        f"Hamilton OSEA: Premature ectopic (pre-RR {pre_ratio:.2f}) "
                        f"with morph deviation (r={best_corr:.2f}, QRS={qrs_dur_ms:.1f}ms)"
                    )
                elif is_wide and best_corr < 0.70:
                    b_class = BeatClass.PVC
                    confidence = 0.85
                    rationale = f"Hamilton OSEA: Wide QRS ({qrs_dur_ms:.1f}ms) with divergent morphology (r={best_corr:.2f})"
                else:
                    b_class = BeatClass.NORMAL
                    confidence = 0.82
                    rationale = f"Hamilton OSEA: New morphology cluster created (r={best_corr:.2f})"

                if len(self.templates) >= self.max_templates:
                    recent_counts = Counter(self.recent_template_ids)
                    evictable = [t for t in self.templates if t.template_id != self.dominant_template_id]
                    if evictable:
                        victim = min(
                            evictable,
                            key=lambda t: (recent_counts.get(t.template_id, 0), t.last_seen_beat_idx),
                        )
                        self.templates.remove(victim)

                new_id = self._next_template_id
                self._next_template_id += 1
                self.templates.append(
                    MorphologyTemplate(
                        template_id=new_id,
                        beat_class=b_class,
                        waveform=norm_slice,
                        mean_width_ms=qrs_dur_ms,
                        mean_amplitude_mv=p2p,
                        last_seen_beat_idx=self._global_beat_idx,
                    )
                )
                assigned_tmpl_id = new_id

            if assigned_tmpl_id >= 0:
                self.recent_template_ids.append(assigned_tmpl_id)

            if b_class == BeatClass.NORMAL:
                self._beats_since_normal = 0
                if is_measured_rr or reset_state:
                    self.rr_history.append(pre_rr)
                    if len(self.rr_history) > 8:
                        self.rr_history.pop(0)
                    running_rr = float(np.median(self.rr_history))
            else:
                self._beats_since_normal += 1
                if self._beats_since_normal >= 8 and is_measured_rr and 0.20 <= pre_rr <= 2.0:
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
            beat_template_ids.append(assigned_tmpl_id)

        # Promote any dominant morphology cluster (>=45% of beats) to NORMAL (AAMI N-class BBB safeguard)
        if self.templates and n_peaks >= 3:
            dom_all = max(self.templates, key=lambda t: t.count)
            total_seen = sum(t.count for t in self.templates)
            if dom_all.beat_class == BeatClass.PVC and dom_all.count >= max(3, int(0.45 * total_seen)):
                dom_all.beat_class = BeatClass.NORMAL
                for idx_b, tid in enumerate(beat_template_ids):
                    if tid == dom_all.template_id and classified_beats[idx_b].beat_class == BeatClass.PVC:
                        cb = classified_beats[idx_b]
                        classified_beats[idx_b] = ClassifiedBeat(
                            beat_index=cb.beat_index,
                            r_peak_sample=cb.r_peak_sample,
                            time_sec=cb.time_sec,
                            beat_class=BeatClass.NORMAL,
                            rhythm_pattern=RhythmPattern.NORMAL_SINUS,
                            confidence=cb.confidence,
                            features=cb.features,
                            diagnostic_rationale="Hamilton OSEA: Dominant rhythm cluster promoted to NORMAL",
                        )
            self._update_dominant_template()

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
            "af_stabilized": any_af_stabilized,
        }

        return classified_beats, summary
