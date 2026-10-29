# Arrhythmia Classification and AAMI EC57 Standards

Repolaris incorporates an automated beat classification engine and clinical annotation management system strictly aligned with the **ANSI/AAMI EC57** international standard.

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

## 2. Rhythm Sequence Detection

In addition to isolated beat classification, the engine analyzes temporal coupling patterns across adjacent beats:

* **Ventricular Bigeminy:** Alternating sinus and ventricular ectopic beats ($N - V - N - V$).
* **Ventricular Trigeminy:** Repetitive sequences of two sinus beats followed by one ectopic beat ($N - N - V - N - N - V$).
* **Ventricular Couplets:** Paired consecutive premature ventricular beats ($V - V$).
* **Ventricular Tachycardia (VT) Runs:** Runs of 3 or more consecutive ventricular ectopic beats ($V - V - V ...$) at elevated rates.

---

## 3. Clinical Events Triage

The triage engine scans recordings to detect high-priority events:

* **Severe QTc Prolongation:** $QT_c \ge 500\text{ ms}$ (High risk for *Torsades de Pointes*).
* **Borderline QTc Prolongation:** $QT_c \ge 480\text{ ms}$.
* **Abnormally Short QTc:** $QT_c \le 340\text{ ms}$ (Short QT Syndrome screening).
* **Sinus Pauses / Asystole:** $RR \ge 2.0\text{ s}$ (Warning) and $RR \ge 2.5\text{ s}$ (Critical).
* **Heart Rate Extremes:** Severe Tachycardia ($> 120\text{ BPM}$), Severe Bradycardia ($< 45\text{ BPM}$), and Study Min/Max HR.

---

## 4. Clinical Annotation Management (`AnnotationManager`)

Medical software requires transparent physician oversight. The `repolaris.detection.annotations` module provides audit compliance:

* **Manual Override Tracking:** Captures original algorithmic values, modified clinical values, physician user IDs, and UTC timestamps formatted under ISO 8601.
* **PhysioNet Export:** Serializes clinical review annotations to standard `.atr` text files for cross-platform validation.

```python
from repolaris.detection.annotations import AnnotationManager

mgr = AnnotationManager()
mgr.add_annotation(sample=15024, symbol="N", comment="Algorithmic classification")

# Physician reclassifies beat to Premature Ventricular Contraction
mgr.override_annotation(
    sample=15024,
    new_symbol="V",
    physician_id="Dr. Mercantete",
    notes="Widened QRS with compensatory pause"
)

# Export audit log
audit_trail = mgr.get_audit_log()
print(audit_trail)
```
