# Packaging, Distribution & CI/CD Guide

This guide covers the native desktop packaging and continuous integration strategy for **Repolaris** using **[Briefcase (BeeWare)](https://briefcase.readthedocs.io/)**, which wraps the application into native platform installers (Windows `.msi`, macOS `.dmg`, Linux `.AppImage` / `.deb`) with system integration, desktop shortcuts, and clean uninstallation.

---

## 1. Strategy Overview

| Feature | BeeWare Briefcase Distribution |
| :--- | :--- |
| **Primary Goal** | Polished end-user installer for hospital clinics and research workstations |
| **Output Type** | Native platform installer (`.msi`, `.dmg`, `.AppImage`, `.deb`) |
| **Packaging Standard** | PEP 621 & PEP 639 (`pyproject.toml` `[tool.briefcase]`) |
| **OS Registration** | Full (Start Menu, Programs & Features, desktop icon) |
| **CI Automation** | GitHub Actions matrix (`.github/workflows/build-artifacts.yml`) |

---

## 2. Setting Up Required Build Tools

### Windows Build Environment

1. **Python $\ge 3.14$ (64-bit)**: Ensure Python is installed from [python.org](https://www.python.org/) with "Add to PATH" checked.
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
    libgl1 \
    libegl1 \
    libxkbcommon-x11-0 \
    libgtk-3-dev \
    appstream \
    dpkg-dev \
    debhelper
```

### macOS Build Environment

Install the Apple Developer Command Line Tools:

```bash
xcode-select --install
```

---

## 3. Local Build Instructions

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
- **Windows**: `dist/Repolaris-0.8.1.msi`
- **macOS**: `dist/Repolaris-0.8.1.dmg`
- **Linux**: `dist/Repolaris-0.8.1.AppImage` (or `.deb`)

---

## 4. Continuous Integration & CD Integration

Repolaris includes an automated multi-platform GitHub Actions workflow located at `.github/workflows/build-artifacts.yml`.

### Workflow Triggers
* **Push to `main` & Pull Requests**: Runs the full 90-test signal engine, streaming, PDF report, and i18n verification suite and builds cross-platform packages.
* **Release Tags (`v*`)**: Compiles official release installers and attaches them to build artifacts.
* **Manual Dispatch**: Can be triggered on-demand from the GitHub Actions tab.

### Matrix Pipeline Stages
1. **`test` Job**: Runs the standard `pip` + `python -m unittest discover tests` verification suite across all 116 unit tests.
2. **`uv-ruff-test` Job**: Uses `astral-sh/setup-uv@v5` with Python 3.14 to run `uv sync --all-extras --dev`, `uv run ruff check src tests`, `uv run ruff format --check src tests`, and `uv run pytest -v`. across all I/O readers, streaming buffers, restitution algorithms, Berger QTVI, PDF report generation, and i18n translation parity.
3. **`briefcase-release` Job**: Parallel matrix generating Windows MSI, macOS DMG, and Linux AppImage/DEB installers. Uploads `repolaris-distribution-<OS>` artifacts (30-day retention).

---

## 5. Troubleshooting & Best Practices

* **Qt Display Failures on Headless Linux**: In CI/CD or Docker testing environments without an X11 server, set `QT_QPA_PLATFORM=offscreen` (configured by default in `.github/workflows/build-artifacts.yml`) to prevent Qt initialization errors.
