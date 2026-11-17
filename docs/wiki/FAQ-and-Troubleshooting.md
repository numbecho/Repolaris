# FAQ and Troubleshooting

Frequently asked questions, troubleshooting steps, and academic reference information for Repolaris.

---

## 1. Frequently Asked Questions

### What is the relationship between PyECG and Repolaris?
**Repolaris** is the modernized, rebranded evolution of PyECG (originally developed under DrC. Alexander Suárez León at Universidad de Oriente and KU Leuven STADIUS). Repolaris refactors the original research codebase into modular Python 3.12+ subpackages (`repolaris.io`, `repolaris.detection`, `repolaris.preprocessing`, `repolaris.api`), adds universal open clinical format readers (DICOM, HL7 aECG, SCP-ECG, ISHNE, Excorde 3C, EDF, WFDB), implements ANSI/AAMI EC57 and Patrick Hamilton (2002) OSEA beat classification, introduces the `.pecg` exchange container, supports out-of-core 24h–48h Holter streaming and printable 2-page PDF reports, and upgrades GUI rendering to 60fps via PyQtGraph.

### Can I run Repolaris headlessly on a Linux server without a display?
**Yes.** All signal processing routines, universal format loaders, streaming buffers, metric calculators, beat classifiers, and PDF report generators are decoupled from desktop GUI dependencies. You can install core dependencies without GUI packages (`pip install repolaris`) and run `repolaris analyze --stream --pdf` in automated Docker containers, CI pipelines, or Linux compute clusters.

### Which QTc formula should I use?
Repolaris computes five rate-correction formulations simultaneously:
* **Bazett (1920):** $QT_c = QT / \sqrt{RR}$ — Traditional clinical standard, but overcorrects during tachycardia ($> 85\text{ BPM}$) and undercorrects during bradycardia ($< 60\text{ BPM}$).
* **Fridericia (1932):** $QT_c = QT / \sqrt[3]{RR}$ — Preferred by the FDA (ICH E14 Thorough QT guidance) because it maintains physiological stability across elevated heart rates.
* **Framingham (1992):** $QT_c = QT + 0.154 \cdot (1 - RR)$ — Linear regression formulation derived from the Framingham Heart Study for broad population screening.
* **Hodges (1983):** $QT_c = QT + 1.75 \cdot (\text{HR} - 60)$ — Linear heart-rate adjustment widely used in hospital telemetry.
* **Individualized $QT_{c,\text{ind}}$ (Pueyo et al., 2004):** Evaluates the patient's own best-fitting biparametric QT-RR restitution curve (after multi-beat hysteresis compensation) at $RR = 1.0\text{ s}$ ($60\text{ BPM}$), eliminating population-formula rate distortion in long-term Holter recordings.

---

## 2. Troubleshooting

### Issue: "GUI dependencies not installed" error when launching `repolaris-gui`
**Solution:** Install GUI optional dependencies:
```bash
pip install -e ".[gui]"
```
Ensure `PyQt6` and `pyqtgraph` are installed in your active virtual environment.

### Issue: Corrupted or missing T-waves in noisy Holter recordings
**Solution:** Evaluate the Two-Stage Signal Quality Index (SQI) via `evaluate_lead_quality` (or multi-lead `rank_leads_two_stage`) before running delineation:
```python
from repolaris.detection.sqi import evaluate_lead_quality

sqi = evaluate_lead_quality(lead_signal, fs=500.0)
if not sqi["passed_absolute_gate"] or sqi["snr_db"] < 12.0 or sqi["psqi"] < 0.65:
    print(f"Warning: Lead quality ({sqi['verdict']}) insufficient for automated calipers.")
```

### Issue: Incompatible ISHNE `.ecg` or compressed SCP-ECG `.scp` files
**Solution:**
* For ISHNE `.ecg`, Repolaris automatically inspects the `ISHNE1.0` magic bytes and variable-length header block offset.
* For SCP-ECG `.scp`, Repolaris decodes uncompressed Section 0, 3, and 6 rhythm waveforms and explicitly checks for Section 2 (Huffman table compression) or Section 5 (reference beat subtraction), raising a descriptive `NotImplementedError` rather than silently producing corrupted waveforms.

---

## 3. Academic Attribution and Citations

If you use Repolaris in academic research, clinical studies, or software applications, please cite the foundational publication from Universidad de Oriente and KU Leuven:

> **Suárez-León, A. A., Varon, C., Willems, R., Van Huffel, S., & Vázquez-Seisdedos, C. R. (2018).**  
> *PyECG: A software tool for the analysis of the QT interval in the electrocardiogram.*  
> Revista Ingeniería Electrónica, Automática y Comunicaciones (RIELAC), 39(2), 54-69.  
> [https://rielac.cujae.edu.cu/index.php/rie/article/view/498](https://rielac.cujae.edu.cu/index.php/rie/article/view/498)

### BibTeX Citation:
```bibtex
@article{suarez2018herramienta,
  title = {PyECG: A software tool for the analysis of the QT interval in the electrocardiogram},
  author = {Suárez-León, Alexander A. and Varon, Carolina and Willems, Rik and Van Huffel, Sabine and Vázquez-Seisdedos, Carlos R.},
  journal = {Revista Ingeniería Electrónica, Automática y Comunicaciones (RIELAC)},
  volume = {39},
  number = {2},
  pages = {54--69},
  year = {2018},
  url = {https://rielac.cujae.edu.cu/index.php/rie/article/view/498}
}
```
