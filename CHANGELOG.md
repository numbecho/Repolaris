# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-10-29

### Added
- Upgraded runtime to Python >= 3.14 minimum.
- Automated packaging with BeeWare Briefcase (Debian, Windows MSI, macOS bundles).
- Native Rich Text License (`LICENSE.rtf`) for Windows WiX installer.
- Modern ISO 8601 UTC timestamp logging via `datetime.now(timezone.utc)`.

### Removed
- Legacy MATLAB matrix loader (`mat_reader.py`) and associated `.mat` ingestion branches.
- Nuitka prototype build scripts and packaging dependencies.

### Changed
- Refactored Excorde 3C unit tests into `test_pipeline.py`.
- Modernized package metadata to strict PEP 639 standard.

### Fixed
- Fixed Debian packaging requirement by providing formal `CHANGELOG.md`.
- Fixed macOS ARM64 SciPy wheel installation via `min_os_version = "13.0"`.
- Fixed Windows WiX XML entity parsing by replacing raw ampersand in description.
- Fixed Linux system Python version alignment in GitHub Actions CI.

## [0.2.0] - 2026-10-28

### Added
- Rebranded and redesigned from PyECG to Repolaris.
- Universal zero-dependency multi-format ingestion (ISHNE 1.0, PhysioNet WFDB, EDF/EDF+, Excorde 3C).
- High-performance 60fps PyQtGraph GUI workstation with real-time digital calipers.
- Portable Clinical ECG (`.pecg`) container format with Zstandard compression.
- Clinical Events Triage Diary and immutable AnnotationManager with audit trails.
- Multi-language internationalization (English, Spanish, French, German).
- Automated 31-case verification test suite.

## [0.1.0] - 2018-06-01

### Added
- Foundational PyECG research software (Suárez-León et al., Universidad de Oriente / KU Leuven).
- Rate-corrected QT formulas (Bazett, Fridericia, Framingham, Hodges).
- Berger QT Variability Index (QTVI) and 4 Hz uniform step-integration resampling.
