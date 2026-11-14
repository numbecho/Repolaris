# Electrophysiological Foundations and Algorithms

Repolaris implements an extensive suite of validated mathematical and electrophysiological algorithms for ventricular repolarization research, autonomic cardiovascular profiling, and clinical Holter monitoring.

---

## 1. Waveform Delineation

Accurate QT interval quantification depends on identifying two primary fiducial points:

### 1.1 Q-Onset Delineation
* **R-Peak Localization:** Detected using an enhanced Pan-Tompkins derivative and moving-average energy integration pipeline.
* **Inflection Search:** A backward search window (typically 80–120 ms preceding the R-peak) identifies the earliest inflection point where the first-order derivative exceeds baseline noise thresholds by more than 2.5 standard deviations.

### 1.2 T-End Delineation Modes
Repolaris provides four selectable T-end delineation algorithms:
1. **Hybrid Steepest Descent (`"hybrid"` - Default):** Combines steepest-descent tangent intersection with the isoelectric baseline and a 15% amplitude threshold fallback.
2. **ICH E14 Tangent (`"tangent"`):** Formal tangent intersection recommended for Thorough QT clinical trials.
3. **Zhang (2006) Sliding-Window Area (`"zhang_area"`):** Sliding-window area (SWA) integration method (*Zhang et al., IEEE TBME 2006*) maximizing delineation stability under low amplitude or noisy T-waves.
4. **Amplitude Threshold (`"threshold"`):** Direct percentage offset along the descending limb.

---

## 2. Rate-Correction Formulations ($QT_c$)

Measured raw QT intervals must be rate-corrected relative to the cardiac cycle length ($RR$ in seconds):

| Formula | Equation | Description & Clinical Utility |
| :--- | :--- | :--- |
| **Bazett (1920)** | $$QT_c = \frac{QT}{\sqrt{RR}}$$ | Clinical standard; overcorrects at tachycardia (>85 bpm) and undercorrects at bradycardia (<60 bpm). |
| **Fridericia (1932)** | $$QT_c = \frac{QT}{\sqrt[3]{RR}}$$ | Cube-root correction; physiologically superior during tachycardia; preferred in FDA E14 TQT trials. |
| **Framingham (1992)** | $$QT_c = QT + 0.154 \cdot (1 - RR)$$ | Linear regression model from 5,018 Framingham Heart Study participants; minimizes rate distortion. |
| **Hodges (1983)** | $$QT_c = QT + 1.75 \cdot (HR - 60)$$ | Linear heart rate formulation widely implemented in hospital telemetry monitors. |

---

## 3. Atrial Fibrillation & Flutter Burden Engine (`af_detector.py`)

Repolaris provides native, automated detection of sustained Atrial Fibrillation (AF) and Atrial Flutter episodes:

### 3.1 Shannon Entropy of RR Distribution
In Normal Sinus Rhythm (NSR), RR intervals are tightly clustered around a single central cycle length. In Atrial Fibrillation, disorganized atrial activity produces chaotic atrioventricular conduction, broadening the distribution.
$$H(RR) = -\sum_{i=1}^B p_i \log_2(p_i) \Big/ \log_2(B)$$
Values of normalized entropy $H(RR) \ge 0.68$ indicate chaotic AV conduction.

### 3.2 Median Absolute Difference (MAD) Irregularity
Successive beat-to-beat cycle variation is quantified using the normalized median absolute difference of successive RR intervals:
$$\text{Irregularity} = \frac{\text{median}(|RR_{i+1} - RR_i|)}{\text{median}(RR)}$$
Values exceeding $0.12$ confirm rhythm irregularity.

### 3.3 Episode Segmentation & Burden Percentage
* Sustained runs satisfying both entropy and irregularity thresholds for $\ge 30\text{ seconds}$ are isolated as discrete clinical episodes.
* **AF Burden Percentage:**
  $$\text{Burden (\%)} = \frac{\sum \text{Episode Duration}}{\text{Total Recording Duration}} \times 100$$

```python
from repolaris.detection.af_detector import detect_atrial_fibrillation

report = detect_atrial_fibrillation(r_peaks, fs=500.0, min_episode_duration_sec=30.0)
print(f"Total AF Duration: {report.af_total_duration_sec:.1f} s | AF Burden: {report.af_burden_pct:.2f}%")
print(f"Total Episodes: {report.num_episodes} | Longest Episode: {report.longest_episode_sec:.1f} s")
```

---

## 4. Berger QT Variability Index (QTVI)

Measures beat-to-beat ventricular repolarization lability (*Berger et al., Circulation 1997*):

$$\text{QTVI} = \log_{10} \left( \frac{\sigma^2_{QT} / \mu^2_{QT}}{\sigma^2_{RR} / \mu^2_{RR}} \right)$$

* Healthy Physiological Baseline: $-1.6$ to $-1.0$
* Pathological Vulnerability: $> -0.5$ (indicative of elevated risk for ventricular fibrillation).
* **Berger Resampling:** Resamples uneven beat series onto an equispaced 4 Hz grid using uniform step-integration (`resample_berger`).

---

## 5. Domain-Guarded QT-RR Restitution Modeling

Repolaris fits all **10 biparametric formulations** established by Pueyo et al. (*IEEE TBME 2004*):

1. **Linear:** $QT = a \cdot RR + b$
2. **Hyperbolic:** $QT = a \cdot \frac{1}{RR} + b$
3. **Parabolic-Logarithmic:** $\ln(QT) = a \cdot \ln(RR) + b$
4. **Logarithmic:** $QT = a \cdot \ln(RR) + b$
5. **Shifted-Logarithmic:** $QT = a \cdot \ln(RR + 0.1) + b$
6. **Exponential:** $QT = a \cdot e^{-RR} + b$
7. **Arc-Tangent:** $QT = a \cdot \arctan(RR) + b$
8. **Hyperbolic Tangent:** $QT = a \cdot \tanh(RR) + b$
9. **Inverse Hyperbolic Sine:** $QT = a \cdot \text{arcsinh}(RR) + b$
10. **Inverse Hyperbolic Cosine:** $QT = a \cdot \text{arccosh}(RR + 1.0) + b$

Includes Vandermonde conditioning guards and estimates patient-specific individualized rate-corrected QT: $QT_{c,\text{ind}} = f(1.0\text{ s})$.

---

## 6. Two-Stage Signal Quality Assessment (SQI)

To protect clinical automated decisions against motion noise and detachment:
* **Stage 1 (Absolute Physiological Gates):** Screens QRS energy ratio ($p\text{SQI} \ge 0.65$), baseline stability ($bas\text{SQI} \ge 0.85$), kurtosis ($k\text{SQI} \ge 5.0$), skewness ($s\text{SQI} > 0$), and $\text{SNR} \ge 12\text{ dB}$ (*Li, Rajagopalan & Clifford, 2014*). Detached or flatlined leads are immediately rejected.
* **Stage 2 (Six-Index Pairwise Voting):** Qualified leads undergo pairwise relative voting across six indices yielding a composite score $VI_k \in [-6, +6]$ (*Suárez-León et al., 2018*) to elect the optimal lead for automated caliper delineation.

---

## 7. Multi-Lead QT Dispersion ($QT_d$)

Quantifies inter-lead spatial heterogeneity in ventricular recovery time:
* **Channel Quorum:** Requires synchronous acquisition across $\ge 3$ diagnostic leads (or 12-lead overlays).
* **Metrics:** Absolute dispersion $QT_d = \max QT - \min QT$, rate-corrected dispersion $QTc_d$, and precordial transmural dispersion $T_{pe,d} = \max T_{pe} - \min T_{pe}$.

---

## 8. Microvolt T-Wave Alternans (TWA)

Evaluates beat-to-beat ABAB alternation in ST-T amplitude:
* **Spectral FFT ($0.5\text{ cpb}$):** Clinically positive if $V_\text{alt} \ge 1.9\ \mu\text{V}$ and $k \ge 3.0$ sustained for $\ge 60\text{ s}$.
* **Modified Moving Average (MMA):** Recursively tracks odd and even beat morphology templates for continuous Holter monitoring:
  $$V_\text{MMA} = \max |T_\text{odd}(t) - T_\text{even}(t)|$$

---

## 9. Heart Rate Turbulence (HRT)

Models baroreflex autonomic response following solitary PVCs:
* **Turbulence Onset ($TO$):** Early post-extrasystolic sinus acceleration ($TO < 0\%$ is normal).
* **Turbulence Slope ($TS$):** Late post-extrasystolic sinus deceleration ($TS > 2.5\text{ ms/beat}$ is normal).
* **Risk Stratification:** ISHNE Category 0 (normal), Category 1 (one abnormal), Category 2 (both abnormal / high risk).

---

## 10. Heart Rate Variability (HRV) Suite

Adheres to ESC/NASPE Task Force standards across normal $NN$ cycles:
* **Time Domain:** $SDNN$, $RMSSD$, $pNN50$, $SDANN$, $SDNN_\text{index}$.
* **Frequency Domain:** Welch periodogram bands over 4.0 Hz resampled series ($ULF$, $VLF$, $LF$, $HF$, $LF/HF$, $LF_\text{nu}$, $HF_\text{nu}$).
* **Non-Linear Dynamics:** Poincaré geometry ($SD1$, $SD2$, $SD1/SD2$), Sample Entropy ($SampEn$), and Detrended Fluctuation Analysis ($\alpha_1$, $\alpha_2$).

---

## 11. Multi-Beat QT-RR Hysteresis

Compensates for the 1-to-3 minute physiological lag of repolarization behind rate changes using memory-weighted effective RR intervals ($RR_\text{eff}$):
* **Kernels:** State-space Exponential Weighting (EW) and Linear Weighting (LW).
* **Optimization:** Solves for patient-specific decay parameter $\lambda^*$, 90% adaptation latency $t_{90}$, and eliminates open hysteresis loops in the $(RR, QT)$ plane.
