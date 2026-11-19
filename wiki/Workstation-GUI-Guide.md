# Workstation GUI Guide

The Repolaris workstation GUI (`repolaris-gui`) provides a 60fps hardware-accelerated environment for interactive Holter analysis, caliper calibration, QT-RR restitution modeling, hourly Holter triage, and printable clinical PDF reporting.

---

## 1. Launching the GUI

```bash
repolaris-gui
```

---

## 2. Interface Layout

```
+--------------------------------------------------------------------------------------------------+
| Repolaris - Interactive QT Caliper & Autonomic Workstation (PyQtGraph)                           |
+--------------------------------------------------------------------------------------------------+
| [📂 Open] [⚡ Demo] [📤 Export (.pecg)] [📄 PDF Report] [Channel: Lead II v] [⚙️ Settings]       |
+--------------------------------------------------------------------------------------------------+
| [ECG Waveform — Lead II] [Canvas: Dark v] [⊞ Lines] [⁚ Dots] [⊘ Off] [📏 Calipers] [📐 25 mm/s]   |
| [Main Waveform Canvas - 60fps PyQtGraph]                  | [Clinical Inspector Tabs (7 Tabs)]   |
|                                                           | ------------------------------------ |
|   /\          /\          /\          /\                  | 1. 📊 Clinical Overview              |
|  /  \  _/\   /  \  _/\   /  \  _/\   /  \  _/\            | 2. 🚨 Events Diary                   |
| /    \/   \_/    \/   \_/    \/   \_/    \/   \_          | 3. 📋 All Heartbeats                 |
|   |         |                                             | 4. 📈 QT-RR Dynamics                 |
|   |<-Region>|                                             | 5. 🕒 Holter Triage                  |
| (Gold)    (Purple)                                        | 6. 📋 Study & Patient                |
| Q-Onset   T-End                                           |                                      |
| --------------------------------------------------------- |                                      |
| [Live Caliper Readout HUD: QT | RR | Bazett | Fridericia] |                                      |
+--------------------------------------------------------------------------------------------------+
```

---

## 3. Key Interactive Features

### 3.0 Application Menu Bar (`QMenuBar`)
The workstation incorporates a native desktop menu bar organized into three dedicated menus:
* **File:**
  * **Open Study (`Ctrl+O`):** Launches file dialog to load clinical ECG records (`.dcm`, `.xml`, `.scp`, `.pecg`, `.ecg`, `.e3c`, `.edf`, `.hea`, `.csv`, `.npy`).
  * **Export Study (`Ctrl+E`):** Packages waveforms, calibrated calipers, and triage events into a compressed `.pecg` container for colleague exchange.
  * **Export Clinical PDF Report (`Ctrl+P`):** Generates a 2-page printable clinical PDF report (`generate_clinical_pdf_report`) with demographics, KPI summary, 10-second calibrated rhythm strip, Events Diary, hourly Holter table, Poincaré plot, and QT-RR restitution curve.
  * **Close Study (`Ctrl+W`):** Closes the currently loaded study, clears waveform curves and tables, and resets the workspace to an empty state.
  * **Exit (`Ctrl+Q`):** Safely terminates the application.
* **Preferences:**
  * **Languages (Dropdown Submenu):** Provides direct live switching across English (`en`), Español (`es`), Français (`fr`), Deutsch (`de`), and Português (`pt`).
  * **Interface Theme (Dropdown Submenu):** Switches the application window styling between **Clinical Dark**, **Clinical Light**, and **Color Blind Safe**.
  * **Canvas Theme (Dropdown Submenu):** Selects independent plot palettes (**Dark**, **Clinical Paper**, **Classic ECG Pink Paper**, **Color Blind Safe**, or **Emerald Phosphor**).
  * **Calipers (`Ctrl+K`):** Checkable toggle action that shows or hides draggable caliper lines and the bottom caliper HUD strip.
* **Help:**
  * **Documentation & Wiki (`F1`):** Opens the Repolaris documentation wiki and clinical user guide.
  * **License:** Displays the open-source Apache-2.0 software license terms and conditions.
  * **About Repolaris:** Displays the About dialog featuring brand identity, electrophysiology credits (AHA/ACC/HRS, FDA E14, AAMI EC57), and release version (v0.9.9).

### 3.1 Dynamic Multi-Lead Dropdown & Lead Switching
* Located in the top toolbar next to the file action buttons.
* When opening multi-channel recordings (e.g., 12-lead DICOM/SCP/HL7, 3-channel ISHNE Holters, multi-lead `.pecg`, or EDF+), the dropdown automatically enumerates all available channels (e.g., `Lead I`, `Lead II`, `V1`–`V6`).
* Automatically selects **Lead II** (or **V5**) by default in accordance with AHA/ACC/HRS and FDA E14 clinical guidelines for optimal T-wave prominence.
* Selecting any channel switches the active signal, re-executes the delineation pipeline, and recalculates R-peak fiducials, caliper positions, QTc metrics, and the Events Diary for that lead.

### 3.2 Draggable Digital Calipers
* **Gold Caliper Line (Q-Onset):** Click and drag along the time axis to adjust the start of ventricular depolarization.
* **Purple Caliper Line (T-End):** Click and drag to adjust the completion of ventricular repolarization.
* **Semi-Transparent Shaded Region:** Highlights the active measurement interval.
* **Live HUD Readout:** As calipers move, raw QT duration and rate-corrected $QT_c$ (Bazett and Fridericia) recalculate dynamically at 60 updates per second.

### 3.3 Exporting Anonymized Studies (`.pecg`) & Clinical PDF Reports (`.pdf`)
* **`.pecg` Study Bundle (`📤 Export Case (.pecg)`):** Prompts for de-identified patient demographics (Age, Sex, Race, Pacemaker status, Indication) and packages all recorded leads, caliper overrides, and annotations into a single compressed `.pecg` file.
* **Printable PDF Report (`📄 PDF Report` / `Ctrl+P`):** Exports a 2-page vector PDF report ready for hospital chart archival or physician sign-off.

### 3.4 Workstation Settings & Algorithm Selectors (`⚙️ Settings`)
Click **`⚙️ Settings`** in the top navigation bar to configure both visual styling and electrophysiological algorithms:
* **Interface Language Selector:** Live switching between English (`en`), Español (`es`), Français (`fr`), Deutsch (`de`), and Português (`pt`).
* **Interface & Canvas Themes:** Choose between **Clinical Dark**, **Clinical Light**, and **High Contrast / Color Blind Safe** window themes, plus 5 independent waveform canvas palettes.
* **Electrophysiology Algorithm Selectors:**
  * **QT-RR Restitution Model:** Select any of the **10 Pueyo (2004) biparametric models** (`linear`, `hyperbolic`, `parabolic_log`, `logarithmic`, `shifted_log`, `exponential`, `arctan`, `tanh`, `arcsinh`, `arccosh`) or `Auto-Select Best Model (Min AIC)`.
  * **Hysteresis Memory Kernel:** Toggle multi-beat hysteresis compensation between **Exponential Weighting (`EW`)**, **Linear Weighting (`LW`)**, or **Uncompensated (`Raw RR`)**.
  * **T-End Delineation Mode:** Switch between **Hybrid Steepest Descent (`hybrid`)**, **ICH E14 Tangent (`tangent`)**, **Zhang 2006 Sliding-Window Area (`zhang_area`)**, **Amplitude Threshold (`threshold`)**, and **Phasor Transform (`phasor`, Martínez et al., 2010)**.

### 3.5 Waveform Canvas Controls, Clinical Grid, Calipers & Zoom
* **Segmented Grid Toggle Buttons (`⊞ Lines`, `⁚ Dots`, `⊘ Off`):** Switch between solid millimeter calibration lines, dotted intersections, or an unobstructed canvas.
* **Conditional Clinical Scale Indicator Badge:** Displays the active clinical sweep speed and voltage gain (e.g., `📐 Scale: 25 mm/s | 10 mm/mV`) whenever the grid is enabled (`Lines` or `Dots`).
* **Caliper, Cursor & Beat Stepping Controls (`📏 Calipers`, `⟲ Center`, `➕ Line`, `◀`, `▶`):** Toggle caliper visibility, re-center calipers in the current viewport, drop extra vertical measurement cursors, or step beat-by-beat with **`◀` / `▶`** (`Left` / `Right` arrow keys).
* **Single-Key AAMI Reclassification Hotkeys (`N`, `V`, `S`, `F`, `Q`):** Pressing `N` (Normal), `V` (PVC), `S` (PAC), `F` (Fusion), or `Q` (Artifact) immediately reclassifies the active beat, updates on-canvas ectopic markers, recalculates PVC/PAC burden, rhythm sequences, HRV, and HRT, and logs an immutable audit entry in `AnnotationManager`.
* **Color-Coded Ectopic R-Peak Markers & On-Canvas Tags:** Normal beats (`N`, `#34d399`), PVCs (`V`, `#f87171`), PACs (`S`, `#fbbf24`), and Fusion beats (`F`, `#c084fc`) are color-coded directly on the waveform trace, with text tags (`V`, `S`, `F`, `Q`) rendered above non-normal R-peaks.
* **Clinical ECG Step-Wise Zoom Engine:**
  * **Sweep Speeds (X-Axis):** $12.5$, $25.0$ (standard), $50.0$, and $100.0\text{ mm/s}$.
  * **Voltage Gains (Y-Axis):** $2.5$, $5.0$, $10.0$ (standard), and $20.0\text{ mm/mV}$.
  * **Quick Navigation Buttons:** `−` (Zoom Out), `+` (Zoom In), `1:1` (Reset to $25\text{ mm/s}$ & $10\text{ mm/mV}$), and `⤢` (Fit full recording).
* **Millisecond Time Axis (`TimeAxisItem`):** Formats X-axis timestamps as `hh:mm:ss:xxx`.

---

## 4. The Seven Clinical Inspector Tabs

The right-hand dock (`self.tabs`) organizes all diagnostic metrics, interactive plots, and tables into seven dedicated tabs:

### 4.1 `📊 Clinical Overview`
* Displays executive KPI cards for **Mean Heart Rate**, **Ventricular Repolarization ($QT_c$ Bazett / Fridericia / Framingham / Hodges)**, **Ectopic Beat Burden (PVC / PAC counts & AAMI classes)**, and **Lead Signal Quality (SQI Status, SNR, $p\text{SQI}$, $bas\text{SQI}$)**.
* Summarizes advanced autonomic and repolarization indices including **Berger QTVI**, **QT-RR Slope & Individualized $QT_{c,\text{ind}}$**, **Hysteresis $\lambda^*$ & Adaptation Latency ($t_{90}$)**, **HRV ($SDNN$, $RMSSD$, $LF/HF$, $SD1/SD2$)**, **Heart Rate Turbulence ($TO$, $TS$, ISHNE Category)**, **Microvolt T-Wave Alternans (Spectral & MMA)**, and **Multi-Lead QT Dispersion ($QT_d$, $T_{pe,d}$)**.

### 4.2 `🚨 Events Diary`
* Lists all automatically flagged clinical episodes: Severe QTc Prolongation ($\ge 500\text{ ms}$), Borderline QTc ($\ge 480\text{ ms}$), Short QTc ($\le 340\text{ ms}$), Sinus Pauses ($\ge 2.0\text{ s}$), Bradycardia/Tachycardia extremes, and Ectopic runs.
* **Click-to-Seek:** Clicking any row pans the waveform canvas directly to that event and aligns the Q-onset and T-end calipers on the offending beat.

### 4.3 `📋 All Heartbeats`
* Displays a beat-by-beat table of every detected cardiac cycle with Timestamp, AAMI EC57 Class (`N`, `V`, `S`, `F`, `Q`), Rhythm Pattern (`NSR`, `Bigeminy`, `Trigeminy`, `Couplet`, `VT`), RR interval, instantaneous BPM, raw QT, and rate-corrected $QT_c$.
* **Physician Reclassification Dialog:** Double-clicking any beat opens the manual override modal to reclassify the beat and record an immutable ISO 8601 audit entry in `AnnotationManager`.

### 4.4 `📈 QT-RR Dynamics`
* **Interactive PyQtGraph Restitution Cloud (`qtrr_plot_widget`):** Plots raw $(RR, QT)$ pairs alongside hysteresis-compensated $(RR_\text{eff}, QT)$ points, overlays the continuous fitted Pueyo (2004) regression curve, and marks the patient-specific individualized $QT_{c,\text{ind}}$ at $RR = 1.0\text{ s}$.
* **Clickable 10-Model Leaderboard (`qtrr_models_table`):** Ranks all 10 Pueyo (2004) biparametric models by AIC, $R^2$, Pearson $r$, RMSE (ms), slope $\beta$, and $QT_{c,\text{ind}}$. Clicking any row immediately switches the active regression curve on the plot.

### 4.5 `🕒 Holter Triage`
* **Executive Holter & AF Banner (`lbl_holter_summary_banner`):** Displays total AF burden percentage, episode count, longest AF episode duration, total PVCs/PACs, and sinus pauses.
* **Hourly Holter Distribution Table (`holter_trends_table`):** Breaks multi-hour recordings into 1-hour epochs showing `Hour`, `Beats`, `Mean HR`, `Min/Max HR`, `PVCs`, `PACs`, `Couplets/VT`, `Pauses`, and `AF %`. Clicking any hour row seeks the main waveform canvas to the start of that hour.
* **Sustained AF / Flutter Episodes Table (`holter_af_table`):** Lists every detected AF episode ($\ge 30\text{ s}$) with onset time, duration, mean/max HR, Shannon entropy, and MAD irregularity score. Clicking any episode seeks the main canvas directly to the episode onset.

### 4.6 `🦋 Butterfly & T-PCA`
* Overlays R-peak-aligned ensemble median beats across all active leads with a spatial RMS magnitude curve, synchronized global calipers ($Q_{\text{onset}}, J, T_{\text{peak}}, T_{\text{end}}$), FDA CiPA sub-intervals ($J\text{–}T_{\text{peak}}c$, $T_{pe}$), and 3D SVD T-wave loop complexity metrics ($T_2/T_1$, $TCRT$).

### 4.7 `📋 Study & Patient`
* Displays **Core Patient Demographics & Timing** (Patient ID, Biological Sex, Age, Acquisition Date) and **Clinical Context & Study Specifications** (Pacemaker Status, Clinical Indication, Race/Ethnicity, De-identification Status, Source Format, Sampling Frequency $f_s$, Lead Count, Total Duration, and Review Notes).

---

## 5. Conditional Multi-Lead Gating

Repolaris automatically adapts its diagnostic calculations based on the number of synchronous leads loaded:

| Clinical Mode | Channel Quorum | QT Dispersion ($QT_d$) Behavior | Single-Lead Autonomic & Holter Suite |
| :--- | :--- | :--- | :--- |
| **Wearable Patch / Single-Lead** | $< 3$ Leads | **Gated (`N/A — Single Lead`):** Bypasses spatial dispersion to prevent degenerate zero-dispersion values. | **Fully Active:** QTVI, 10-model QT-RR restitution, Hysteresis, HRV, HRT, TWA, AF Burden, and Hourly Holter Trends run on the active lead. |
| **Holter / 12-Lead Diagnostic** | $\ge 3$ Leads | **Active:** Computes inter-lead $QT_d$, Fridericia-corrected $QTc_d$, precordial $T_{pe,d}$, and Stage 2 six-index pairwise lead voting ($VI_k$). | **Fully Active:** Evaluated on the optimal or user-selected lead alongside multi-lead spatial dispersion. |
