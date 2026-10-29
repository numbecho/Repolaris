# Workstation GUI Guide

The Repolaris workstation GUI (`repolaris-gui`) provides a 60fps hardware-accelerated environment for interactive Holter analysis, caliper calibration, and clinical case review.

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
| Repolaris - Interactive QT Caliper Workstation (PyQtGraph)                       |
+----------------------------------------------------------------------------------+
| [Main Waveform Canvas - 60fps PyQtGraph]              | [Sidebar Controls]       |
|                                                       | ------------------------ |
|   /\          /\          /\          /\              | [Open File] [Demo Rhyth] |
|  /  \  _/\   /  \  _/\   /  \  _/\   /  \  _/\        | Active Lead: [Lead II v] |
| /    \/   \_/    \/   \_/    \/   \_/    \/   \_      | ------------------------ |
|   |         |                                         | Live Caliper Readout:    |
|   |<-Region>|                                         |  QT: 412.0 ms            |
| (Gold)    (Purple)                                    |  Bazett QTc: 438.2 ms    |
| Q-Onset   T-End                                       |  Fridericia: 429.1 ms    |
|                                                       | ------------------------ |
|                                                       | Navigation Tabs:         |
|                                                       | [Events Diary] [Beats]   |
+----------------------------------------------------------------------------------+
```

---

## 3. Key Interactive Features

### 3.1 Dynamic Multi-Lead Selection Dropdown
* Located in the **Study Controls** panel directly under the Open/Reload buttons.
* When opening multi-channel recordings (e.g., 12-lead ISHNE `.ecg`, 3-channel Holters, multi-lead `.pecg``.mat`), the dropdown automatically discovers and enumerates all available channels (e.g., `Lead I`, `Lead II`, `V1`–`V6`).
* Automatically selects **Lead II** (or **V5**) by default in accordance with AHA/ACC/HRS and FDA E14 clinical guidelines for optimal T-wave prominence and steepest repolarization downslope.
* Selecting any channel instantly switches the active signal, re-executes the morphological delineation pipeline, and dynamically recalculates R-peak fiducials, caliper positions, QTc metrics, and the Events Diary for that specific lead.

### 3.2 Draggable Digital Calipers
* **Gold Caliper Line (Q-Onset):** Click and drag along the time axis to adjust the start of ventricular depolarization.
* **Purple Caliper Line (T-End):** Click and drag to adjust the completion of ventricular repolarization.
* **Semi-Transparent Shaded Region:** Highlights the active measurement interval.
* **Live HUD Readout:** As calipers move, raw QT duration and rate-corrected $QT_c$ (Bazett and Fridericia) recalculate dynamically at 60 updates per second.

### 3.3 Clinical Events Diary
* Located in the right sidebar under the **`🚨 Events Diary`** tab.
* Lists all classified critical episodes (Severe QTc, Sinus Pauses, Ectopic Beats, Tachycardia/Bradycardia).
* **Click-to-Seek:** Clicking any entry immediately pans the main viewport and positions the calipers directly on that beat.

### 3.4 Manual Beat Reclassification Dialog
* Double-clicking any beat markerrow in the beat table opens the **Physician Reclassification Dialog**.
* Select a new AAMI EC57 class (`N`, `V`, `S`, `F`, `Q`) and enter clinical notes.
* Overrides are logged with timestamps in the `AnnotationManager` audit history.

### 3.5 Exporting Anonymized Studies (`.pecg`)
* Click **`📤 Export Anonymized Study (.pecg)`** in the control panel.
* Enter patient demographics (Age, Sex, Race) and consultation notes.
* The system packages the raw waveforms (preserving all original recorded leads), physician caliper adjustments, and triage events into a single compressed `.pecg` container for colleague exchange.
