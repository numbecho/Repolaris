"""Headless Multi-File Cohort Batch Runner (`CSV` and `JSON` Clinical Trial Export).

Processes a directory of ECG/Holter files across all supported open and clinical formats
(.pecg, .ecg, .ishne, .edf, .hea, .e3c, .dcm, .xml, .scp, .npy, .csv) with zero database
dependencies, automatically streaming large recordings via `analyze_ecg_stream()` and
isolating per-file errors into a flat, trial-ready biomarker matrix.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from repolaris.detection.pipeline import analyze_ecg, analyze_ecg_stream
from repolaris.io.ecg_loader import _EXT_FORMAT_MAP, load_ecg_dataset

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(_EXT_FORMAT_MAP.keys())

BATCH_BIOMARKER_COLUMNS: tuple[str, ...] = (
    "file_name",
    "file_path",
    "status",
    "error_message",
    "execution_mode",
    "sampling_rate_hz",
    "total_beats",
    "mean_hr_bpm",
    "mean_qt_ms",
    "mean_qtc_bazett_ms",
    "mean_qtc_fridericia_ms",
    "mean_qtc_framingham_ms",
    "mean_qtc_hodges_ms",
    "mean_j_tpeak_ms",
    "mean_j_tpeakc_ms",
    "mean_tpe_ms",
    "mean_tpe_qt_ratio",
    "stv_qt_ms",
    "ltv_qt_ms",
    "tdp_risk_category",
    "t_wave_asymmetry_ratio",
    "t_wave_flatness_score",
    "t_wave_notched_pct",
    "t_wave_morphology_verdict",
    "svd_t2_t1_ratio",
    "svd_tcrt",
    "qtvi",
    "qtrr_slope_beta",
    "hysteresis_lambda_star",
    "hysteresis_t90_sec",
    "hrv_sdnn_ms",
    "hrv_rmssd_ms",
    "hrt_category",
    "peak_mma_twa_uv",
    "prsa_dc_ms",
    "prsa_ac_ms",
    "prsa_risk_category",
    "st_mean_level_uv",
    "st_ischemic_episodes",
    "st_verdict",
    "pr_mean_ms",
    "av_block_verdict",
    "edr_respiratory_rate_brpm",
    "edr_apnea_screening",
    "circadian_hr_dip_pct",
    "circadian_delta_qtcf_ms",
    "circadian_verdict",
    "af_burden_pct",
    "pvc_count",
    "pac_count",
    "sqi_verdict",
)


def _extract_batch_row(
    file_path: Path,
    res: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    """Extracts the 51 standardized clinical & repolarization columns from an analysis result dict."""
    summ = res.get("summary") or {}
    qtv = res.get("stv_qt") or res.get("qt_variability") or {}
    tmorph = res.get("t_morphology") or res.get("t_wave_morphology") or {}
    svd = tmorph.get("svd_3d") or {}
    qtvi_raw = res.get("qtvi")
    qtvi_val = float(qtvi_raw.get("qtvi", 0.0)) if isinstance(qtvi_raw, dict) else float(qtvi_raw or 0.0)
    qtrr_d = res.get("qtrr") or {}
    hyst_d = res.get("hysteresis") or {}
    hrv_d = (res.get("hrv") or {}).get("time_domain") or (res.get("hrv") or {})
    hrt_d = res.get("hrt") or {}
    twa_d = res.get("twa") or {}
    prsa_d = res.get("prsa") or res.get("prsa_report") or {}
    st_d = res.get("st_segment") or res.get("st_report") or {}
    pw_d = res.get("p_wave") or res.get("p_wave_report") or {}
    edr_d = res.get("edr") or res.get("edr_report") or {}
    circ_d = res.get("circadian") or res.get("circadian_report") or {}
    af_d = res.get("af_report") or {}
    sqi_d = res.get("sqi") or {}

    return {
        "file_name": file_path.name,
        "file_path": str(file_path),
        "status": "OK",
        "error_message": "",
        "execution_mode": mode,
        "sampling_rate_hz": round(float(res.get("fs", 500.0) or 500.0), 1),
        "total_beats": int(summ.get("num_beats", len(res.get("beats") or []))),
        "mean_hr_bpm": round(float(summ.get("mean_hr_bpm", 0.0) or 0.0), 2),
        "mean_qt_ms": round(float(summ.get("mean_qt_ms", 0.0) or 0.0), 2),
        "mean_qtc_bazett_ms": round(float(summ.get("mean_qtc_bazett_ms", 0.0) or 0.0), 2),
        "mean_qtc_fridericia_ms": round(float(summ.get("mean_qtc_fridericia_ms", 0.0) or 0.0), 2),
        "mean_qtc_framingham_ms": round(float(summ.get("mean_qtc_framingham_ms", 0.0) or 0.0), 2),
        "mean_qtc_hodges_ms": round(float(summ.get("mean_qtc_hodges_ms", 0.0) or 0.0), 2),
        "mean_j_tpeak_ms": round(float(summ.get("mean_j_tpeak_ms", 0.0) or 0.0), 2),
        "mean_j_tpeakc_ms": round(float(summ.get("mean_j_tpeakc_ms", 0.0) or 0.0), 2),
        "mean_tpe_ms": round(float(summ.get("mean_tpe_ms", 0.0) or 0.0), 2),
        "mean_tpe_qt_ratio": round(float(summ.get("mean_tpe_qt_ratio", 0.0) or 0.0), 4),
        "stv_qt_ms": round(float(qtv.get("stv_qt_ms", summ.get("stv_qt_ms", 0.0)) or 0.0), 3),
        "ltv_qt_ms": round(float(qtv.get("ltv_qt_ms", summ.get("ltv_qt_ms", 0.0)) or 0.0), 3),
        "tdp_risk_category": str(qtv.get("tdp_risk_category", summ.get("tdp_risk_category", "LOW_TDP_RISK"))),
        "t_wave_asymmetry_ratio": round(float(tmorph.get("mean_asymmetry_ratio", 1.0) or 1.0), 3),
        "t_wave_flatness_score": round(float(tmorph.get("mean_flatness_score", 0.0) or 0.0), 3),
        "t_wave_notched_pct": round(float(tmorph.get("notched_beats_pct", 0.0) or 0.0), 2),
        "t_wave_morphology_verdict": str(tmorph.get("verdict", "NORMAL_MORPHOLOGY")),
        "svd_t2_t1_ratio": round(float(svd.get("t2_t1_ratio", 0.0) or 0.0), 4),
        "svd_tcrt": round(float(svd.get("tcrt", 0.0) or 0.0), 4),
        "qtvi": round(qtvi_val if qtvi_val == qtvi_val else 0.0, 3),
        "qtrr_slope_beta": round(float(qtrr_d.get("slope", 0.0) or 0.0), 4),
        "hysteresis_lambda_star": round(float(hyst_d.get("optimal_lambda", 0.0) or 0.0), 4),
        "hysteresis_t90_sec": round(float(hyst_d.get("t90_sec", 0.0) or 0.0), 2),
        "hrv_sdnn_ms": round(float(hrv_d.get("sdnn_ms", 0.0) or 0.0), 2),
        "hrv_rmssd_ms": round(float(hrv_d.get("rmssd_ms", 0.0) or 0.0), 2),
        "hrt_category": str(hrt_d.get("risk_category", "CATEGORY_0_NORMAL")),
        "peak_mma_twa_uv": round(float((twa_d.get("mma") or {}).get("peak_twa_uv", 0.0) or 0.0), 2),
        "prsa_dc_ms": round(float(prsa_d.get("dc_ms", 0.0) or 0.0), 2),
        "prsa_ac_ms": round(float(prsa_d.get("ac_ms", 0.0) or 0.0), 2),
        "prsa_risk_category": str(prsa_d.get("risk_category", "INSUFFICIENT_DATA")),
        "st_mean_level_uv": round(float(st_d.get("mean_st_level_uv", 0.0) or 0.0), 2),
        "st_ischemic_episodes": int(st_d.get("num_episodes", 0) or 0),
        "st_verdict": str(st_d.get("verdict", "NORMAL")),
        "pr_mean_ms": round(float(pw_d.get("mean_pr_ms", 0.0) or 0.0), 2),
        "av_block_verdict": str(pw_d.get("av_conduction_verdict", pw_d.get("av_block_verdict", "NORMAL_AV_CONDUCTION"))),
        "edr_respiratory_rate_brpm": round(float(edr_d.get("respiratory_rate_brpm", 0.0) or 0.0), 2),
        "edr_apnea_screening": str(edr_d.get("apnea_screening_verdict", edr_d.get("apnea_screening", "NORMAL_RESPIRATION"))),
        "circadian_hr_dip_pct": round(float(circ_d.get("hr_dip_pct", 0.0) or 0.0), 2),
        "circadian_delta_qtcf_ms": round(float(circ_d.get("delta_qtcf_night_minus_day_ms", 0.0) or 0.0), 2),
        "circadian_verdict": str(circ_d.get("verdict", "SINGLE_EPOCH_RECORDING")),
        "af_burden_pct": round(float(af_d.get("af_burden_pct", 0.0) or 0.0), 2),
        "pvc_count": int(summ.get("pvc_count", 0) or 0),
        "pac_count": int(summ.get("pac_count", 0) or 0),
        "sqi_verdict": str(sqi_d.get("verdict", "UNKNOWN")),
    }


class BatchAPI:
    """Headless cohort batch runner for multi-file ECG and Holter clinical trials."""

    @staticmethod
    def analyze_directory(
        input_dir: str | Path,
        output_csv_path: str | Path | None = None,
        output_json_path: str | Path | None = None,
        recursive: bool = False,
        stream_threshold_mb: float = 25.0,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> dict[str, Any]:
        """Scans a directory for ECG files, executes fault-isolated analysis, and exports CSV/JSON summaries."""
        root = Path(input_dir)
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Batch input directory does not exist: {root}")

        pattern = "**/*" if recursive else "*"
        all_candidates = sorted(p for p in root.glob(pattern) if p.is_file())

        # Collect WFDB header stems so companion .dat files are not analyzed twice
        hea_stems = {p.with_suffix("") for p in all_candidates if p.suffix.lower() == ".hea"}

        ecg_files: list[Path] = []
        for p in all_candidates:
            ext = p.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            if ext == ".dat" and p.with_suffix("") in hea_stems:
                continue
            ecg_files.append(p)

        rows: list[dict[str, Any]] = []
        n_files = len(ecg_files)
        succeeded = 0
        failed = 0

        for idx, f_path in enumerate(ecg_files):
            if progress_callback:
                progress_callback(idx / max(1, n_files), f"Analyzing {f_path.name} ({idx + 1}/{n_files})...")
            try:
                size_mb = f_path.stat().st_size / (1024.0 * 1024.0)
                if size_mb >= stream_threshold_mb:
                    res = analyze_ecg_stream(f_path)
                    mode = "STREAM"
                else:
                    leads, fs, meta = load_ecg_dataset(f_path)
                    if not leads:
                        raise ValueError("No ECG leads decoded from container.")
                    first_lead = next(iter(leads.values()))
                    res = analyze_ecg(first_lead, fs=fs, multi_lead_signals=leads, metadata=meta)
                    mode = "IN_MEMORY"

                row = _extract_batch_row(f_path, res, mode=mode)
                rows.append(row)
                succeeded += 1
            except Exception as exc:
                err_row: dict[str, Any] = dict.fromkeys(BATCH_BIOMARKER_COLUMNS, "")
                err_row.update({
                    "file_name": f_path.name,
                    "file_path": str(f_path),
                    "status": "ERROR",
                    "error_message": str(exc),
                    "execution_mode": "FAILED",
                })
                rows.append(err_row)
                failed += 1

        if output_csv_path is not None:
            csv_out = Path(output_csv_path)
            csv_out.parent.mkdir(parents=True, exist_ok=True)
            with csv_out.open("w", newline="", encoding="utf-8") as cf:
                writer = csv.DictWriter(cf, fieldnames=list(BATCH_BIOMARKER_COLUMNS))
                writer.writeheader()
                for r in rows:
                    writer.writerow(r)

        report_payload = {
            "input_directory": str(root),
            "total_files": n_files,
            "succeeded_count": succeeded,
            "failed_count": failed,
            "columns": list(BATCH_BIOMARKER_COLUMNS),
            "records": rows,
        }

        if output_json_path is not None:
            json_out = Path(output_json_path)
            json_out.parent.mkdir(parents=True, exist_ok=True)
            json_out.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

        if progress_callback:
            progress_callback(1.0, f"Batch analysis complete ({succeeded}/{n_files} succeeded).")

        return report_payload
