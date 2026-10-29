# Packaging, Distribution & CI/CD Guide

This guide covers the two-tier packaging strategy for **Repolaris**:
1. **[Briefcase (BeeWare)](https://briefcase.readthedocs.io/) for Distribution Releases**: Wraps the application into native platform installers (Windows `.msi`, macOS `.dmg`, Linux `.AppImage` / `.deb`) with system integration, desktop shortcuts, and clean uninstallation.

---

## 1. Strategy Overview

| Feature | BeeWare Briefcase Distribution |
| :--- | :--- |
| :--- | :--- |
| **Primary Goal** | Polished end-user installer for hospital clinics |
| **Output Type** | Native platform installer (`.msi`, `.dmg`, `.AppImage`) |
| **IP Protection** | Standard (packaged Python wheels) |
| **OS Registration** | Full (Start Menu, Programs & Features, desktop icon) |
| **Build Driver** | `pyproject.toml` (`[tool.briefcase]`) |

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
1. **`test` Job**: Runs the 32-case unit test suite on Python 3.14 across all I/O readers, restitution algorithms, Berger QTVI, and i18n translation parity.
3. **`briefcase-release` Job**: Parallel matrix generating Windows MSI, macOS DMG, and Linux AppImage/DEB installers. Uploads `repolaris-distribution-<OS>` artifacts (30-day retention).

---

## 5. Troubleshooting & Best Practices

* **Qt Display Failures on Headless Linux**: In CI/CD or docker testing environments without an X11 server, set `QT_QPA_PLATFORM=offscreen` to prevent Qt initialization errors.
