# Workstation GUI Guide

The Repolaris workstation GUI (`repolaris-gui`) provides a 60fps hardware-accelerated environment for interactive Holter analysis, caliper calibration, spatial repolarization inspection, and autonomic triage.

---

## 1. Launching the GUI

```bash
repolaris-gui
```
*(Legacy alias: `pyecg-gui`)*

---

## 2. Interface Layout

```
+----------------------------------------------------------------------------------+
| Repolaris - Interactive QT Caliper & Autonomic Workstation (PyQtGraph)           |
+----------------------------------------------------------------------------------+
| [ECG Waveform — Lead II] [Canvas: Dark v] [Grid: Lines v] [📐 25 mm/s | 10 mm/mV] |
| [Main Waveform Canvas - 60fps PyQtGraph]              | [Sidebar Controls]       |
|                                                       | ------------------------ |
|   /\          /\          /\          /\              | [Open File] [Demo] [⚙️ Settings] |
|  /  \  _/\   /  \  _/\   /  \  _/\   /  \  _/\        | Active Lead: [Lead II v] |
| /    \/   \_/    \/   \_/    \/   \_/    \/   \_      | ------------------------ |
|   |         |                                         | Live Caliper Readout:    |
|   |<-Region>|                                         |  QT: 412.0 ms            |
| (Gold)    (Purple)                                    |  Bazett QTc: 438.2 ms    |
| Q-Onset   T-End                                       |  Fridericia: 429.1 ms    |
|                                                       | ------------------------ |
|                                                       | Navigation Tabs:         |
|                                                       | [Overview] [Events]      |
|                                                       | [Beats] [Study Info]     |
|                                                       | [Dispersion*] [HRV]      |
|                                                       | [HRT] [TWA] [Hyst]       |
+----------------------------------------------------------------------------------+
```
*\*The Spatial Dispersion tab is conditionally enabled when $\ge 3$ synchronous leads are detected.*

---

## 3. Key Interactive Features

### 3.0 Application Menu Bar (`QMenuBar`)
The workstation incorporates a native desktop menu bar organized into three dedicated menus:
* **File (`File(open study | export study | close study || exit)`):**
  * **Open Study (`Ctrl+O`):** Launches file dialog to load clinical ECG records (`.pecg`, `.ecg`, `.edf`, `.hea`, `.csv`).
  * **Export Study (`Ctrl+E`):** Packages waveforms, calibrated calipers, and triage events into a compressed `.pecg` container for colleague exchange.
  * **Close Study (`Ctrl+W`):** Closes the currently loaded study, clears waveform curves and tables, and resets the workspace to an empty state.
  * **Exit (`Ctrl+Q`):** Safely terminates the application.
* **Preferences (`Preferences(Languages | Interface theme | Canvas theme | calipers toggle)`):**
  * **Languages (Dropdown Submenu):** Provides direct live switching across English (`en`), Español (`es`), Français (`fr`), Deutsch (`de`), and Português (`pt`).
  * **Interface Theme (Dropdown Submenu):** Switches the application window styling between **Clinical Dark**, **Clinical Light**, and **Color Blind Safe**.
  * **Canvas Theme (Dropdown Submenu):** Selects independent plot palettes (**Dark**, **Clinical Paper**, **Classic ECG Pink Paper**, **Color Blind Safe**, or **Emerald Phosphor**).
  * **Calipers (Toggle Action, `Ctrl+K`):** Checkable toggle action that shows or hides draggable caliper lines and the bottom caliper HUD strip, synchronized with the canvas toolbar button.
* **Help (`Help(shortcut link to wiki | License | about)`):**
  * **Documentation & Wiki (`F1`):** Direct shortcut link opening the official Repolaris documentation wiki and clinical user guide.
  * **License:** Displays the open-source Apache-2.0 software license terms and conditions.
  * **About Repolaris:** Displays the About dialog featuring brand identity, electrophysiology credits (AHA/ACC/HRS, FDA E14, AAMI EC57), and release version (v0.6.1).

### 3.1 Dynamic Multi-Lead Dropdown & Lead Switching
* Located in the **Study Controls** panel directly under the Open/Reload buttons.
* When opening multi-channel recordings (e.g., 12-lead ISHNE `.ecg`, 3-channel Holters, multi-lead `.pecg`, or EDF+), the dropdown automatically discovers and enumerates all available channels (e.g., `Lead I`, `Lead II`, `V1`–`V6`).
* Automatically selects **Lead II** (or **V5**) by default in accordance with AHA/ACC/HRS and FDA E14 clinical guidelines for optimal T-wave prominence and steepest repolarization downslope.
* Selecting any channel instantly switches the active signal, re-executes the morphological delineation pipeline, and dynamically recalculates R-peak fiducials, caliper positions, QTc metrics, and the Events Diary for that specific lead.

### 3.2 Draggable Digital Calipers
* **Gold Caliper Line (Q-Onset):** Click and drag along the time axis to adjust the start of ventricular depolarization.
* **Purple Caliper Line (T-End):** Click and drag to adjust the completion of ventricular repolarization.
* **Semi-Transparent Shaded Region:** Highlights the active measurement interval.
* **Live HUD Readout:** As calipers move, raw QT duration and rate-corrected $QT_c$ (Bazett and Fridericia) recalculate dynamically at 60 updates per second.

### 3.3 Clinical Events Diary
* Located in the right sidebar under the **`🚨 Events Diary`** tab.
* Lists all classified critical episodes (Severe QTc, Sinus Pauses, Ectopic Beats, Tachycardia/Bradycardia, MTWA runs).
* **Click-to-Seek:** Clicking any entry immediately pans the main viewport and positions the calipers directly on that beat.

### 3.4 Manual Beat Reclassification Dialog
* Double-clicking any beat marker/row in the beat table opens the **Physician Reclassification Dialog**.
* Select a new AAMI EC57 class (`N`, `V`, `S`, `F`, `Q`) and enter clinical notes.
* Overrides are logged with timestamps in the `AnnotationManager` audit history.

### 3.5 Exporting Anonymized Studies (`.pecg`)
* Click **`📤 Export Anonymized Study (.pecg)`** in the control panel.
* Enter patient demographics (Age, Sex, Race) and consultation notes.
* The system packages the raw waveforms (preserving all original recorded leads), physician caliper adjustments, and triage events into a single compressed `.pecg` container for colleague exchange.

### 3.6 Study & Patient Metadata Inspector
* Positioned as the **final tab** in the clinical inspector sidebar (`📋 Study & Patient`).
* Structured into two dedicated clinical parameter cards:
  * **Core Patient Demographics & Timing**: Displays universal anchor fields present across all clinical recordings: Patient ID / Subject Code, Biological Sex / Gender (essential for sex-specific QTc baselines), Age / Date of Birth, and Acquisition Date & Start Time.
  * **Clinical Context & Study Specifications**: Gracefully populates format-specific fields: Pacemaker Implant Status (`NO`, `YES`, `VVI`, `DDD`, `AAI`, `CRT`), Clinical Indication / Referral Reason, Race / Ethnicity, Patient Full Name (or automated HIPAA/GDPR De-identification notice for `.pecg` files), Source File Format & Container Version, Recording Hardware / Device Model, Lead Count & Sampling Frequency ($f_s$), Total Duration, and Embedded Consultation / Review Notes.

### 3.7 Workstation Settings & Color Scheme (Theme Dialog)
* Click **`⚙️ Settings`** in the top navigation bar to open the preferences modal dialog.
* **Interface Language Selector:** Allows instant live switching between English (`en`), Español (`es`), Français (`fr`), Deutsch (`de`), and Português (`pt`).
* **Visual Theme / Color Scheme Options:**
  * **Clinical Dark (Default):** Low-glare deep navy/slate palette (`#0f111a` background, `#1a1e2e` cards, cyan waveform `#38bdf8`) engineered for continuous multi-hour diagnostic reading and reduced optical fatigue.
  * **Clinical Light (Paper):** High-illumination clean medical paper palette (`#f1f5f9` / `#ffffff`) with deep ocean blue waveforms (`#0284c7`) and crimson R-peaks, optimized for well-lit hospital environments.
  * **High Contrast / Color Blind Safe:** Universally accessible scheme based on the Okabe-Ito / Paul Tol color palette (`#121212` background, sky blue waveform `#56b4e9`, high-visibility yellow R-peaks `#f0e442`, and distinct line styles: dashed orange Q-caliper vs. dash-dot blue T-caliper). Conforms to WCAG AAA contrast ratios and completely avoids red-green and blue-yellow perceptual confusion.
* All visual theme and language changes take effect immediately across all windows, tables, plots, calipers, and dialogs without reloading recordings.

### 3.8 Waveform Canvas Controls, Clinical Grid, Calipers & Zoom
* **Independent Canvas Color Scheme Dropdown:** Located directly on the canvas header toolbar (and in the Settings dialog), providing independent selection of the waveform display palette:
  * **Dark (Obsidian & Cyan):** Vibrant medical cyan lead plot (`#38bdf8`) on deep obsidian canvas (`#13151f`), with bright gold Q-caliper and neon fuchsia T-caliper.
  * **Clinical Paper (White & Midnight):** Deep ocean blue lead plot (`#0369a1`) on pure medical white canvas (`#ffffff`), with deep amber Q-caliper and vivid purple T-caliper.
  * **Classic ECG Paper (Pink Grid & Black):** Standard thermal paper pink background (`#fff1f2`) with red millimeter grid (`#fda4af`), jet black lead plot (`#0f172a`), electric royal blue Q-caliper, and flame orange T-caliper.
  * **High Contrast / Color Blind Safe:** Pure pitch black canvas (`#000000`), Okabe-Ito sky blue lead plot (`#56b4e9`), yellow diamond R-peaks (`#f0e442`), and contrasting dashed orange Q-caliper vs. dash-dot white/blue T-caliper (WCAG AAA compliant).
  * **Emerald Phosphor (Night Green):** Deep night emerald canvas (`#021a0f`) with neon green lead plot (`#22c55e`) and bright orange/coral calipers.
* **Segmented Grid Toggle Buttons (`⊞ Lines`, `⁚ Dots`, `⊘ Off`):**
  * **Lines (`⊞ Lines`):** Displays solid grid lines highlighting international clinical ECG calibration standards ($25\text{ mm/s}$ sweep speed, $10\text{ mm/mV}$ voltage gain).
  * **Dots (`⁚ Dots`):** Renders a matrix of dotted grid intersection coordinates for low-density orientation.
  * **Off (`⊘ Off`):** Completely clears grid lines for an unobstructed raw waveform view.
* **Conditional Clinical Scale Indicator Badge:**
  * **Grid-Linked Visibility:** The scale indicator badge (pinned to the top right corner of the plot and displayed in the header toolbar) is **only visible when a grid is enabled** (`Lines` or `Dots`). If the grid is toggled to `Off`, the scale label and value are automatically hidden.
  * **Dynamic Scaling Value:** Reflects the active clinical paper sweep speed and voltage gain (e.g. `📐 Scale: 25 mm/s | 10 mm/mV`, `📐 Scale: 50 mm/s | 20 mm/mV`).
* **Draggable Vertical Measurement Lines (Calipers & Cursors):**
  * **`📏 Calipers` Toggle Button:** Instantly toggles the visibility of the draggable vertical caliper lines and the bottom caliper measurement HUD strip.
  * **`⟲ Center` Button:** Re-centers the draggable vertical measurement lines within the currently visible viewport window (positioning Q-onset and T-end 10% on either side of center).
  * **`➕ Line` Button:** Dynamically drops an additional interactive draggable vertical cursor (`angle=90`, `movable=True`) with real-time timestamp tooltips to facilitate arbitrary interval measurements (PR interval, QRS duration, or RR cycle).
* **Clinical ECG Step-Wise Zoom Engine:**
  * **Standardized Paper Sweep Speeds (X-Axis):** Selectable between $12.5\text{ mm/s}$ (half-speed overview / $20\text{ s}$ standard span), $25.0\text{ mm/s}$ (clinical diagnostic standard / $10\text{ s}$ span), $50.0\text{ mm/s}$ (high-resolution repolarization inspection / $5\text{ s}$ span), and $100.0\text{ mm/s}$ (maximum temporal detail / $2.5\text{ s}$ span).
  * **Standardized Voltage Gains (Y-Axis):** Selectable between $2.5\text{ mm/mV}$ ($0.25\times$), $5.0\text{ mm/mV}$ ($0.5\times$ / half standard), $10.0\text{ mm/mV}$ ($1.0\times$ / clinical standard), and $20.0\text{ mm/mV}$ ($2.0\times$ / double standard).
  * **Quick Navigation Buttons:**
    * **`−` (Zoom Out):** Steps down to the preceding clinical speed or gain.
    * **`+` (Zoom In):** Steps up to the next clinical speed or gain.
    * **`1:1` (Reset):** Snaps directly to standard baseline clinical calibration ($25\text{ mm/s}$ and $10\text{ mm/mV}$).
    * **`⤢` (Fit):** Autoscales the view to fit the entire recording duration.
* **Clinical Axis Nomenclature & Timestamp Formatting:**
  * **Y-Axis:** Explicitly labeled **`Voltage (mV)`**.
  * **X-Axis:** Explicitly labeled **`Time (hh:mm:ss:xxx)`**, with tick labels formatted down to millisecond precision (`00:00:00:040`, `00:01:15:250`) via the custom `TimeAxisItem`.

---

## 4. Conditional Multi-Lead Gating & UI Adaptation

Repolaris incorporates an automated channel-sensing state machine based on `len(multi_lead_signals)` to adapt the UI dynamically between wearable patches and 12-lead Holters:

| Clinical Mode | Channel Quorum | QT Dispersion ($QT_d$) Behavior | Single-Lead Autonomic Suite Behavior |
| :--- | :--- | :--- | :--- |
| **Wearable Patch / Single-Lead** | $< 3$ Leads | **Disabled / Badged:** Spatial Dispersion tab is grayed out or hidden. Overview KPI card displays `N/A — Single Lead`. | **Fully Active:** HRV, HRT, TWA, and QT-RR Hysteresis remain fully operational on the active lead. |
| **Holter / 12-Lead Diagnostic** | $\ge 3$ Leads | **Fully Unlocked:** Enables the Spatial Dispersion tab, multi-channel butterfly overlay, and 12-lead polar radar plot. | **Fully Active:** Evaluated on the selected lead, with cross-lead validation where applicable. |

---

## 5. Advanced Electrocardiographic Diagnostic Docks

### 5.1 Spatial QT Dispersion View (Multi-Lead Only)
* **Multi-Lead Butterfly Overlay:** Displays all qualified leads superposed in semi-transparent traces, visually exposing the regional variation between global $Q_\text{onset}$ and the spread of $T_\text{end}$ offsets.
* **12-Lead Polar Radar Widget:** Maps lead locations against localized QT and $T_{pe}$ intervals, exposing the anatomical vector of maximal repolarization delay.
* **Dynamic Dispersion Timeline Ribbon:** Renders an interactive ribbon under the main time axis color-coded into Green ($QT_d < 50\text{ ms}$), Amber ($50\text{--}65\text{ ms}$), and Red ($> 65\text{ ms}$).

### 5.2 Microvolt T-Wave Alternans (TWA) Diagnostic Dock
* **ST-T Alternans Overlay:** Plots superposed median odd (blue) and even (orange) ST-T segments with shaded delta regions illustrating microvolt divergence.
* **Alternans Periodogram Waterfall:** Displays a 2D/3D spectral waterfall chart highlighting peak power at $f = 0.5\text{ cycles/beat}$ relative to the noise band.
* **Ambulatory Trend Strip:** Graphs continuous Modified Moving Average ($V_\text{MMA}$) against instantaneous Heart Rate.

### 5.3 Heart Rate Turbulence (HRT) Inspector
* **Ensemble Post-PVC Tachogram:** Plots normalized interval averages from $NN_{-2}$ to $NN_{20}$ following qualifying solitary PVCs, displaying the characteristic early acceleration dip and late decelerative recovery.
* **Turbulence Slope (TS) Regression Line:** Overlays the steepest positive 5-beat regression line in cyan.
* **Autonomic Risk Badge:** Highlights clinical categorization (Category 0 / 1 / 2) on the overview summary.

### 5.4 Comprehensive HRV Autonomic Dashboard
* **Poincaré Plot Dock:** Displays a 2D scatter plot of $NN_i$ vs. $NN_{i+1}$ with fitted major ($SD2$) and minor ($SD1$) ellipse axes.
* **Welch Spectral Distribution Widget:** Visualizes power spectral density across VLF (gray), LF (amber), and HF (blue) frequency bands, accompanied by a dynamic $LF/HF$ balance dial.
* **24-Hour Circadian Boxplots:** Renders hourly distributions of $SDNN$ and $RMSSD$ to monitor circadian autonomic shifts.

### 5.5 Multi-Beat QT-RR Hysteresis Dock
* **Phase-Plane Loop Collapse Plot:** Graphs raw $QT\text{ vs. }RR$ (displaying wide hysteresis loops during acceleration/deceleration) beside $QT\text{ vs. }RR_\text{eff}$ (displaying the loop collapsed into a tight single restitution curve).
* **Memory Decay Slider:** Interactive slider allowing clinicians to tune the exponential decay parameter ($\lambda$) or memory window ($N$) to observe real-time loop narrowing and residual variance reduction.
* **Stabilized Dual-Trace Timeline:** Overlays volatile raw $QT_c$ against smoothed hysteresis-corrected $QTc_\text{hyst}$.
