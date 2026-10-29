#!/usr/bin/env python3
"""
Repolaris Nuitka Prototype Build Script
Compiles the Repolaris clinical GUI workstation into an optimized native standalone binary.

Usage:
    python scripts/build_nuitka.py [--standalone | --onefile] [--debug]

Prerequisites:
    pip install "nuitka>=2.1" ordered-set
    Windows: Visual Studio Community / Build Tools with C++ workload
    Linux:   gcc/g++ >= 10, patchelf
    macOS:   Xcode Command Line Tools
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path

def main():
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)

    mode = "--onefile" if "--onefile" in sys.argv else "--standalone"
    is_debug = "--debug" in sys.argv

    output_dir = repo_root / "dist" / "nuitka"
    output_dir.mkdir(parents=True, exist_ok=True)

    entry_point = repo_root / "src" / "repolaris" / "app.py"
    if not entry_point.exists():
        print(f"Error: Entry point not found at {entry_point}", file=sys.stderr)
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "nuitka",
        mode,
        "--assume-yes-for-downloads",
        "--enable-plugin=pyqt6",
        "--include-package=repolaris",
        "--include-package-data=repolaris",
        "--follow-imports",
        "--warn-unusual-code",
        f"--output-dir={output_dir}",
        "--output-filename=repolaris",
    ]

    # Windows GUI mode to prevent terminal popup
    if sys.platform == "win32":
        cmd.append("--windows-console-mode=disable")
        cmd.append("--windows-icon-from-ico=src/repolaris/resources/icon.ico" if (repo_root / "src/repolaris/resources/icon.ico").exists() else "--windows-console-mode=disable")
    elif sys.platform == "darwin":
        cmd.append("--macos-create-app-bundle")
        cmd.append("--macos-app-name=Repolaris")

    if not is_debug:
        cmd.append("--lto=yes")
        cmd.append("--remove-output")

    cmd.append(str(entry_point))

    print(f"Building Repolaris native prototype with Nuitka [{mode}]...")
    print(f"Command: {' '.join(cmd)}")
    
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print(f"\nBuild successfully generated in: {output_dir}")
    else:
        print(f"\nBuild failed with exit code: {res.returncode}", file=sys.stderr)
        sys.exit(res.returncode)

if __name__ == "__main__":
    main()
