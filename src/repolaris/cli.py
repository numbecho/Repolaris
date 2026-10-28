"""Command-line interface (CLI) for the PyECG analysis workstation."""

from __future__ import annotations

import argparse
import sys
from typing import Optional
import numpy as np

from repolaris.utils.signal import generate_synthetic_ecg
from repolaris.detection.pipeline import analyze_ecg
from repolaris.io.ecg_loader import load_ecg_file


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

    # analyze command
    ana_p = subparsers.add_parser("analyze", help="Analyze an ECG recording file")
    ana_p.add_argument("file", help="Path to ECG file (.pecg, .ecg, .e3c, .edf, .hea, .mat, .csv, .npy)")
    ana_p.add_argument("--fs", type=float, default=500.0, help="Sampling frequency")
    ana_p.add_argument("--lead", default=0, help="Lead index or channel name")

    args = parser.parse_args(argv)

    if args.command == "demo":
        print(f"Generating synthetic ECG ({args.duration}s, {args.hr} BPM, {args.fs} Hz)...")
        _, sig, _ = generate_synthetic_ecg(
            duration_sec=args.duration, fs=args.fs, heart_rate_bpm=args.hr
        )
        results = analyze_ecg(sig, fs=args.fs)

    elif args.command == "analyze":
        print(f"Loading {args.file}...")
        lead_param = int(args.lead) if str(args.lead).isdigit() else args.lead
        sig = load_ecg_file(args.file, lead_param)
        results = analyze_ecg(sig, fs=args.fs)

    else:
        parser.print_help()
        sys.exit(0)

    summary = results["summary"]
    ectopic = results.get("ectopic_summary", {})
    qtvi = results.get("qtvi")
    qtrr = results.get("qtrr")
    sqi = results.get("sqi", {})
    events = results.get("events", [])

    print("\n" + "=" * 50)
    print("             REPOLARIS CLINICAL REPORT")
    print("=" * 50)
    print(f"Total Beats Analyzed : {summary['total_beats']}")
    print(f"Mean Heart Rate      : {summary['mean_hr_bpm']:.1f} BPM")
    print(f"Mean QT Interval     : {summary['mean_qt_ms']:.1f} ms")
    print(f"Mean QTc (Bazett)    : {summary['mean_qtc_bazett_ms']:.1f} ms")
    print(f"Mean QTc (Fridericia): {summary['mean_qtc_fridericia_ms']:.1f} ms")

    if ectopic:
        pvc_c = ectopic.get("pvc_count", 0)
        pac_c = ectopic.get("pac_count", 0)
        burden = ectopic.get("ectopic_burden_pct", 0.0)
        print(f"AAMI Ectopic Burden  : {burden:.1f}% (PVC: {pvc_c}, PAC: {pac_c})")

    if qtvi is not None:
        print(f"Berger QTVI          : {qtvi:.2f} (Repolarization Lability)")
    if qtrr is not None:
        print(f"QT-RR Restitution    : Slope={qtrr['slope']:.3f}, r={qtrr['pearson_r']:.3f}")

    verdict = sqi.get("verdict", "N/A")
    snr = sqi.get("snr_db", 0.0)
    print(f"Signal Quality (SQI) : {verdict} (SNR: {snr:.1f} dB)")

    if events:
        print("-" * 50)
        print(f"Clinical Events Diary ({len(events)} detected):")
        for ev in events[:8]:
            sev = ev.get("severity", "INFO")
            print(f"  [{ev['timestamp_sec']:6.2f}s] {sev:8s} : {ev['event_type']} ({ev['metric_value']:.1f} {ev['unit']})")
        if len(events) > 8:
            print(f"  ... and {len(events) - 8} more events.")
    else:
        print("-" * 50)
        print("Clinical Events Diary: No critical arrhythmia or pause events.")
    print("=" * 50)


if __name__ == "__main__":
    main()
