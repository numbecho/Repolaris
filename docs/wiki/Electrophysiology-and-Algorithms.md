# Electrophysiological Foundations and Algorithms

Repolaris implements an extensive suite of validated mathematical and electrophysiological algorithms for ventricular repolarization research, autonomic cardiovascular profiling, and clinical Holter monitoring.

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

---

## 6. QT Dispersion ($QT_d$) & Transmural Repolarization Dispersion

QT dispersion quantifies inter-lead spatial heterogeneity in ventricular recovery time, serving as a primary marker for myocardial vulnerability to reentrant arrhythmias (*Day et al., Br Heart J 1990*).

### 6.1 Multi-Lead Quorum & Pre-Conditioning
* **Channel Quorum:** Requires simultaneous acquisition across $\ge 3$ diagnostic leads (or standard 12-lead overlays). Single-lead recordings automatically disable $QT_d$ calculations.
* **Lead Quality Filtering:** Excludes leads with $\text{pSQI} < 0.65$, $\text{basSQI} < 0.85$, or $\text{SNR} < 12\text{ dB}$, and masks leads where peak-to-peak T-wave amplitude is $< 50\ \mu\text{V}$.

### 6.2 Mathematical Formulations
* **Global Q-Onset:** Defined as the earliest depolarization deflection across all qualified leads $\mathcal{L}$:
  $$Q_\text{onset,global}(i) = \min_{l \in \mathcal{L}} Q_\text{onset}^{(l)}(i)$$
* **Absolute QT Dispersion:**
  $$QT_d(i) = \max_{l \in \mathcal{L}} QT^{(l)}(i) - \min_{l \in \mathcal{L}} QT^{(l)}(i)$$
* **Rate-Corrected Dispersion ($QTc_d$):**
  $$QTc_d(i) = \max_{l \in \mathcal{L}} QTc^{(l)}(i) - \min_{l \in \mathcal{L}} QTc^{(l)}(i)$$
* **T-Peak to T-End Dispersion ($T_{pe,d}$):** Quantifies regional differences in transmural repolarization:
  $$T_{pe,d}(i) = \max_{l \in \mathcal{L}} \left(T_\text{end}^{(l)}(i) - T_\text{peak}^{(l)}(i)\right) - \min_{l \in \mathcal{L}} \left(T_\text{end}^{(l)}(i) - T_\text{peak}^{(l)}(i)\right)$$

### 6.3 Diagnostic Interpretation
* Normal Reference Range: $QT_d < 50\text{ ms}$
* Borderline Dispersion: $50\text{--}65\text{ ms}$
* Pathological Dispersion: $> 65\text{--}80\text{ ms}$ (significantly elevated risk for ventricular tachycardia/fibrillation and sudden cardiac death).

---

## 7. Microvolt T-Wave Alternans (TWA)

Microvolt T-Wave Alternans reflects beat-to-beat ABAB alternation in the morphology, polarity, or amplitude of the ST-T complex (*Smith et al., Circulation 1988; Rosenbaum et al., NEJM 1994*). Caused by cellular action potential duration alternans and intracellular $Ca^{2+}$ cycling instability in the sarcoplasmic reticulum, MTWA provides powerful prognostic stratification for arrhythmic risk.

### 7.1 Spectral Method (FFT)
Evaluated across a sliding analysis window of $M = 128$ consecutive normal sinus beats (AAMI Class `N`) at sustained heart rates ($90\text{--}120\text{ bpm}$):
1. Extract ST-T segment: $w(t) = [R + 80\text{ ms}, R + \min(0.65 \times RR, 450\text{ ms})]$.
2. Compute Discrete Fourier Transform across beat index $n = 0, \dots, 127$ for each time point within the window.
3. Compute alternans power at $f_\text{alt} = 0.5\text{ cycles/beat}$ relative to the adjacent noise band ($[0.44, 0.49]\text{ cycles/beat}$):
   $$V_\text{alt} = \sqrt{\max(0, P(0.5) - \mu_\text{noise})}$$
4. Alternans Ratio ($k$-score):
   $$k = \frac{P(0.5) - \mu_\text{noise}}{\sigma_\text{noise}}$$
   A test episode is clinically positive if $V_\text{alt} \ge 1.9\ \mu\text{V}$ and $k \ge 3.0$ sustained for $\ge 60\text{ seconds}$.

### 7.2 Modified Moving Average (MMA) Method
For continuous non-stationary ambulatory Holter monitoring (*Verrier et al., J Electrocardiol 2005*):
* Recursively updates odd and even beat morphology templates:
  $$T_\text{odd}[n] = T_\text{odd}[n-1] + \frac{x_\text{odd}[n] - T_\text{odd}[n-1]}{32}$$
  $$T_\text{even}[n] = T_\text{even}[n-1] + \frac{x_\text{even}[n] - T_\text{even}[n-1]}{32}$$
* Alternans voltage:
  $$V_\text{MMA} = \max_{t \in \text{ST-T}} |T_\text{odd}(t) - T_\text{even}(t)|$$
* Clinical thresholds: $V_\text{MMA} < 47\ \mu\text{V}$ (Normal), $47\text{--}65\ \mu\text{V}$ (Abnormal/Elevated Risk), $> 65\ \mu\text{V}$ (Severe Proarrhythmic Risk).

---

## 8. Heart Rate Turbulence (HRT)

Heart Rate Turbulence models the short-term autonomic baroreflex response of the sinus node following a solitary Premature Ventricular Contraction (PVC / Class `V`) (*Schmidt et al., Lancet 1999*).

### 8.1 Purity Filtering
Solitary PVCs are qualified only when framed by $\ge 2$ preceding sinus beats ($NN_{-2}, NN_{-1}$) and $\ge 15\text{--}20$ succeeding sinus beats ($NN_1, \dots, NN_{20}$), with coupling prematurity $RR_\text{pre} < 0.80 \times \text{median}(RR)$ and compensatory pause $RR_\text{post} > 1.20 \times \text{median}(RR)$. Sequences with intervening PACs or secondary PVCs are excluded.

### 8.2 Turbulence Onset (TO)
Quantifies early post-extrasystolic sinus acceleration:
$$TO = \frac{(NN_1 + NN_2) - (NN_{-2} + NN_{-1})}{NN_{-2} + NN_{-1}} \times 100\%$$
* Normal: $TO < 0\%$ (immediate sinus acceleration).
* Pathological: $TO \ge 0\%$ (blunted/absent baroreflex response).

### 8.3 Turbulence Slope (TS)
Quantifies late post-extrasystolic sinus deceleration. Derived from the maximum positive regression slope over 5 consecutive beats across the post-extrasystolic sequence ($NN_1$ through $NN_{20}$):
$$TS = \max_{i \in [1, 16]} \text{Slope}\left(\{k, \overline{NN}[k]\}_{k=i}^{i+4}\right) \quad (\text{ms/beat})$$
* Normal: $TS > 2.5\text{ ms/beat}$.
* Pathological: $TS \le 2.5\text{ ms/beat}$.

### 8.4 Clinical Risk Categories
* **Category 0:** Normal $TO < 0\%$ and Normal $TS > 2.5\text{ ms/beat}$ (Low Risk).
* **Category 1:** Either $TO \ge 0\%$ OR $TS \le 2.5\text{ ms/beat}$ (Intermediate Risk).
* **Category 2:** Both $TO \ge 0\%$ AND $TS \le 2.5\text{ ms/beat}$ (Severe Risk / Autonomic Denervation).

---

## 9. Comprehensive Heart Rate Variability (HRV) Suite

Adhering to the international standards of the Task Force of the ESC and NASPE (*Malik et al., Circulation 1996*), Repolaris provides time, frequency, and non-linear autonomic evaluations over Normal-to-Normal ($NN$) beat sequences.

### 9.1 Time-Domain Metrics
* **$SDNN$:** Standard deviation of all NN intervals:
  $$SDNN = \sqrt{\frac{1}{N-1}\sum_{i=1}^N (NN_i - \overline{NN})^2}$$
* **$RMSSD$:** Root mean square of successive differences (parasympathetic vagal tone):
  $$RMSSD = \sqrt{\frac{1}{N-1}\sum_{i=1}^{N-1} (NN_{i+1} - NN_i)^2}$$
* **$pNN50$:** Percentage of adjacent NN intervals with difference $> 50\text{ ms}$.
* **$SDANN$:** Standard deviation of 5-minute average NN intervals across 24 hours.
* **$SDNN_\text{index}$:** Mean of standard deviations across all 5-minute segments.

### 9.2 Frequency-Domain Metrics (Welch Periodogram)
Uniformly resampled onto a 4.0 Hz grid using `resample_berger`:
* **Very Low Frequency (VLF):** $0.0033\text{--}0.04\text{ Hz}$ (thermoregulation and renin-angiotensin dynamics).
* **Low Frequency (LF):** $0.04\text{--}0.15\text{ Hz}$ (baroreflex activity; joint sympathetic and parasympathetic influence).
* **High Frequency (HF):** $0.15\text{--}0.40\text{ Hz}$ (respiratory sinus arrhythmia; vagal parasympathetic modulation).
* **LF/HF Ratio:** Sympathovagal balance metric.
* **Normalized Units:**
  $$LF_\text{nu} = \frac{\text{LF}}{\text{Total Power} - \text{VLF}} \times 100, \quad HF_\text{nu} = \frac{\text{HF}}{\text{Total Power} - \text{VLF}} \times 100$$

### 9.3 Non-Linear Dynamics
* **Poincaré Plot Geometry:** Plots $NN_{i+1}$ against $NN_i$:
  $$SD1 = \sqrt{\frac{1}{2}\text{Var}(NN_i - NN_{i+1})} = \frac{RMSSD}{\sqrt{2}} \quad (\text{short-term beat-to-beat dispersion})$$
  $$SD2 = \sqrt{2\text{Var}(NN) - \frac{1}{2}\text{Var}(NN_i - NN_{i+1})} \quad (\text{long-term continuous dispersion})$$
  $$SD1/SD2\text{ Ratio}$$
* **Sample Entropy ($SampEn$):** Quantifies time-series complexity with embedding dimension $m = 2$ and tolerance $r = 0.2 \times SDNN$.
* **Detrended Fluctuation Analysis (DFA):** Evaluates fractal correlation scaling: short-range exponent $\alpha_1$ (4–11 beats) and long-range exponent $\alpha_2$ (12–64 beats).

---

## 10. Multi-Beat QT-RR Hysteresis & Lag-Weighted Profiles

Ventricular repolarization does not adjust instantaneously to changes in heart rate. Hysteresis causes the QT interval to lag behind RR transitions by 1 to 3 minutes ($60\text{--}180$ cycles) (*Pueyo et al., IEEE TBME 2004; Malik et al., J Physiol 2008*). Static rate-correction formulas during rate transitions produce mathematical over- or under-correction. Repolaris resolves this by deriving an effective memory-weighted cycle length ($RR_\text{eff}$).

### 10.1 Mathematical Formulation
$$RR_\text{eff}(i, \mathbf{w}) = \sum_{k=0}^{N-1} w_k RR_{i-k}, \quad \text{where } \sum_{k=0}^{N-1} w_k = 1, \quad w_k \ge 0$$

### 10.2 Weighting Kernels
* **Exponential Weighting (EW):**
  $$w_k(\lambda) = \frac{e^{-\lambda k}}{\sum_{j=0}^{N-1} e^{-\lambda j}}, \quad \lambda > 0$$
  Implemented recursively in state-space:
  $$RR_\text{eff}[i] = (1 - \alpha) RR_\text{eff}[i-1] + \alpha RR[i], \quad \alpha = 1 - e^{-\lambda}$$
  Adaptation Half-Life: $t_{1/2} = \frac{\ln(2)}{\lambda \cdot \overline{HR}_\text{hz}}\text{ seconds}$.
* **Linear Weighting (LW):**
  $$w_k(M) = \frac{2(M - k)}{M(M + 1)}, \quad k = 0, \dots, M-1$$

### 10.3 Patient-Specific Optimization
The memory decay parameter $\lambda^*$ is determined by minimizing the residual variance of the restitution curve:
$$\lambda^* = \arg\min_\lambda \sum_i \left[ QT_i - f\left(RR_\text{eff}(i, \lambda); \boldsymbol{\theta}\right) \right]^2$$
The 90% adaptation latency metric is defined as:
$$t_{90} = -\frac{\ln(0.1)}{\lambda^*} \times \overline{RR}\text{ seconds}$$
Replacing raw $RR_i$ with $RR_\text{eff}$ collapses open hysteresis loops in the $(RR, QT)$ plane into tight restitution curves, preventing false-positive drug-induced QT prolongation warnings.
