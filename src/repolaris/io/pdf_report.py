"""Clinical PDF Report Generator Module for Repolaris.

Generates multi-page printable clinical ECG and Holter reports using matplotlib PdfPages:
- Page 1: Patient Demographics & Study Metadata, Executive KPI Summary Table,
  Calibrated ECG Rhythm Strip (with R-peak, Q-onset, and T-end markers), and Clinical Events Diary.
- Page 2: Hourly Holter Arrhythmia Trend Histogram & Summary Table,
  Poincaré Heart Rate Variability Plot (NN_i vs NN_{i+1}), and QT-RR Restitution & Hysteresis Curve.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

matplotlib.use("Agg")



def _style_grid_table(
    tbl: Any,
    fontsize: float,
    scale_y: float,
    *,
    header_bg: str | None = None,
    label_cols: tuple[int, ...] = (),
    label_bg: str = "#f8fafc",
) -> None:
    """Applies consistent clinical typography and cell shading to a matplotlib Table."""
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(fontsize)
    tbl.scale(1.0, scale_y)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#cbd5e1")
        if header_bg and r == 0:
            cell.set_facecolor(header_bg)
            cell.set_text_props(weight="bold", color="#ffffff")
        elif c in label_cols:
            cell.set_facecolor(label_bg)
            cell.set_text_props(weight="bold", color="#0f172a")


def _render_page1_summary(
    analysis_results: dict[str, Any],
    meta: dict[str, Any],
    fs: float,
    lead_name: str,
    progress_callback: Callable[[float, str], None] | None = None,
) -> plt.Figure:
    """Renders Page 1: Demographics, Executive KPI Summary, Rhythm Strip, and Events Diary."""
    summary = analysis_results.get("summary", {})
    ectopic = analysis_results.get("ectopic_summary", {})
    sqi = analysis_results.get("sqi", {})
    qtrr = analysis_results.get("qtrr") or {}
    hrv = analysis_results.get("hrv") or {}
    af_report = analysis_results.get("af_report") or {}
    events = analysis_results.get("events", [])
    beats = analysis_results.get("beats", [])
    clean_signal = analysis_results.get("clean_signal", np.zeros(int(fs * 5), dtype=np.float32))
    r_peaks = analysis_results.get("r_peaks", np.array([], dtype=int))

    fig1 = plt.figure(figsize=(8.5, 11.0), dpi=150)
    fig1.patch.set_facecolor("#ffffff")

    ax_hdr = fig1.add_axes([0.06, 0.90, 0.88, 0.06])
    ax_hdr.axis("off")
    ax_hdr.text(
        0.0,
        0.65,
        "REPOLARIS CLINICAL ELECTROCARDIOGRAPHY & HOLTER REPORT",
        fontsize=13,
        fontweight="bold",
        color="#0f172a",
    )
    gen_ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    ax_hdr.text(
        0.0,
        0.15,
        f"Lead: {lead_name}  |  Sampling Rate: {fs:.0f} Hz  |  Generated: {gen_ts}  |  Engine: Repolaris v0.8.1",
        fontsize=8.5,
        color="#475569",
    )

    ax_meta = fig1.add_axes([0.06, 0.78, 0.88, 0.10])
    ax_meta.axis("off")
    meta_rows = [
        [
            "Patient ID",
            str(meta.get("patient_id", "ANONYMOUS")),
            "Age / Sex",
            f"{meta.get('age', 'N/A')} / {meta.get('gender', meta.get('sex', 'N/A'))}",
        ],
        [
            "Pacemaker",
            str(meta.get("pacemaker", "NO")),
            "Source Format",
            str(meta.get("format", "Standard ECG")),
        ],
        [
            "Indication",
            str(meta.get("indication", "Diagnostic ECG / Holter Evaluation"))[:45],
            "Total Beats",
            str(summary.get("total_beats", len(beats))),
        ],
    ]
    tbl_meta = ax_meta.table(
        cellText=meta_rows,
        colWidths=[0.18, 0.32, 0.18, 0.32],
        loc="center",
        cellLoc="left",
    )
    _style_grid_table(tbl_meta, 8.5, 1.35, label_cols=(0, 2), label_bg="#f1f5f9")

    ax_kpi = fig1.add_axes([0.06, 0.60, 0.88, 0.16])
    ax_kpi.axis("off")
    ax_kpi.set_title(
        "Executive Repolarization & Arrhythmia Summary",
        fontsize=10,
        fontweight="bold",
        loc="left",
        pad=6,
    )

    qtvi_val = analysis_results.get("qtvi")
    qtvi_str = f"{qtvi_val:.2f}" if qtvi_val is not None else "N/A"
    td_hrv = hrv.get("time_domain", {}) if isinstance(hrv, dict) else {}
    sdnn_str = f"{td_hrv.get('sdnn', 0.0):.1f} ms" if td_hrv else "N/A"
    rmssd_str = f"{td_hrv.get('rmssd', 0.0):.1f} ms" if td_hrv else "N/A"

    kpi_rows = [
        [
            "Mean Heart Rate",
            f"{summary.get('mean_hr_bpm', 0.0):.1f} BPM",
            "Mean Raw QT",
            f"{summary.get('mean_qt_ms', 0.0):.1f} ms",
        ],
        [
            "QTc Bazett / Fridericia",
            f"{summary.get('mean_qtc_bazett_ms', 0.0):.1f} / {summary.get('mean_qtc_fridericia_ms', 0.0):.1f} ms",
            "QTc Framingham / Hodges",
            f"{summary.get('mean_qtc_framingham_ms', 0.0):.1f} / {summary.get('mean_qtc_hodges_ms', 0.0):.1f} ms",
        ],
        [
            "Berger QTVI Score",
            qtvi_str,
            "QT-RR Slope (Model)",
            f"{qtrr.get('slope', 0.0):.4f} ({qtrr.get('model', 'N/A')})" if qtrr else "N/A",
        ],
        [
            "Ectopic Burden (PVC / PAC)",
            f"{ectopic.get('ectopic_burden_pct', 0.0):.2f}% ({ectopic.get('pvc_count', 0)} V, {ectopic.get('pac_count', 0)} S)",
            "AF / Flutter Burden",
            f"{af_report.get('af_burden_pct', 0.0):.2f}% ({af_report.get('num_episodes', 0)} episodes)",
        ],
        [
            "HRV (SDNN / RMSSD)",
            f"{sdnn_str} / {rmssd_str}",
            "Signal Quality (SQI)",
            f"{sqi.get('verdict', 'Good')} (SNR: {sqi.get('snr_db', 0.0):.1f} dB, pSQI: {sqi.get('psqi', 0.0):.2f})",
        ],
    ]
    tbl_kpi = ax_kpi.table(
        cellText=kpi_rows,
        colWidths=[0.24, 0.26, 0.24, 0.26],
        loc="center",
        cellLoc="left",
    )
    _style_grid_table(tbl_kpi, 8.0, 1.30, label_cols=(0, 2), label_bg="#f8fafc")

    if progress_callback:
        progress_callback(0.45, "Rendering calibrated ECG rhythm strip...")

    ax_strip = fig1.add_axes([0.06, 0.34, 0.88, 0.21])
    strip_samples = min(len(clean_signal), int(10.0 * fs))
    if strip_samples > 0:
        t_vec = np.arange(strip_samples) / fs
        sig_slice = np.asarray(clean_signal[:strip_samples], dtype=np.float32)
        ax_strip.plot(t_vec, sig_slice, color="#0284c7", linewidth=1.0, label=lead_name)

        r_in_win = [int(r) for r in r_peaks if int(r) < strip_samples]
        if r_in_win:
            ax_strip.scatter(
                np.array(r_in_win) / fs,
                sig_slice[r_in_win],
                color="#dc2626",
                s=18,
                zorder=4,
                label="R-Peaks",
            )

        for b in beats[:12]:
            q_s = b.get("q_onset_sample", -1)
            t_s = b.get("t_end_sample", -1)
            if 0 <= q_s < strip_samples:
                ax_strip.axvline(q_s / fs, color="#d97706", linestyle="--", linewidth=0.7, alpha=0.6)
            if 0 <= t_s < strip_samples:
                ax_strip.axvline(t_s / fs, color="#9333ea", linestyle=":", linewidth=0.7, alpha=0.6)
        ax_strip.legend(loc="upper right", fontsize=7.5)

    ax_strip.set_title(
        f"Calibrated Waveform Disclosure Strip — {lead_name} (25 mm/s, 10 mm/mV eq.)",
        fontsize=9.5,
        fontweight="bold",
        loc="left",
    )
    ax_strip.set_xlabel("Time (s)", fontsize=8.5)
    ax_strip.set_ylabel("Amplitude (mV)", fontsize=8.5)
    ax_strip.grid(True, which="both", color="#fecdd3", linestyle="-", linewidth=0.5, alpha=0.8)

    ax_ev = fig1.add_axes([0.06, 0.06, 0.88, 0.22])
    ax_ev.axis("off")
    ax_ev.set_title(
        f"Clinical Events Diary ({len(events)} Total Flagged Episodes)",
        fontsize=9.5,
        fontweight="bold",
        loc="left",
        pad=4,
    )

    ev_headers = ["Time (s)", "Event Type", "Severity", "Metric", "Clinical Description"]
    ev_rows = [
        [
            f"{ev.get('timestamp_sec', 0.0):.2f}s",
            str(ev.get("event_type", "EVENT")),
            str(ev.get("severity", "INFO")),
            f"{ev.get('metric_value', 0.0):.1f} {ev.get('unit', '')}",
            str(ev.get("description", ""))[:48],
        ]
        for ev in events[:8]
    ] or [["--", "NONE", "INFO", "--", "No abnormal clinical events detected."]]

    tbl_ev = ax_ev.table(
        cellText=ev_rows,
        colLabels=ev_headers,
        colWidths=[0.12, 0.20, 0.12, 0.14, 0.42],
        loc="upper center",
        cellLoc="left",
    )
    _style_grid_table(tbl_ev, 7.8, 1.25, header_bg="#1e293b")
    return fig1


def _render_page2_holter_and_dynamics(analysis_results: dict[str, Any]) -> plt.Figure:
    """Renders Page 2: Hourly Holter Trends Table, Poincaré Plot, and QT-RR Restitution Plot."""
    qtrr = analysis_results.get("qtrr") or {}
    trends = analysis_results.get("trends") or {}
    beats = analysis_results.get("beats", [])

    fig2 = plt.figure(figsize=(8.5, 11.0), dpi=150)
    fig2.patch.set_facecolor("#ffffff")

    ax_p2_hdr = fig2.add_axes([0.06, 0.92, 0.88, 0.04])
    ax_p2_hdr.axis("off")
    ax_p2_hdr.text(
        0.0,
        0.3,
        "HOLTER HOURLY ARRHYTHMIA TRENDS, AUTONOMIC POINCARÉ & QT-RR DYNAMICS",
        fontsize=11.5,
        fontweight="bold",
        color="#0f172a",
    )

    ax_tr_tbl = fig2.add_axes([0.06, 0.56, 0.88, 0.33])
    ax_tr_tbl.axis("off")
    ax_tr_tbl.set_title("Hourly Holter Distribution Table", fontsize=9.5, fontweight="bold", loc="left", pad=4)

    tr_headers = [
        "Hour",
        "Window (s)",
        "Beats",
        "Mean HR",
        "Min/Max HR",
        "PVCs",
        "PACs",
        "Couplets/VT",
        "Pauses",
        "AF (%)",
    ]
    hourly_bins = trends.get("hourly_bins", []) if isinstance(trends, dict) else []
    tr_rows = [
        [
            f"H{b.get('hour_index', 1)}",
            f"{b.get('start_time_sec', 0):.0f}-{b.get('end_time_sec', 0):.0f}",
            str(b.get("total_beats", 0)),
            f"{b.get('mean_hr_bpm', 0.0):.1f}",
            f"{b.get('min_hr_bpm', 0.0):.0f}/{b.get('max_hr_bpm', 0.0):.0f}",
            str(b.get("pvc_count", 0)),
            str(b.get("pac_count", 0)),
            f"{b.get('couplet_count', 0)}/{b.get('vt_run_count', 0)}",
            str(b.get("pause_count", 0)),
            f"{b.get('af_burden_pct', 0.0):.1f}%",
        ]
        for b in hourly_bins[:10]
    ] or [["H1", "0-0", "0", "0.0", "0/0", "0", "0", "0/0", "0", "0.0%"]]

    tbl_tr = ax_tr_tbl.table(
        cellText=tr_rows,
        colLabels=tr_headers,
        colWidths=[0.07, 0.15, 0.09, 0.10, 0.13, 0.08, 0.08, 0.12, 0.08, 0.10],
        loc="upper center",
        cellLoc="center",
    )
    _style_grid_table(tbl_tr, 7.5, 1.25, header_bg="#0f172a")

    ax_poin = fig2.add_axes([0.08, 0.10, 0.38, 0.38])
    rr_ms = [b["rr_sec"] * 1000.0 for b in beats if b.get("rr_sec", 0.0) > 0.2]
    if len(rr_ms) >= 3:
        rr_n = np.array(rr_ms[:-1])
        rr_n1 = np.array(rr_ms[1:])
        ax_poin.scatter(rr_n, rr_n1, color="#2563eb", s=12, alpha=0.65, label="NN Pairs")
        lims = [min(np.min(rr_n), np.min(rr_n1)) * 0.9, max(np.max(rr_n), np.max(rr_n1)) * 1.1]
        ax_poin.plot(lims, lims, color="#64748b", linestyle="--", linewidth=0.8, label="Identity")
    ax_poin.set_title("Poincaré Lorentz Plot (RR_n vs RR_{n+1})", fontsize=9.0, fontweight="bold")
    ax_poin.set_xlabel("RR_n (ms)", fontsize=8.0)
    ax_poin.set_ylabel("RR_{n+1} (ms)", fontsize=8.0)
    ax_poin.grid(True, color="#e2e8f0", linestyle="-", linewidth=0.6)

    ax_qtrr = fig2.add_axes([0.55, 0.10, 0.38, 0.38])
    if qtrr and "rr_raw_sec" in qtrr and "qt_ms" in qtrr:
        rr_raw = np.asarray(qtrr["rr_raw_sec"], dtype=np.float64)
        rr_eff = np.asarray(qtrr.get("rr_effective_sec", rr_raw), dtype=np.float64)
        qt_ms_arr = np.asarray(qtrr["qt_ms"], dtype=np.float64)
        valid_mask = rr_raw > 0.2
        if np.any(valid_mask):
            ax_qtrr.scatter(
                rr_raw[valid_mask],
                qt_ms_arr[valid_mask],
                color="#94a3b8",
                s=10,
                alpha=0.5,
                label="Raw (RR, QT)",
            )
            ax_qtrr.scatter(
                rr_eff[valid_mask],
                qt_ms_arr[valid_mask],
                color="#0284c7",
                s=14,
                alpha=0.8,
                label="Hysteresis (RR_eff, QT)",
            )
            ax_qtrr.legend(loc="best", fontsize=7.0)
    ax_qtrr.set_title(f"QT-RR Dynamics ({qtrr.get('label', 'Restitution')})", fontsize=9.0, fontweight="bold")
    ax_qtrr.set_xlabel("Cycle Length RR / RR_eff (s)", fontsize=8.0)
    ax_qtrr.set_ylabel("QT Interval (ms)", fontsize=8.0)
    ax_qtrr.grid(True, color="#e2e8f0", linestyle="-", linewidth=0.6)
    return fig2


def generate_clinical_pdf_report(
    filepath: str | Path | os.PathLike[str],
    analysis_results: dict[str, Any],
    patient_metadata: dict[str, Any] | None = None,
    fs: float = 500.0,
    lead_name: str = "Lead II",
    progress_callback: Callable[[float, str], None] | None = None,
) -> str:
    """Generates a multi-page printable clinical PDF report from analyze_ecg results."""
    out_path = Path(filepath)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta = patient_metadata or {}

    if progress_callback:
        progress_callback(0.15, "Preparing clinical report layout and metrics...")

    with PdfPages(str(out_path)) as pdf:
        fig1 = _render_page1_summary(analysis_results, meta, fs, lead_name, progress_callback=progress_callback)
        pdf.savefig(fig1)
        plt.close(fig1)

        if progress_callback:
            progress_callback(0.75, "Rendering Holter hourly trends, Poincaré, and QT-RR dynamics...")

        fig2 = _render_page2_holter_and_dynamics(analysis_results)
        pdf.savefig(fig2)
        plt.close(fig2)

    if progress_callback:
        progress_callback(1.00, f"Clinical PDF report saved to {out_path.name}.")

    return str(out_path.resolve())
