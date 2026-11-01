"""Command-line interface (CLI) for the PyECG analysis workstation."""

from __future__ import annotations

import argparse
import sys
from typing import Optional
import numpy as np

from repolaris.api import StudyAPI, AnalysisAPI, ExportAPI


def print_cli_progress(fraction: float, message: str) -> None:
    """Renders a standard terminal progress bar with status message."""
    percent = int(min(max(fraction, 0.0), 1.0) * 100)
    bar_len = 24
    filled = int(bar_len * min(max(fraction, 0.0), 1.0))
    bar = "█" * filled + "░" * (bar_len - filled)
    sys.stdout.write(f"\r[{bar}] {percent:3d}% — {message:<48}")
    sys.stdout.flush()
    if fraction >= 1.0:
        sys.stdout.write("\n")
        sys.stdout.flush()


def main(argv: Optional[list[str]] = None) -> None:
    """Entrypoint for the PyECG command-line tool."""
    parser = argparse.ArgumentParser(
        prog="repolaris",
        description="PyECG: Modern ECG, QT interval, and ventricular repolarization CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # demo command
    demo_p = subparsers.add_parser("demo", help="Run analysis on a synthetic ECG")
    demo_p.add_argument("--duration", type=float, default=10.0, help="Duration in seconds")
    demo_p.add_argument("--fs", type=float, default=500.0, help="Sampling frequency (Hz)")
    demo_p.add_argument("--hr", type=float, default=72.0, help="Heart rate (BPM)")
    demo_p.add_argument("--export", help="Optional target .pecg path to export the study after analysis")

    # analyze command
    ana_p = subparsers.add_parser("analyze", help="Analyze an ECG recording file")
    ana_p.add_argument("file", help="Path to ECG file (.pecg, .ecg, .e3c, .edf, .hea, .csv, .npy)")
    ana_p.add_argument("--fs", type=float, default=500.0, help="Sampling frequency")
    ana_p.add_argument("--lead", default=0, help="Lead index or channel name")
    ana_p.add_argument("--export", help="Optional target .pecg path to export the study after analysis")

    # export command
    exp_p = subparsers.add_parser("export", help="Convert and export an ECG recording to .pecg format")
    exp_p.add_argument("file", help="Path to input ECG recording")
    exp_p.add_argument("output", help="Target .pecg output path")
    exp_p.add_argument("--compression", default="zstd", choices=["zstd", "deflate", "none"], help="Compression mode")

    args = parser.parse_args(argv)

    if args.command == "demo":
        print(f"Generating synthetic ECG ({args.duration}s, {args.hr} BPM, {args.fs} Hz)...")
        _, sig, _ = StudyAPI.generate_demo_study(
            duration_sec=args.duration,
            fs=args.fs,
            heart_rate_bpm=args.hr,
            progress_callback=print_cli_progress,
        )
        print("Executing diagnostic analysis pipeline...")
        results = AnalysisAPI.analyze_signal(
            sig,
            fs=args.fs,
            progress_callback=print_cli_progress,
        )
        if args.export:
            print(f"Exporting benchmark study container to {args.export}...")
            ExportAPI.export_study_pecg(
                filepath=args.export,
                signals=sig,
                sampling_rate=args.fs,
                lead_names=["Lead II"],
                patient_info={"indication": "Synthetic Demo Study"},
                annotations={"beats": results.get("annotations").to_dict_list()} if results.get("annotations") else {},
                events=results.get("events", []),
                progress_callback=print_cli_progress,
            )

    elif args.command == "analyze":
        print(f"Loading {args.file}...")
        lead_param = int(args.lead) if str(args.lead).isdigit() else args.lead
        sig, detected_fs = StudyAPI.load_study_file(
            args.file,
            lead_param,
            progress_callback=print_cli_progress,
        )
        fs = args.fs if args.fs else detected_fs
        print("Executing diagnostic analysis pipeline...")
        results = AnalysisAPI.analyze_signal(
            sig,
            fs=fs,
            progress_callback=print_cli_progress,
        )
        if args.export:
            print(f"Exporting study container to {args.export}...")
            ExportAPI.export_study_pecg(
                filepath=args.export,
                signals=sig,
                sampling_rate=fs,
                lead_names=[f"Lead {args.lead}"],
                annotations={"beats": results.get("annotations").to_dict_list()} if results.get("annotations") else {},
                events=results.get("events", []),
                progress_callback=print_cli_progress,
            )

    elif args.command == "export":
        print(f"Loading {args.file} for export packaging...")
        signals, fs, meta = StudyAPI.load_study_dataset(
            args.file,
            progress_callback=print_cli_progress,
        )
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
        return

    else:
        parser.print_help()
        sys.exit(0)

    summary = results["summary"]
    ectopic = results.get("ectopic_summary", {})
    qtvi = results.get("qtvi")
    qtrr = results.get("qtrr")
    sqi = results.get("sqi", {})
    events = results.get("events", [])

    print("========================================")
    print("      PyECG Repolarization Report       ")
    print("========================================")
    print(f"Heart Rate:          {summary['mean_hr_bpm']:.1f} BPM")
    print(f"Total Beats:         {summary['total_beats']}")
    print(f"Mean QT:             {summary['mean_qt_ms']:.1f} ms")
    print(f"Mean QTc Bazett:     {summary['mean_qtc_bazett_ms']:.1f} ms")
    print(f"Mean QTc Fridericia: {summary['mean_qtc_fridericia_ms']:.1f} ms")
    if ectopic:
        print(f"PVC Count:           {ectopic.get('pvc_count', 0)} ({ectopic.get('pvc_percentage', 0.0):.1f}%)")
        print(f"PAC Count:           {ectopic.get('pac_count', 0)}")
    if qtvi is not None:
        print(f"QTVI:                {qtvi:.2f}")
    if qtrr:
        print(f"QT-RR Slope (Beta):  {qtrr.get('linear_slope', 0):.4f}")
    if sqi:
        print(f"SQI (pSQI/basSQI):   {sqi.get('psqi', 0):.2f} / {sqi.get('bassqi', 0):.2f}")
        print(f"Quality Status:      {sqi.get('status', 'Unknown')}")
    if events:
        print(f"Clinical Events:     {len(events)} detected")
        for ev in events[:5]:
            t_sec = getattr(ev, "time_offset_sec", ev.get("time_offset_sec", ev.get("time_sec", 0.0)) if isinstance(ev, dict) else 0.0)
            etype = getattr(ev, "event_type", ev.get("event_type", "Event") if isinstance(ev, dict) else "Event")
            etype_str = etype.value if hasattr(etype, "value") else str(etype)
            desc = getattr(ev, "description", ev.get("description", "") if isinstance(ev, dict) else "")
            print(f"  - [{t_sec:.1f}s] {etype_str}: {desc}")
        if len(events) > 5:
            print(f"  ... and {len(events) - 5} more")
    print("========================================")


if __name__ == "__main__":
    main()
