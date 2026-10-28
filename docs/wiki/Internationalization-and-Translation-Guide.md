# Internationalization (i18n) and Translation Guide

Welcome to the **Repolaris Internationalization (i18n) Guide**. This document outlines how localized translations are structured and provides step-by-step instructions for contributors who want to add a new language to the desktop GUI and the wiki documentation.

---

## 1. Core Architectural Policy

To maintain long-term maintainability across a global biomedical engineering community, Repolaris adheres to a strict two-tier localization policy:

1. **Source Code & Algorithmic Core (Strictly English):**
   * All Python variable names, class names, function signatures, internal logic, algorithmic comments, and docstrings **must remain in English**.
   * Scientific formulas, math models (e.g., Berger QTVI, Bazett/Fridericia, Pan-Tompkins), and internal database schemas remain untranslated.
2. **User Interface (UI) & Documentation (Fully Internationalized):**
   * All patient-facing and clinician-facing visual elements (GUI buttons, KPI cards, table headers, diagnostic override dialogs, and event alert descriptions) are externalized into localized translation dictionaries.
   * Documentation wiki pages can be translated into any language.

---

## 2. Supported Languages

| Language Code | Language Name | Native Name | Status |
| :--- | :--- | :--- | :--- |
| **`en`** | English | English | Default / Baseline |
| **`es`** | Spanish | Español | Complete (100%) |
| **`fr`** | French | Français | Complete (100%) |
| **`de`** | German | Deutsch | Complete (100%) |

---

## 3. How the UI Translation Engine Works

The internationalization engine resides in `src/repolaris/i18n.py`:

```
src/repolaris/
├── i18n.py                   # Central translation dictionary and I18nManager
├── app.py                    # GUI workstation importing tr(), set_locale()
```

### Key Components

* **`SUPPORTED_LANGUAGES`:** Dictionary mapping ISO 639-1 language codes (e.g., `"es"`, `"fr"`, `"de"`) to their native display names.
* **`TRANSLATIONS`:** Nested dictionary mapping language codes to key-value string pairs.
* **`tr(key, **kwargs)`:** Helper function that looks up the translated string for the currently active locale. If a key is missing in the chosen language, it automatically falls back to the English baseline.

```python
from repolaris.i18n import tr, set_locale

# Switch active language
set_locale("es")

# Retrieve localized string
label = tr("btn_open")  # Returns "📂 Abrir Registro"

# Formatting with dynamic arguments
msg = tr("adv_total_cycles", count=142)  # Returns "Total de Ciclos Analizados: 142"
```

---

## 4. How to Add a New Language to the UI (Step-by-Step)

Want to add Italian (`it`), Portuguese (`pt`), Japanese (`ja`), or another language? Follow these four steps:

### Step 1: Register Language Code in `src/repolaris/i18n.py`

Open `src/repolaris/i18n.py` and add your language to `SUPPORTED_LANGUAGES`:

```python
SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",      # <-- Add your new language
}
```

### Step 2: Add the Translation Dictionary

Copy the `TRANSLATIONS["en"]` dictionary block and paste it with your language code (e.g., `"it"`). Translate all values while **preserving exact dictionary keys and `{placeholder}` tokens**:

```python
TRANSLATIONS["it"] = {
    "app_title": "Repolaris",
    "demo_filename": "Demo del Ritmo Sintetico (72 BPM)",
    "channel_label": "Canale:",
    "language_label": "Lingua:",
    "btn_open": "📂 Apri Registrazione",
    "btn_open_tooltip": "Apri qualsiasi file ECG (.pecg, .ecg, .edf, .hea, .mat, .csv)",
    "btn_demo": "⚡ Ritmo Demo",
    "btn_demo_tooltip": "Genera ritmo ECG sintetico realistico (72 BPM)",
    "btn_export": "📤 Esporta Caso (.pecg)",
    # ... translate remaining keys ...
}
```

### Step 3: Register in GUI Language Dropdown (`src/repolaris/app.py`)

In `src/repolaris/app.py`, add your code to `self.lang_codes`:

```python
self.lang_codes = ["en", "es", "fr", "de", "it"]
```

### Step 4: Verify with Unit Tests

Run the automated test suite. The `test_dictionary_key_parity` test automatically verifies that your new language has zero missing keys:

```bash
python3 -m unittest tests/test_i18n.py
```

If any key is missing, the test output will show the exact missing keys so you can fill them in!

---

## 5. How to Translate the Wiki Documentation

To translate wiki pages:

1. Duplicate the target markdown file with the language code suffix (e.g., `Getting-Started.es.md`, `Architecture-Overview.fr.md`, or inside `wiki/i18n/<lang>/`).
2. Translate the narrative text while keeping code snippets, CLI commands, and LaTeX math formulas (`$QT_c$`, `QTVI`) intact.
3. Link the translation in `_Sidebar.md` under a **Languages / Idiomas** section.

---

## 6. Medical Terminology Guidelines

When translating clinical terms, adhere to standard electrophysiology conventions:

| English Term | Spanish (es) | French (fr) | German (de) |
| :--- | :--- | :--- | :--- |
| **Normal Sinus Rhythm** | Ritmo Sinusal Normal | Rythme Sinusal Normal | Normaler Sinusrhythmus |
| **Premature Ventricular Contraction (PVC)** | Contracción Ventricular Prematura (CVP) | Extrasystole Ventriculaire (ESV) | Ventrikuläre Extrasystole (VES) |
| **Premature Atrial Contraction (PAC)** | Contracción Auricular Prematura (CAP) | Extrasystole Auriculaire (ESA) | Supraventrikuläre Extrasystole (SVES) |
| **Ventricular Repolarization** | Repolarización Ventricular | Repolarisation Ventriculaire | Ventrikuläre Repolarisation |
| **Rate-Corrected QT (QTc)** | QT Corregido (QTc) | QT Corrigé (QTc) | Frequenzkorrigiertes QT (QTc) |
| **Signal-to-Noise Ratio (SNR)** | Relación Señal-Ruido (SNR) | Rapport Signal sur Bruit (RSB) | Signal-Rausch-Verhältnis (SNR) |
| **Digital Calipers** | Calibradores Digitales | Pied à coulisse digital | Digitale Messzange |
