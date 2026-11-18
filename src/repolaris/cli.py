"""Command-line interface (CLI) for the Repolaris analysis workstation."""

from __future__ import annotations

import argparse
import sys
from typing import Any

import numpy as np

from repolaris.api import AnalysisAPI, ExportAPI, StudyAPI


def print_cli_progress(fraction: float, message: str) -> None:
    """Renders a standard terminal progress bar with status message."""
    clamped = min(max(fraction, 0.0), 1.0)
    percent = int(clamped * 100)
    bar_len = 24
    filled = int(bar_len * clamped)
    bar = "█" * filled + "░" * (bar_len - filled)
    sys.stdout.write(f"\r[{bar}] {percent:3d}% — {message:<48}")
    sys.stdout.flush()
    if fraction >= 1.0:
        sys.stdout.write("\n")
        sys.stdout.flush()


def _build_parser() -> argparse.ArgumentParser:
    """Constructs the Repolaris CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="repolaris",
        description="Repolaris: Modern ECG, QT interval, and ventricular repolarization CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    demo_p = subparsers.add_parser("demo", help="Run analysis on a synthetic ECG")
    demo_p.add_argument("--duration", type=float, default=10.0, help="Duration in seconds")
    demo_p.add_argument("--fs", type=float, default=500.0, help="Sampling frequency (Hz)")
    demo_p.add_argument("--hr", type=float, default=72.0, help="Heart rate (BPM)")
    demo_p.add_argument("--export", help="Optional target .pecg path to export the study after analysis")
    demo_p.add_argument("--pdf", help="Optional target .pdf path to generate a clinical PDF report")

    ana_p = subparsers.add_parser("analyze", help="Analyze an ECG recording file")
    ana_p.add_argument(
        "file",
        help="Path to ECG file (.pecg, .ecg, .dcm, .dicom, .xml, .aecg, .scp, .e3c, .edf, .hea, .csv, .npy)",
    )
    ana_p.add_argument(
        "--fs",
        type=float,
        default=None,
        help="Optional sampling frequency override (Hz); auto-detected from file header by default",
    )
    ana_p.add_argument("--lead", default=0, help="Lead index or channel name")
    ana_p.add_argument("--export", help="Optional target .pecg path to export the study after analysis")
    ana_p.add_argument("--pdf", help="Optional target .pdf path to generate a clinical PDF report")
    ana_p.add_argument("--stream", action="store_true", help="Use chunked out-of-core streaming for multi-hour Holters")

    exp_p = subparsers.add_parser("export", help="Convert and export an ECG recording to .pecg format")
    exp_p.add_argument("file", help="Path to input ECG recording")
    exp_p.add_argument("output", help="Target .pecg output path")
    exp_p.add_argument("--compression", default="zstd", choices=["zstd", "deflate", "none"], help="Compression mode")

    return parser


def _run_demo(args: argparse.Namespace) -> dict[str, Any]:
    """Executes synthetic benchmark generation, analysis, and optional exports."""
    print(f"Generating synthetic ECG ({args.duration}s, {args.hr} BPM, {args.fs} Hz)...")
    _, sig, _ = StudyAPI.generate_demo_study(
        duration_sec=args.duration,
        fs=args.fs,
        heart_rate_bpm=args.hr,
        progress_callback=print_cli_progress,
    )
    print("Executing diagnostic analysis pipeline...")
    results = AnalysisAPI.analyze_signal(sig, fs=args.fs, progress_callback=print_cli_progress)

    if args.export:
        print(f"Exporting benchmark study container to {args.export}...")
        ann_mgr = results.get("annotations")
        ExportAPI.export_study_pecg(
            filepath=args.export,
            signals=sig,
            sampling_rate=args.fs,
            lead_names=["Lead II"],
            patient_info={"indication": "Synthetic Demo Study"},
            annotations={"beats": ann_mgr.to_dict_list()} if ann_mgr else {},
            events=results.get("events", []),
            progress_callback=print_cli_progress,
        )
    if args.pdf:
        print(f"Generating clinical PDF report at {args.pdf}...")
        ExportAPI.export_clinical_pdf(
            filepath=args.pdf,
            analysis_results=results,
            patient_metadata={"patient_id": "DEMO-001", "indication": "Synthetic Demo Study"},
            fs=args.fs,
            lead_name="Lead II",
            progress_callback=print_cli_progress,
        )
    return results


def _run_analyze(args: argparse.Namespace) -> dict[str, Any]:
    """Executes file-based or streamed ECG analysis and optional exports."""
    print(f"Loading {args.file}...")
    lead_param: str | int = int(args.lead) if str(args.lead).isdigit() else str(args.lead)

    meta: dict[str, Any] = {}
    if args.stream:
        fs_init = float(args.fs) if args.fs is not None else 500.0
        print("Executing chunked streaming Holter pipeline...")
        results = AnalysisAPI.analyze_stream(
            args.file,
            fs=fs_init,
            lead=lead_param,
            progress_callback=print_cli_progress,
        )
        fs = float(args.fs) if args.fs is not None else float(results.get("fs", fs_init))
        meta = dict(results.get("metadata") or {})
        sig = results.get("clean_signal")
    else:
        signals_dict, detected_fs, meta = StudyAPI.load_study_dataset(
            args.file,
            progress_callback=print_cli_progress,
        )
        lead_keys = list(signals_dict.keys())
        if isinstance(lead_param, int):
            sig = signals_dict[lead_keys[min(max(0, lead_param), len(lead_keys) - 1)]]
        elif lead_param in signals_dict:
            sig = signals_dict[lead_param]
        else:
            sig = next(iter(signals_dict.values()))
        fs = float(args.fs) if args.fs is not None else float(detected_fs)
        multi_sigs = signals_dict if len(signals_dict) >= 2 else None
        print("Executing diagnostic analysis pipeline...")
        results = AnalysisAPI.analyze_signal(
            sig,
            fs=fs,
            progress_callback=print_cli_progress,
            multi_lead_signals=multi_sigs,
            lead_names=lead_keys if multi_sigs is not None else None,
        )

    if args.export and sig is not None:
        print(f"Exporting study container to {args.export}...")
        ann_mgr = results.get("annotations")
        ExportAPI.export_study_pecg(
            filepath=args.export,
            signals=sig,
            sampling_rate=fs,
            lead_names=[f"Lead {args.lead}"],
            patient_info=meta,
            annotations={"beats": ann_mgr.to_dict_list()} if ann_mgr else {},
            events=results.get("events", []),
            progress_callback=print_cli_progress,
        )
    if args.pdf:
        print(f"Generating clinical PDF report at {args.pdf}...")
        ExportAPI.export_clinical_pdf(
            filepath=args.pdf,
            analysis_results=results,
            patient_metadata=meta,
            fs=fs,
            lead_name=f"Lead {args.lead}",
            progress_callback=print_cli_progress,
        )
    return results


def _run_export(args: argparse.Namespace) -> None:
    """Converts any clinical ECG file into a compressed .pecg study archive."""
    print(f"Loading {args.file} for export packaging...")
    signals, fs, meta = StudyAPI.load_study_dataset(args.file, progress_callback=print_cli_progress)
    lead_names = list(signals.keys())
    lead_matrix = np.array([signals[k] for k in lead_names])
    print(f"Packaging {len(lead_names)} channels to {args.output}...")
    ExportAPI.export_study_pecg(
        filepath=args.output,
        signals=lead_matrix,
        sampling_rate=fs,
        lead_names=lead_names,
        patient_info=meta,
        compression=args.compression,
        progress_callback=print_cli_progress,
    )
    print(f"Export complete: {args.output}")


def _print_report(results: dict[str, Any]) -> None:
    """Formats and prints the diagnostic repolarization report to stdout."""
    summary = results["summary"]
    ectopic = results.get("ectopic_summary", {})
    qtvi = results.get("qtvi")
    stv_qt = results.get("stv_qt") or {}
    t_morph = results.get("t_morphology") or {}
    qtrr = results.get("qtrr")
    sqi = results.get("sqi", {})
    hrv = results.get("hrv")
    twa = results.get("twa")
    hyst = results.get("hysteresis")
    events = results.get("events", [])
    af_report = results.get("af_report")
    trends = results.get("trends")

    print("========================================")
    print("    Repolaris Repolarization Report     ")
    print("========================================")
    print(f"Heart Rate:          {summary['mean_hr_bpm']:.1f} BPM")
    print(f"Total Beats:         {summary['total_beats']}")
    print(f"Mean QT:             {summary['mean_qt_ms']:.1f} ms")
    print(f"Mean QTc Bazett:     {summary['mean_qtc_bazett_ms']:.1f} ms")
    print(f"Mean QTc Fridericia: {summary['mean_qtc_fridericia_ms']:.1f} ms")
    if "mean_qtc_framingham_ms" in summary:
        print(f"Mean QTc Framingham: {summary['mean_qtc_framingham_ms']:.1f} ms")
    if "mean_qtc_hodges_ms" in summary:
        print(f"Mean QTc Hodges:     {summary['mean_qtc_hodges_ms']:.1f} ms")
    if summary.get("mean_jt_peak_c_ms", 0.0) > 0:
        print(f"FDA CiPA J-Tpeakc:   {summary['mean_jt_peak_c_ms']:.1f} ms")
        print(
            f"Transmural Tpe:      {summary.get('mean_tpe_ms', 0.0):.1f} ms "
            f"(Tpe/QT: {summary.get('mean_tpe_qt_ratio', 0.0):.3f})"
        )
    if stv_qt:
        print(
            f"Poincaré STV_QT:     {stv_qt.get('stv_qt_ms', 0.0):.2f} ms "
            f"(LTV_QT: {stv_qt.get('ltv_qt_ms', 0.0):.2f} ms, {stv_qt.get('risk_category', 'NORMAL')})"
        )
    if t_morph:
        svd_3d = t_morph.get("svd_3d") or {}
        t2t1 = svd_3d.get("t2_t1_ratio")
        tcrt = svd_3d.get("tcrt")
        svd_str = f" | T2/T1: {t2t1:.3f}, TCRT: {tcrt:.2f}" if (t2t1 is not None and tcrt is not None) else ""
        print(
            f"T-Wave Morphology:   Asym={t_morph.get('mean_asymmetry_ratio', 1.0):.2f}, "
            f"Flat={t_morph.get('mean_flatness_score', 0.0):.2f}{svd_str} ({t_morph.get('verdict', 'NORMAL')})"
        )
    if ectopic:
        print(f"PVC Count:           {ectopic.get('pvc_count', 0)} ({ectopic.get('pvc_percentage', 0.0):.1f}%)")
        print(f"PAC Count:           {ectopic.get('pac_count', 0)}")
    if qtvi is not None:
        print(f"QTVI:                {qtvi:.2f}")
    if qtrr:
        slope_val = qtrr.get("slope", qtrr.get("linear_slope", 0.0))
        print(f"QT-RR Slope (Beta):  {slope_val:.4f}")
    if hyst:
        print(f"Hysteresis Lambda*:  {hyst.get('optimal_lambda', 0.0):.4f} (t90: {hyst.get('t90_sec', 0.0):.1f}s)")
    if hrv and "time_domain" in hrv:
        td = hrv["time_domain"]
        print(f"HRV (SDNN / RMSSD):  {td.get('sdnn', 0.0):.1f} ms / {td.get('rmssd', 0.0):.1f} ms")
    if twa and "mma" in twa:
        print(f"Peak MMA TWA:        {twa['mma'].get('max_v_mma_uv', 0.0):.1f} uV ({twa['mma'].get('risk_level', 'NORMAL')})")
    if sqi:
        print(f"SQI (pSQI/basSQI):   {sqi.get('psqi', 0):.2f} / {sqi.get('bassqi', 0):.2f}")
        print(f"Quality Status:      {sqi.get('verdict', sqi.get('status', 'Unknown'))}")
    if af_report:
        print(f"AF Burden:           {af_report.get('af_burden_pct', 0.0):.2f}% ({af_report.get('num_episodes', 0)} episodes)")
    if trends:
        print(f"Holter Pauses:       {trends.get('total_pauses', 0)} (max {trends.get('max_pause_sec', 0.0):.2f}s)")
    if events:
        print(f"Clinical Events:     {len(events)} detected")
        for ev in events[:5]:
            if isinstance(ev, dict):
                t_sec = ev.get("timestamp_sec", ev.get("time_offset_sec", ev.get("time_sec", 0.0)))
                etype = ev.get("event_type", "Event")
                desc = ev.get("description", "")
            else:
                t_sec = getattr(ev, "timestamp_sec", getattr(ev, "time_offset_sec", 0.0))
                etype = getattr(ev, "event_type", "Event")
                desc = getattr(ev, "description", "")
            etype_str = etype.value if hasattr(etype, "value") else str(etype)
            print(f"  - [{t_sec:.1f}s] {etype_str}: {desc}")
        if len(events) > 5:
            print(f"  ... and {len(events) - 5} more")
    print("========================================")


def main(argv: list[str] | None = None) -> None:
    """Entry point for the Repolaris command-line interface."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "demo":
        results = _run_demo(args)
        _print_report(results)
    elif args.command == "analyze":
        results = _run_analyze(args)
        _print_report(results)
    elif args.command == "export":
        _run_export(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
