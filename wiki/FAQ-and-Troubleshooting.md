# FAQ and Troubleshooting

Frequently asked questions, troubleshooting steps, and academic reference information for Repolaris.

---

## 1. Frequently Asked Questions

### What is the relationship between PyECG and Repolaris?
**Repolaris** is the modernized, rebranded evolution of PyECG (originally developed under DrC. Alexander Suárez León at Universidad de Oriente and KU Leuven). Repolaris refactors the monolithic PyECG codebase into modular packages, adds AAMI EC57 beat classification, introduces the `.pecg` exchange container, and upgrades GUI rendering to 60fps via PyQtGraph. A full backward compatibility shim (`import pyecg`) is maintained.

### Can I run Repolaris headlessly on a Linux server without a display?
**Yes.** All signal processing routines, universal format loaders, metric calculators, and beat classifiers are fully decoupled from GUI dependencies. You can install core dependencies without GUI packages (`pip install repolaris`) and run analysis pipelines in automated Docker containers or compute clusters.

### Which QTc formula should I use?
* **Clinical Holter Standard:** Bazett is most familiar to clinicians, but overcorrects during tachycardia.
* **Clinical Trials & Pharmacology (FDA E14):** Fridericia is preferred by regulatory bodies because it maintains physiological stability across heart rates from 50 to 120 bpm.
* **Broad Rate Variations:** Framingham provides linear stability across wide rate distributions.

---

## 2. Troubleshooting

### Issue: "GUI dependencies not installed" error when launching `repolaris-gui`
**Solution:** Install GUI optional dependencies:
```bash
pip install "repolaris[gui]"
```
Ensure PyQt6 and PyQtGraph are installed.

### Issue: Corrupted or missing T-waves in noisy Holter recordings
**Solution:** Check the Signal Quality Index (SQI) before running delineation:
```python
from repolaris.detection.sqi import compute_sqi

sqi = compute_sqi(lead_signal, fs=500.0)
if sqi["snr_db"] < 12.0 or sqi["p_sqi"] < 0.60:
    print("Warning: Lead signal quality insufficient for automated calipers.")
```

### Issue: Incompatible ISHNE `.ecg` header
**Solution:** Ensure the Holter file begins with the magic bytes `ISHNE1.0`. Some legacy commercial software exports truncated 512-byte headers; Repolaris automatically detects and handles variable block offsets.

---

## 3. Academic Attribution and Citations

If you use Repolaris in academic research, clinical studies, or software applications, please cite the primary baseline publication:

> **Suárez-León, A. A., Varon, C., Willems, R., Van Huffel, S., & Vázquez-Seisdedos, C. R. (2018).**  
> *Herramienta para el análisis de la repolarización ventricular en el electrocardiograma.*  
> Revista Ingeniería Electrónica, Automática y Comunicaciones (RIELAC), 39(1), 1-13.  
> [Article Link](https://rielac.cujae.edu.cu/index.php/rie/article/view/498)

### BibTeX Citation:
```bibtex
@article{suarez2018herramienta,
  title={Herramienta para el an{\'a}lisis de la repolarizaci{\'o}n ventricular en el electrocardiograma},
  author={Su{\'a}rez-Le{\'o}n, Alexander A and Varon, Carolina and Willems, Rik and Van Huffel, Sabine and V{\'a}zquez-Seisdedos, Carlos R},
  journal={Revista Ingenier{\'i}a Electr{\'o}nica, Autom{\'a}tica y Comunicaciones (RIELAC)},
  volume={39},
  number={1},
  pages={1--13},
  year={2018}
}
```
