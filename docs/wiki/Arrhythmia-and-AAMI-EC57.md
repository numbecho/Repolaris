# Arrhythmia Classification, Rhythm Patterns & Holter Trends

Repolaris incorporates an automated beat classification engine, clinical annotation management system, and Holter trend breakdown aligned with **ANSI/AAMI EC57** international standards and the **Patrick Hamilton (2002)** OSEA framework.

---

## 1. AAMI EC57 Beat Taxonomy

Individual cardiac cycles are categorized into five standard classes:

```
+----------------------------------------------------------------------------------------------------+
| Class | Label                        | Morphological & Timing Criteria                             |
+----------------------------------------------------------------------------------------------------+
|   N   | Normal Sinus Beat            | Narrow QRS (< 100 ms), high correlation (r >= 0.85) to      |
|       |                              | the running patient sinus template.                         |
+----------------------------------------------------------------------------------------------------+
|   V   | Premature Ventricular (PVC)  | Marked prematurity (RR_pre < 0.82 * RR_median), QRS widening|
|       |                              | (>= 110 ms), low correlation (r < 0.70), compensatory pause.|
+----------------------------------------------------------------------------------------------------+
|   S   | Supraventricular Ectopic     | Premature coupling (RR_pre < 0.85 * RR_median) with narrow, |
|       | (PAC)                        | preserved sinus-like QRS morphology (r >= 0.80).            |
+----------------------------------------------------------------------------------------------------+
|   F   | Fusion Beat                  | Intermediate hybrid morphology combining characteristics of |
|       |                              | normal sinus conduction and ventricular ectopic focus.      |
+----------------------------------------------------------------------------------------------------+
|   Q   | Unknown / Artifact / Paced   | Distorted or unclassifiable waveform corrupted by motion    |
|       |                              | artifact or pacing spikes.                                  |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Patrick Hamilton (2002) OSEA Template Matching

Repolaris implements the unencumbered, public-domain Patrick Hamilton (2002) Open Source ECG Analysis dynamic template-matching classifier (`repolaris.detection.hamilton_classifier`):

* **Dynamic Morphology Clusters**: Automatically creates new template clusters when novel morphology variations occur.
* **12.5% Exponential Adaptation**: Updates dominant normal templates with a running exponential moving average:
  $$T_{n}[k] = (1 - \alpha) T_{n-1}[k] + \alpha \cdot X[k], \quad \alpha = 0.125$$
* **Dual Prematurity & Compensatory Gating**: Evaluates coupling interval against a running median of the last 8 normal cycles ($RR_\text{curr} < 0.82 \times RR_\text{local}$) and requires post-extrasystolic pause ($RR_\text{post} > 1.12 \times RR_\text{local}$).
* **Atrial Fibrillation Entropy Stabilizer**: Under chaotic, high-entropy rhythms (Shannon entropy $> 0.75$), isolated prematurity gating is suppressed to prevent normal narrow complexes from being misclassified as ventricular ectopics during AF with rapid ventricular response.

```python
from repolaris.detection.hamilton_classifier import HamiltonBeatClassifier

classifier = HamiltonBeatClassifier(fs=500.0)
classified_beats, summary = classifier.classify_recording(signal, r_peaks)
print(f"Total Beats: {summary['total_beats']} | PVCs: {summary['pvc_count']} | PACs: {summary['pac_count']}")
print(f"Ectopic Burden: {summary['ectopic_burden_pct']:.2f}% | Clusters Created: {summary['template_cluster_count']}")
```

---

## 3. Rhythm Sequence Detection

The engine analyzes temporal coupling patterns across adjacent beats:

* **Ventricular Bigeminy:** Alternating sinus and ventricular ectopic beats ($N - V - N - V$).
* **Ventricular Trigeminy:** Repetitive sequences of two sinus beats followed by one ectopic beat ($N - N - V - N - N - V$).
* **Ventricular Couplets:** Paired consecutive premature ventricular beats ($V - V$).
* **Ventricular Tachycardia (VT) Runs:** Runs of 3 or more consecutive ventricular ectopic beats ($V - V - V ...$) at elevated rates.

---

## 4. Hourly Arrhythmia Trends & Holter Histograms (`trends.py`)

For multi-hour and 24h/48h Holter monitoring, `generate_hourly_trends()` aggregates beat classifications, events, and AF burden into consecutive 1-hour epochs:

* **Heart Rate Extrema**: Tracks hourly minimum, mean, and maximum heart rates.
* **Ventricular Ectopy**: Counts isolated PVCs, Couplets, and VT runs per hour.
* **Supraventricular Ectopy**: Counts isolated PACs and SVEB runs per hour.
* **Bradyarrhythmias**: Indexes sinus pauses ($\ge 2.0\text{ s}$, $\ge 2.5\text{ s}$).
* **Hourly AF Burden**: Quantifies exact seconds and percentage of atrial fibrillation overlap within each epoch.

```python
from repolaris.detection.trends import generate_hourly_trends

trend_report = generate_hourly_trends(
    classified_beats,
    events=clinical_events,
    total_duration_sec=86400.0,
    af_episodes=af_report.episodes
)
print(f"Total Duration: {trend_report.total_duration_hours:.1f} hours | Total PVCs: {trend_report.total_pvcs}")
for b in trend_report.hourly_bins:
    print(f"Hour {b.hour_index}: Mean HR {b.mean_hr_bpm:.0f} BPM | PVCs: {b.pvc_count} | AF: {b.af_burden_pct:.1f}%")
```

---

## 5. Clinical Events Triage

The triage engine scans recordings to detect high-priority episodes:

* **Severe QTc Prolongation:** $QT_c \ge 500\text{ ms}$ (High risk for *Torsades de Pointes*).
* **Borderline QTc Prolongation:** $QT_c \ge 480\text{ ms}$.
* **Abnormally Short QTc:** $QT_c \le 340\text{ ms}$ (Short QT Syndrome screening).
* **Sinus Pauses / Asystole:** $RR \ge 2.0\text{ s}$ (Warning) and $RR \ge 2.5\text{ s}$ (Critical).
* **Heart Rate Extremes:** Severe Tachycardia ($> 120\text{ BPM}$), Severe Bradycardia ($< 45\text{ BPM}$), and Study Min/Max HR.

---

## 6. Clinical Annotation Management (`AnnotationManager`)

Medical software requires transparent physician oversight. The `repolaris.detection.annotations` module provides audit compliance:

* **Manual Override Tracking:** Captures original algorithmic values, modified clinical values, physician user IDs, and UTC timestamps formatted under ISO 8601.
* **PhysioNet Export:** Serializes clinical review annotations to standard `.atr` text files for cross-platform validation.
