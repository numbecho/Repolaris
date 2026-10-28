# Developer and Contributing Guide

This guide describes development workflows, coding standards, automated testing, and release procedures for Repolaris.

---

## 1. Development Environment Setup

We recommend using [Astral `uv`](https://astral.sh/uv) for fast environment setup:

```bash
# Clone the repository
git clone https://github.com/numbecho/repolaris.git
cd repolaris

# Create virtual environment and install development dependencies
uv venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
uv pip install -e ".[gui,wfdb,dev]"
```

---

## 2. Code Quality & Formatting (`ruff`)

Repolaris strictly adheres to modern Python packaging (PEP 517/621) and uses [Astral `ruff`](https://astral.sh/ruff) for linting and formatting.

### Run Linter
```bash
ruff check .
```

### Auto-Fix Formatting
```bash
ruff check --fix .
ruff format .
```

### Configuration (`pyproject.toml`)
```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "SIM"]
ignore = ["E501"]
```

---

## 3. Strict Type Safety (PEP 484 / 585 / 604)

All new code must include static type annotations:
* Use modern union operators (`int | float | None` instead of `Optional[Union[int, float]]`).
* Use built-in generic collections (`list[str]`, `dict[str, Any]` instead of `typing.List`).
* Verify with `mypy`:
  ```bash
  mypy src/repolaris
  ```

---

## 4. Automated Testing

All pull requests must pass the complete unit test suite:

```bash
# Run with Python unittest
python3 -m unittest discover tests

# Or run with pytest
pytest tests/ -v
```

### Adding New Test Cases
Place unit tests in `tests/test_*.py`. Use synthetic ECG generators (`repolaris.utils.signal.generate_synthetic_ecg`) to create reproducible test fixtures with known heart rates and QT durations.

---

## 5. Syncing Wiki with GitHub

The wiki documentation files in this directory are formatted for GitHub Wikis. To publish or synchronize updates:

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
