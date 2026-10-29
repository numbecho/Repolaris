"""Internationalization (i18n) translation engine for Repolaris.

Provides localized UI dictionaries for:
- en: English (Default)
- es: Español (Spanish)
- fr: Français (French)
- de: Deutsch (German)

All source code and internal algorithms remain in English; this module provides
human-facing localized labels, tooltips, dialogs, and diagnostic descriptions.
"""

from __future__ import annotations
from typing import Dict, Any

SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
}

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        # App Header & Actions
        "app_title": "Repolaris",
        "demo_filename": "Synthetic Rhythm Demo (72 BPM)",
        "channel_label": "Channel:",
        "language_label": "Language:",
        "btn_open": "📂 Open Recording",
        "btn_open_tooltip": "Open any clinical ECG file (.pecg, .ecg, .edf, .hea, .csv)",
        "btn_demo": "⚡ Demo Rhythm",
        "btn_demo_tooltip": "Generate realistic synthetic ECG rhythm (72 BPM)",
        "btn_export": "📤 Export Case (.pecg)",
        "btn_export_tooltip": "Export de-identified multi-channel study for colleague consultation",
        
        # Caliper Strip
        "calipers_title": "🔍 Digital Calipers:",
        "cal_raw_qt": "Raw QT:",
        "cal_bazett": "Bazett QTc:",
        "cal_fridericia": "Fridericia QTc:",
        "cal_tip": "💡 Drag calipers along the waveform to measure any cardiac cycle.",

        # Tabs
        "tab_overview": "📊 Overview",
        "tab_events": "🚨 Events Diary",
        "tab_beats": "📋 All Beats",

        # KPI Card Titles
        "kpi_hr_title": "Mean Heart Rate",
        "kpi_qtc_title": "Ventricular Repolarization (QTc)",
        "kpi_ectopic_title": "Ectopic Burden (PVC / PAC)",
        "kpi_sqi_title": "Lead Signal Quality (SQI)",

        # KPI Subtexts
        "hr_sub_normal": "Normal resting range (60-100 BPM)",
        "hr_sub_brady": "Bradycardia detected (<50 BPM)",
        "hr_sub_tachy": "Tachycardia detected (>100 BPM)",
        "qtc_sub_normal": "Normal ventricular repolarization (<450 ms)",
        "qtc_sub_borderline": "Warning: Borderline prolonged (>460 ms)",
        "qtc_sub_critical": "Critical: Severe prolongation (TdP risk)",
        "qtc_sub_short": "Warning: Abnormally short (<340 ms)",
        "ect_sub_normal": "100% normal sinus beats (0 ectopics)",
        "ect_sub_low": "Low burden ({pvc} PVC, {pac} PAC)",
        "ect_sub_high": "High burden ({pvc} PVCs, {pac} PACs)",
        "sqi_sub_clean": "Clean signal (SNR: {snr:.1f} dB)",
        "sqi_sub_mod": "Moderate noise (SNR: {snr:.1f} dB)",
        "sqi_sub_noisy": "Significant artifact (SNR: {snr:.1f} dB)",

        # Advanced Section
        "adv_group_title": "Repolarization Lability & Restitution",
        "adv_qtvi": "Berger QTVI: {val} (Normal: -1.6 to -1.0)",
        "adv_qtvi_na": "Berger QTVI: Not enough beats (<5)",
        "adv_qtrr": "QT-RR Restitution Slope: {val}",
        "adv_qtrr_na": "QT-RR Restitution Slope: N/A",
        "adv_total_cycles": "Total Analyzed Cycles: {count}",

        # Events Table Headers
        "hdr_time": "Time",
        "hdr_event": "Event",
        "hdr_value": "Value",
        "hdr_severity": "Severity",

        # Beat Table Headers
        "hdr_beat_num": "Beat #",
        "hdr_class": "Class",
        "hdr_qt": "QT (ms)",
        "hdr_qtc": "QTc (ms)",

        # Dialogs
        "override_title": "Override Beat #{num} Diagnosis",
        "override_prompt": "Current automated classification: {curr}\nSelect physician diagnostic override:",
        "export_dialog_title": "Export Anonymized Study",
        "patient_age_title": "Patient Age",
        "patient_age_prompt": "Enter patient age:",
        "patient_race_title": "Patient Race",
        "patient_race_prompt": "Enter race / ethnicity:",
        "notes_title": "Clinical Notes",
        "notes_prompt": "Enter consultation notes for colleague:",
        "export_success_title": "Export Successful",
        "export_success_msg": "De-identified study exported to:\n{path}",
        "error_title": "Error Loading File",
        "no_rec_title": "No Recording",
        "no_rec_msg": "Please load an ECG recording before exporting.",

        # AAMI Options
        "opt_n": "N (Normal Sinus)",
        "opt_v": "V (Premature Ventricular Contraction / PVC)",
        "opt_s": "S (Premature Atrial Contraction / PAC)",
        "opt_f": "F (Fusion Beat)",
        "opt_q": "Q (Unclassifiable / Artifact)",
    },
    
    "es": {
        # App Header & Actions
        "app_title": "Repolaris",
        "demo_filename": "Demostración de Ritmo Sintético (72 LPM)",
        "channel_label": "Canal:",
        "language_label": "Idioma:",
        "btn_open": "📂 Abrir Registro",
        "btn_open_tooltip": "Abrir archivo de ECG (.pecg, .ecg, .edf, .hea, .csv)",
        "btn_demo": "⚡ Ritmo Demo",
        "btn_demo_tooltip": "Generar ritmo ECG sintético realista (72 LPM)",
        "btn_export": "📤 Exportar Caso (.pecg)",
        "btn_export_tooltip": "Exportar estudio anonimizado multicanal para consulta colegiada",
        
        # Caliper Strip
        "calipers_title": "🔍 Calibradores Digitales:",
        "cal_raw_qt": "QT Medido:",
        "cal_bazett": "QTc Bazett:",
        "cal_fridericia": "QTc Fridericia:",
        "cal_tip": "💡 Arrastre los calibradores a lo largo de la señal para medir cualquier ciclo cardíaco.",

        # Tabs
        "tab_overview": "📊 Resumen Clínico",
        "tab_events": "🚨 Diario de Eventos",
        "tab_beats": "📋 Todos los Latidos",

        # KPI Card Titles
        "kpi_hr_title": "Frecuencia Cardíaca Media",
        "kpi_qtc_title": "Repolarización Ventricular (QTc)",
        "kpi_ectopic_title": "Carga Ectópica (CVP / CAP)",
        "kpi_sqi_title": "Calidad de Señal (SQI)",

        # KPI Subtexts
        "hr_sub_normal": "Rango sinusal en reposo (60-100 LPM)",
        "hr_sub_brady": "Bradicardia detectada (<50 LPM)",
        "hr_sub_tachy": "Taquicardia detectada (>100 LPM)",
        "qtc_sub_normal": "Repolarización ventricular normal (<450 ms)",
        "qtc_sub_borderline": "Advertencia: Límite prolongado (>460 ms)",
        "qtc_sub_critical": "Crítico: Prolongación severa (Riesgo de TdP)",
        "qtc_sub_short": "Advertencia: Anormalmente corto (<340 ms)",
        "ect_sub_normal": "100% latidos sinusales normales (0 ectópicos)",
        "ect_sub_low": "Baja carga ({pvc} CVP, {pac} CAP)",
        "ect_sub_high": "Alta carga ({pvc} CVP, {pac} CAP)",
        "sqi_sub_clean": "Señal limpia (SNR: {snr:.1f} dB)",
        "sqi_sub_mod": "Ruido moderado (SNR: {snr:.1f} dB)",
        "sqi_sub_noisy": "Artefacto significativo (SNR: {snr:.1f} dB)",

        # Advanced Section
        "adv_group_title": "Labilidad de Repolarización y Restitución",
        "adv_qtvi": "QTVI de Berger: {val} (Normal: -1.6 a -1.0)",
        "adv_qtvi_na": "QTVI de Berger: Insuficientes latidos (<5)",
        "adv_qtrr": "Pendiente de Restitución QT-RR: {val}",
        "adv_qtrr_na": "Pendiente de Restitución QT-RR: N/D",
        "adv_total_cycles": "Total de Ciclos Analizados: {count}",

        # Events Table Headers
        "hdr_time": "Tiempo",
        "hdr_event": "Evento",
        "hdr_value": "Valor",
        "hdr_severity": "Severidad",

        # Beat Table Headers
        "hdr_beat_num": "Latido #",
        "hdr_class": "Clase",
        "hdr_qt": "QT (ms)",
        "hdr_qtc": "QTc (ms)",

        # Dialogs
        "override_title": "Modificar Diagnóstico del Latido #{num}",
        "override_prompt": "Clasificación automática actual: {curr}\nSeleccione el diagnóstico médico definitivo:",
        "export_dialog_title": "Exportar Estudio Anonimizado",
        "patient_age_title": "Edad del Paciente",
        "patient_age_prompt": "Ingrese la edad del paciente:",
        "patient_race_title": "Etnia / Raza",
        "patient_race_prompt": "Ingrese la etnia o procedencia:",
        "notes_title": "Notas Clínicas",
        "notes_prompt": "Ingrese notas u observaciones para interconsulta:",
        "export_success_title": "Exportación Exitosa",
        "export_success_msg": "Estudio anonimizado exportado a:\n{path}",
        "error_title": "Error al Cargar Archivo",
        "no_rec_title": "Sin Registro",
        "no_rec_msg": "Por favor cargue un registro de ECG antes de exportar.",

        # AAMI Options
        "opt_n": "N (Sinusal Normal)",
        "opt_v": "V (Contracción Ventricular Prematura / CVP)",
        "opt_s": "S (Contracción Auricular Prematura / CAP)",
        "opt_f": "F (Latido de Fusión)",
        "opt_q": "Q (No clasificable / Artefacto)",
    },

    "fr": {
        # App Header & Actions
        "app_title": "Repolaris",
        "demo_filename": "Démo de Rythme Synthétique (72 BPM)",
        "channel_label": "Canal:",
        "language_label": "Langue:",
        "btn_open": "📂 Ouvrir Enregistrement",
        "btn_open_tooltip": "Ouvrir un fichier ECG (.pecg, .ecg, .edf, .hea, .csv)",
        "btn_demo": "⚡ Rythme Démo",
        "btn_demo_tooltip": "Générer un tracé ECG synthétique réaliste (72 BPM)",
        "btn_export": "📤 Exporter Cas (.pecg)",
        "btn_export_tooltip": "Exporter l'étude anonymisée multicanaux pour consultation collégiale",
        
        # Caliper Strip
        "calipers_title": "🔍 Pied à Coulisse Digital:",
        "cal_raw_qt": "QT Brut:",
        "cal_bazett": "QTc Bazett:",
        "cal_fridericia": "QTc Fridericia:",
        "cal_tip": "💡 Faites glisser les curseurs pour mesurer n'importe quel cycle cardiaque.",

        # Tabs
        "tab_overview": "📊 Vue d'Ensemble",
        "tab_events": "🚨 Journal des Événements",
        "tab_beats": "📋 Tous les Battements",

        # KPI Card Titles
        "kpi_hr_title": "Fréquence Cardiaque Moyenne",
        "kpi_qtc_title": "Repolarisation Ventriculaire (QTc)",
        "kpi_ectopic_title": "Charge Ectopique (ESV / ESSV)",
        "kpi_sqi_title": "Qualité du Signal (SQI)",

        # KPI Subtexts
        "hr_sub_normal": "Rythme sinusal au repos (60-100 BPM)",
        "hr_sub_brady": "Bradycardie détectée (<50 BPM)",
        "hr_sub_tachy": "Tachycardie détectée (>100 BPM)",
        "qtc_sub_normal": "Repolarisation ventriculaire normale (<450 ms)",
        "qtc_sub_borderline": "Avertissement: Limite allongée (>460 ms)",
        "qtc_sub_critical": "Critique: Allongement sévère (Risque de TdP)",
        "qtc_sub_short": "Avertissement: Anormalement court (<340 ms)",
        "ect_sub_normal": "100% battements sinusaux normaux (0 ectopie)",
        "ect_sub_low": "Faible charge ({pvc} ESV, {pac} ESSV)",
        "ect_sub_high": "Charge élevée ({pvc} ESV, {pac} ESSV)",
        "sqi_sub_clean": "Signal clair (SNR: {snr:.1f} dB)",
        "sqi_sub_mod": "Bruit modéré (SNR: {snr:.1f} dB)",
        "sqi_sub_noisy": "Artefact significatif (SNR: {snr:.1f} dB)",

        # Advanced Section
        "adv_group_title": "Labilité de Repolarisation et Restitution",
        "adv_qtvi": "QTVI de Berger: {val} (Normal: -1.6 à -1.0)",
        "adv_qtvi_na": "QTVI de Berger: Pas assez de battements (<5)",
        "adv_qtrr": "Pente de Restitution QT-RR: {val}",
        "adv_qtrr_na": "Pente de Restitution QT-RR: N/D",
        "adv_total_cycles": "Total des Cycles Analysés: {count}",

        # Events Table Headers
        "hdr_time": "Temps",
        "hdr_event": "Événement",
        "hdr_value": "Valeur",
        "hdr_severity": "Gravité",

        # Beat Table Headers
        "hdr_beat_num": "Battement #",
        "hdr_class": "Classe",
        "hdr_qt": "QT (ms)",
        "hdr_qtc": "QTc (ms)",

        # Dialogs
        "override_title": "Modifier le Diagnostic du Battement #{num}",
        "override_prompt": "Classification automatique actuelle: {curr}\nSélectionnez le diagnostic médical:",
        "export_dialog_title": "Exporter l'Étude Anonymisée",
        "patient_age_title": "Âge du Patient",
        "patient_age_prompt": "Entrez l'âge du patient:",
        "patient_race_title": "Origine / Ethnicité",
        "patient_race_prompt": "Entrez l'origine ou l'ethnicité:",
        "notes_title": "Notes Cliniques",
        "notes_prompt": "Entrez des remarques cliniques pour le confrère:",
        "export_success_title": "Exportation Réussie",
        "export_success_msg": "Étude anonymisée exportée vers:\n{path}",
        "error_title": "Erreur de Chargement",
        "no_rec_title": "Aucun Enregistrement",
        "no_rec_msg": "Veuillez charger un enregistrement ECG avant d'exporter.",

        # AAMI Options
        "opt_n": "N (Sinusal Normal)",
        "opt_v": "V (Extrasystole Ventriculaire / ESV)",
        "opt_s": "S (Extrasystole Supraventriculaire / ESSV)",
        "opt_f": "F (Battement de Fusion)",
        "opt_q": "Q (Inclassable / Artefact)",
    },

    "de": {
        # App Header & Actions
        "app_title": "Repolaris",
        "demo_filename": "Synthetisches Rhythmus-Demo (72 BPM)",
        "channel_label": "Kanal:",
        "language_label": "Sprache:",
        "btn_open": "📂 EKG Öffnen",
        "btn_open_tooltip": "EKG-Datei öffnen (.pecg, .ecg, .edf, .hea, .csv)",
        "btn_demo": "⚡ Demo-Rhythmus",
        "btn_demo_tooltip": "Realistischen synthetischen EKG-Rhythmus erzeugen (72 BPM)",
        "btn_export": "📤 Fall Exportieren (.pecg)",
        "btn_export_tooltip": "Anonymisierte Mehrkanalstudie für Kollegen exportieren",
        
        # Caliper Strip
        "calipers_title": "🔍 Digitale Messzange:",
        "cal_raw_qt": "Gemessenes QT:",
        "cal_bazett": "Bazett QTc:",
        "cal_fridericia": "Fridericia QTc:",
        "cal_tip": "💡 Verschieben Sie die Messlinien, um jeden Herzzyklus zu vermessen.",

        # Tabs
        "tab_overview": "📊 Übersicht",
        "tab_events": "🚨 Ereignistagebuch",
        "tab_beats": "📋 Alle Schläge",

        # KPI Card Titles
        "kpi_hr_title": "Mittlere Herzfrequenz",
        "kpi_qtc_title": "Ventrikuläre Repolarisation (QTc)",
        "kpi_ectopic_title": "Ektopie-Belastung (VES / SVES)",
        "kpi_sqi_title": "Signalqualität (SQI)",

        # KPI Subtexts
        "hr_sub_normal": "Normaler Sinusrhythmus in Ruhe (60-100 BPM)",
        "hr_sub_brady": "Bradykardie erkannt (<50 BPM)",
        "hr_sub_tachy": "Tachykardie erkannt (>100 BPM)",
        "qtc_sub_normal": "Normale ventrikuläre Repolarisation (<450 ms)",
        "qtc_sub_borderline": "Warnung: Grenzwertig verlängert (>460 ms)",
        "qtc_sub_critical": "Kritisch: Schwere Verlängerung (TdP-Risiko)",
        "qtc_sub_short": "Warnung: Abnorm verkürzt (<340 ms)",
        "ect_sub_normal": "100% normale Sinusschläge (0 Ektopien)",
        "ect_sub_low": "Niedrige Belastung ({pvc} VES, {pac} SVES)",
        "ect_sub_high": "Hohe Belastung ({pvc} VES, {pac} SVES)",
        "sqi_sub_clean": "Sauberes Signal (SNR: {snr:.1f} dB)",
        "sqi_sub_mod": "Mäßiges Rauschen (SNR: {snr:.1f} dB)",
        "sqi_sub_noisy": "Erhebliches Artefakt (SNR: {snr:.1f} dB)",

        # Advanced Section
        "adv_group_title": "Repolarisations-Labilität & Restitution",
        "adv_qtvi": "Berger QTVI: {val} (Normal: -1.6 bis -1.0)",
        "adv_qtvi_na": "Berger QTVI: Zu wenige Schläge (<5)",
        "adv_qtrr": "QT-RR Restitutions-Steigung: {val}",
        "adv_qtrr_na": "QT-RR Restitutions-Steigung: N/A",
        "adv_total_cycles": "Analysierte Zyklen Gesamt: {count}",

        # Events Table Headers
        "hdr_time": "Zeit",
        "hdr_event": "Ereignis",
        "hdr_value": "Wert",
        "hdr_severity": "Schweregrad",

        # Beat Table Headers
        "hdr_beat_num": "Schlag #",
        "hdr_class": "Klasse",
        "hdr_qt": "QT (ms)",
        "hdr_qtc": "QTc (ms)",

        # Dialogs
        "override_title": "Diagnose für Schlag #{num} anpassen",
        "override_prompt": "Aktuelle automatische Klassifikation: {curr}\nÄrztliche Diagnose auswählen:",
        "export_dialog_title": "Anonymisierte Studie Exportieren",
        "patient_age_title": "Patientenalter",
        "patient_age_prompt": "Patientenalter eingeben:",
        "patient_race_title": "Ethnizität / Herkunft",
        "patient_race_prompt": "Ethnizität oder Herkunft eingeben:",
        "notes_title": "Klinische Notizen",
        "notes_prompt": "Konsultationsnotizen für Kollegen eingeben:",
        "export_success_title": "Export Erfolgreich",
        "export_success_msg": "Anonymisierte Studie exportiert nach:\n{path}",
        "error_title": "Fehler beim Laden der Datei",
        "no_rec_title": "Kein EKG Geladen",
        "no_rec_msg": "Bitte vor dem Export eine EKG-Aufzeichnung laden.",

        # AAMI Options
        "opt_n": "N (Normaler Sinus)",
        "opt_v": "V (Ventrikuläre Extrasystole / VES)",
        "opt_s": "S (Supraventrikuläre Extrasystole / SVES)",
        "opt_f": "F (Fusionsschlag)",
        "opt_q": "Q (Nicht klassifizierbar / Artefakt)",
    }
}


class I18nManager:
    """Manages active language state and translation lookups."""

    def __init__(self, default_lang: str = "en") -> None:
        self.current_lang = default_lang if default_lang in SUPPORTED_LANGUAGES else "en"

    def set_language(self, lang_code: str) -> bool:
        """Switches current language. Returns True if supported."""
        if lang_code in SUPPORTED_LANGUAGES:
            self.current_lang = lang_code
            return True
        return False

    def get(self, key: str, **kwargs: Any) -> str:
        """Looks up translated string for current language with fallback to English."""
        lang_dict = TRANSLATIONS.get(self.current_lang, TRANSLATIONS["en"])
        template = lang_dict.get(key, TRANSLATIONS["en"].get(key, key))
        if kwargs:
            try:
                return template.format(**kwargs)
            except Exception:
                return template
        return template


# Singleton instance
_i18n = I18nManager("en")


def tr(key: str, **kwargs: Any) -> str:
    """Global translation helper function."""
    return _i18n.get(key, **kwargs)


def set_locale(lang_code: str) -> bool:
    """Sets active application locale."""
    return _i18n.set_language(lang_code)


def get_current_locale() -> str:
    """Returns active language code."""
    return _i18n.current_lang


def get_supported_locales() -> Dict[str, str]:
    """Returns dictionary of supported language codes and display names."""
    return SUPPORTED_LANGUAGES
