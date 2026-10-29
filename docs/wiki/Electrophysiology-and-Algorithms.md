# Electrophysiological Foundations and Algorithms

Repolaris implements an extensive suite of validated mathematical and electrophysiological algorithms for ventricular repolarization research and clinical Holter monitoring.

---

## 1. Waveform Delineation

Accurate QT interval quantification depends on identifying two primary fiducial points:

### 1.1 Q-Onset Delineation
* **R-Peak Localization:** Detected using an enhanced Pan-Tompkins derivative and moving-average energy integration pipeline.
* **Inflection Search:** A backward search window (typically 80–120 ms preceding the R-peak) identifies the earliest inflection point where the first-order derivative exceeds baseline noise thresholds by more than 2.5 standard deviations.

### 1.2 T-End Delineation (Hybrid Slope-Intercept)
* **T-Peak Detection:** Identified within a forward search window (typically 120–450 ms following the R-peak).
* **Steepest Descent Tangent:** The maximum negative first-order derivative on the descending limb of the T-wave defines the tangent slope.
* **Baseline Intercept:** The intersection of this tangent line with the isoelectric PR/TP baseline defines the primary T-end.
* **Threshold Fallback:** For asymmetric or flat T-waves, a 15% amplitude threshold fallback ensures mathematical convergence.

---

## 2. Rate-Correction Formulations ($QT_c$)

Because heart rate dynamically modulates the ventricular action potential duration, measured raw QT intervals must be rate-corrected relative to the preceding cardiac cycle length ($RR$ interval in seconds):

| Formula | Equation | Description & Clinical Utility |
| :--- | :--- | :--- |
| **Bazett (1920)** | $$QT_c = \frac{QT}{\sqrt{RR}}$$ | Clinical gold standard; overcorrects at high HR (>85 bpm) and undercorrects at bradycardia (<60 bpm). |
| **Fridericia (1932)** | $$QT_c = \frac{QT}{\sqrt[3]{RR}}$$ | Cube-root correction; physiologically superior during tachycardia; preferred in FDA E14 TQT trials. |
| **Framingham (1992)** | $$QT_c = QT + 0.154 \cdot (1 - RR)$$ | Linear regression model from 5,018 Framingham Heart Study participants; minimizes rate distortion. |
| **Hodges (1983)** | $$QT_c = QT + 1.75 \cdot (HR - 60)$$ | Linear heart rate formulation widely implemented in hospital telemetry monitors. |

---

## 3. Berger QT Variability Index (QTVI)

While static $QT_c$ measures average repolarization duration, beat-to-beat repolarization lability reflects underlying myocardial electrical vulnerability. Repolaris implements Berger's classical formulation (*Berger et al., Circulation 1997*):

$$\text{QTVI} = \log_{10} \left( \frac{\sigma^2_{QT} / \mu^2_{QT}}{\sigma^2_{RR} / \mu^2_{RR}} \right) = \log_{10} \left( \frac{\sigma^2_{QT}}{\sigma^2_{RR}} \cdot \left(\frac{\mu_{RR}}{\mu_{QT}}\right)^2 \right)$$

* **Reference Ranges:**
  * Healthy Physiological Baseline: $-1.6$ to $-1.0$
  * Pathological Vulnerability: $> -0.5$ (indicative of heightened risk for ventricular fibrillation and sudden cardiac death).
* **Uniform Step-Integration Resampling:**
  Unevenly spaced beat series are resampled onto an equispaced 4 Hz grid using Berger's 1986 uniform step-integration algorithm (`resample_berger`), eliminating spline artifacts.

```python
from repolaris.detection.qtvi import compute_qtvi, resample_berger

# Compute QTVI across consecutive cycles
qtvi_result = compute_qtvi(qt_intervals_sec, rr_intervals_sec)
print(f"QTVI: {qtvi_result['qtvi']:.2f}")
print(f"Mean QT: {qtvi_result['mean_qt_ms']:.1f} ms | Mean RR: {qtvi_result['mean_rr_ms']:.1f} ms")
```

---

## 4. Dynamic QT-RR Restitution Modeling

During physical activity and autonomic shifts, the adaptation of the QT interval to changes in cycle length provides critical prognostic indicators. Repolaris fits six non-linear mathematical models across $(RR_i, QT_i)$ pairs:

1. **Linear:** $QT = a \cdot RR + b$
2. **Hyperbolic:** $QT = a \cdot \frac{1}{RR} + b$
3. **Parabolic-Logarithmic:** $\ln(QT) = a \cdot \ln(RR) + b \implies QT = e^b \cdot RR^a$
4. **Logarithmic:** $QT = a \cdot \ln(RR) + b$
5. **Exponential:** $QT = a \cdot e^{-RR} + b$
6. **Arc-Tangent:** $QT = a \cdot \arctan(RR) + b$

The engine returns optimal parameters $(a, b)$, coefficient of determination ($R^2$), and Root Mean Square Error (RMSE) for each model.

---

## 5. Spectral Signal Quality Indices (SQI)

To prevent automated algorithms from generating false alerts on corrupted leads, Repolaris evaluates spectral energy distributions:

* **QRS Relative Power ($p\text{SQI}$):** Ratio of energy in 5–15 Hz relative to 5–40 Hz. Values $\ge 0.65$ indicate crisp QRS morphology.
* **Baseline Stability ($bas\text{SQI}$):** Evaluates respiration wander in the 0–1 Hz band. Values $\ge 0.85$ confirm baseline stability.
* **Estimated SNR (dB):** Log ratio of cardiac band power (5–40 Hz) against muscular high-frequency noise (>40 Hz). Leads with $\text{SNR} < 12\text{ dB}$ are flagged for lead rejection.
