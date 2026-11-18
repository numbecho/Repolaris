# Developer and Contributing Guide

This guide describes development workflows, coding standards, automated testing, and release procedures for Repolaris.

---

## 1. Development Environment Setup

We recommend using [Astral `uv`](https://astral.sh/uv) for fast environment setup:

```bash
# Clone the repository
git clone https://github.com/numbecho/repolaris.git
cd repolaris

# Provision Python 3.14 and sync environment
uv python install 3.14
uv sync --all-extras --dev
```

---

## 2. Code Quality & Formatting (`ruff`)

Repolaris strictly adheres to modern Python packaging (PEP 517/621/639) and uses [Astral `ruff`](https://astral.sh/ruff) for linting and formatting.

### Run Linter
```bash
uv run ruff check src tests
```

### Auto-Fix Formatting
```bash
uv run ruff check --fix src tests
uv run ruff format src tests
```

### Configuration (`pyproject.toml`)
```toml
[tool.ruff]
line-length = 100
target-version = "py314"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "SIM", "C4", "PIE", "RET"]
ignore = ["E501"]
```

---

## 3. UI Layout & Precompilation (`app.ui`)

The workstation graphical layout is designed in Qt 6 Designer and stored in XML format at `src/repolaris/resources/app.ui`. For fast startup and static IDE type safety, it is precompiled to native Python at `src/repolaris/resources/ui_app.py`.

### Recompiling UI Layouts
Whenever you modify `app.ui` in Qt Designer, recompile the Python presentation module using either method:

```bash
# Automated compiler (auto-detects pyuic6 or falls back to built-in generator)
python -m repolaris.resources.compile_ui

# Or using standard pyuic6 CLI
pyuic6 src/repolaris/resources/app.ui -o src/repolaris/resources/ui_app.py
```

---

## 4. Strict Type Safety (PEP 484 / 585 / 604)

All new code must include static type annotations:
* Use modern union operators (`int | float | None` or `Optional[Union[...]]` with `from __future__ import annotations`).
* Verify with `mypy`:
  ```bash
  uv run mypy src/repolaris
  ```

---

## 5. Automated Testing

All pull requests must pass the complete 104-test unit test suite:

```bash
# Run with Python unittest (headless-safe)
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m unittest discover tests -v

# Or run with Astral uv & pytest
QT_QPA_PLATFORM=offscreen uv run pytest -v

# Run dedicated uv & ruff tooling verification suite
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m unittest tests/test_tooling_uv_ruff.py -v
```

### Adding New Test Cases
Place unit tests in `tests/test_*.py`. Use synthetic ECG generators (`repolaris.utils.signal.generate_synthetic_ecg` or `StudyAPI.generate_demo_study`) to create reproducible test fixtures with known heart rates and QT durations.

---

## 6. Syncing Wiki with GitHub

The wiki documentation files in `wiki/` (mirrored in `docs/wiki/`) are formatted for GitHub Wikis. To publish or synchronize updates:

```bash
# Clone your repository's wiki git repository
git clone https://github.com/numbecho/repolaris.wiki.git

# Copy all wiki files from the repository's wiki/ directory
cp -r wiki/* repolaris.wiki/

# Commit and push
cd repolaris.wiki
git add .
git commit -m "Update Repolaris documentation wiki"
git push origin master
```
