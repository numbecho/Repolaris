# Packaging, Distribution & CI/CD Guide

This guide covers the two-tier packaging strategy for **Repolaris**:
1. **[Nuitka](https://nuitka.net/) for Rapid Prototype Testing**: Compiles Python source directly into native machine code (C/C++) for standalone executable testing with intellectual property protection and high execution speed.
2. **[Briefcase (BeeWare)](https://briefcase.readthedocs.io/) for Distribution Releases**: Wraps the application into native platform installers (Windows `.msi`, macOS `.dmg`, Linux `.AppImage` / `.deb`) with system integration, desktop shortcuts, and clean uninstallation.

---

## 1. Strategy Overview

| Feature | Nuitka (Prototype / Internal Review) | Briefcase (Production Distribution) |
| :--- | :--- | :--- |
| **Primary Goal** | Fast standalone binary for research & colleague testing | Polished end-user installer for hospital clinics |
| **Output Type** | Standalone folder / single binary (`repolaris.exe`) | Native platform installer (`.msi`, `.dmg`, `.AppImage`) |
| **IP Protection** | High (compiled to native C/C++ machine code) | Standard (packaged Python wheels) |
| **OS Registration** | Portable (runs from any folder / USB stick) | Full (Start Menu, Programs & Features, desktop icon) |
| **Build Driver** | `scripts/build_nuitka.py` | `pyproject.toml` (`[tool.briefcase]`) |

---

## 2. Setting Up Required Build Tools

### Windows Build Environment

1. **Python $\ge 3.10$ (64-bit)**: Ensure Python is installed from [python.org](https://www.python.org/) with "Add to PATH" checked.
2. **Microsoft Visual C++ Build Tools**:
   - Download the [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).
   - In the installer, select **Desktop development with C++** (includes MSVC compiler and Windows SDK).
3. **WiX Toolset (for Briefcase MSI packaging)**:
   - Briefcase automatically downloads the WiX Toolset during its first run, or you can install it via:
     ```powershell
     dotnet tool install --global wix
     ```

### Linux (Ubuntu / Debian) Build Environment

Install the required C/C++ compiler, OpenGL development libraries, and packaging utilities:

```bash
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    gcc \
    g++ \
    patchelf \
    ccache \
    libgl1-mesa-dev \
    libgl1-mesa-glx \
    libxkbcommon-x11-0 \
    appstream
```

### macOS Build Environment

Install the Apple Developer Command Line Tools:

```bash
xcode-select --install
```

---

## 3. Local Build Instructions

### A. Compiling a Standalone Prototype with Nuitka

Install the packaging dependencies:

```bash
pip install -e ".[gui,packaging]"
```

Run the automated Nuitka build script:

```bash
# Standalone directory bundle (recommended for fast testing)
python scripts/build_nuitka.py --standalone

# Single executable file
python scripts/build_nuitka.py --onefile
```

The resulting binaries will be placed in `dist/nuitka/`. The standalone output is completely portable and can be zipped and shared with colleagues or clinicians without requiring Python.

### B. Building a Native Installer with Briefcase

Install Briefcase:

```bash
pip install briefcase
```

Execute the 3-step Briefcase workflow:

```bash
# 1. Generate the platform-specific scaffold
briefcase create

# 2. Build the application code and dependencies
briefcase build

# 3. Generate the distribution installer
briefcase package
```

The resulting installers are located in `dist/`:
- **Windows**: `dist/Repolaris-0.2.0.msi`
- **macOS**: `dist/Repolaris-0.2.0.dmg`
- **Linux**: `dist/Repolaris-0.2.0.AppImage` (or `.deb`)

---

## 4. Continuous Integration & CD Integration

Repolaris includes an automated multi-platform GitHub Actions workflow located at `.github/workflows/build-artifacts.yml`.

### Workflow Triggers
* **Push to `main`**: Runs full signal engine tests and packages trial builds.
* **Release Tags (`v*`)**: Compiles official release installers and attaches them to build artifacts.
* **Manual Dispatch**: Can be triggered manually on-demand from the GitHub Actions tab.

### Matrix Pipeline Stages
1. **`test` Job**: Runs the 32-case unit test suite on Python 3.10 across all I/O readers, restitution algorithms, Berger QTVI, and i18n translation parity.
2. **`nuitka-prototype` Job**: Parallel matrix across `windows-latest`, `ubuntu-22.04`, and `macos-13` compiling native standalone binaries. Uploads `repolaris-prototype-<OS>` artifacts (14-day retention).
3. **`briefcase-release` Job**: Parallel matrix generating Windows MSI, macOS DMG, and Linux AppImage/DEB installers. Uploads `repolaris-distribution-<OS>` artifacts (30-day retention).

---

## 5. Troubleshooting & Best Practices

* **Qt Display Failures on Headless Linux**: In CI/CD or docker testing environments without an X11 server, set `QT_QPA_PLATFORM=offscreen` to prevent Qt initialization errors.
* **Antivirus False Positives (Windows)**: Unsigned Nuitka executables may occasionally trigger heuristic alerts on Windows Defender. For production distributions, sign the Briefcase `.msi` using your organization's Authenticode certificate (`signtool.exe sign /a /fd SHA256 /tr ...`).
* **Dynamic Codecs & Translations**: If adding new translation locales (`i18n.py`) or format parsers, verify that `scripts/build_nuitka.py` includes `--include-package-data=repolaris` so resource dictionaries are bundled inside the binary.
