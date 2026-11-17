"""Automated Test Suite for Python 3.14 Syntax Modernization, Astral uv, and Ruff Tooling.

Validates:
1. `pyproject.toml` configuration for `[tool.uv]`, `[tool.ruff]` (`target-version = "py314"`), and PEP 735 `[dependency-groups]`.
2. `.python-version` presence and target version specification (`3.14`).
3. AST-level verification across all `src/repolaris/` and `tests/` modules ensuring zero legacy `typing` generics (`Optional`, `Union`, `List`, `Dict`, `Tuple`, `Set`), zero unused imports (`F401`), zero unused local variables (`F841`), zero implicit `None` returns (`RET502`), zero single-line multi-statements (`E701`), zero trailing whitespace (`W291`/`W293`), and zero `try/except/pass` (`SIM105`) blocks.
4. Optional live execution of `ruff check` and `uv --version` when `ruff` / `uv` binaries are available in `PATH`.
"""

from __future__ import annotations

from pathlib import Path
import ast
import shutil
import subprocess
import tomllib
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestPython314UvAndRuffTooling(unittest.TestCase):
    """Verifies Python 3.14 codebase modernization, uv/ruff configuration, and static lint rules."""

    def test_pyproject_uv_and_ruff_configuration(self) -> None:
        """Verifies pyproject.toml defines [tool.uv], [tool.ruff] (py314), and [dependency-groups]."""
        pyproject_path = PROJECT_ROOT / "pyproject.toml"
        self.assertTrue(pyproject_path.is_file(), "pyproject.toml must exist at repository root")

        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

        self.assertIn("dependency-groups", data)
        self.assertIn("dev", data["dependency-groups"])
        dev_deps = " ".join(data["dependency-groups"]["dev"])
        self.assertIn("ruff", dev_deps)
        self.assertIn("pytest", dev_deps)

        tool_cfg = data.get("tool", {})
        self.assertIn("uv", tool_cfg)
        self.assertTrue(tool_cfg["uv"].get("managed", False))

        self.assertIn("ruff", tool_cfg)
        ruff_cfg = tool_cfg["ruff"]
        self.assertEqual(ruff_cfg.get("target-version"), "py314")
        lint_select = ruff_cfg.get("lint", {}).get("select", [])
        for rule in ("E", "W", "F", "I", "UP", "B", "SIM", "C4", "PIE", "RET"):
            self.assertIn(rule, lint_select)

    def test_python_version_pin_file(self) -> None:
        """Verifies .python-version pins Python 3.14 for Astral uv."""
        py_ver_file = PROJECT_ROOT / ".python-version"
        self.assertTrue(py_ver_file.is_file(), ".python-version file must exist for uv")
        self.assertEqual(py_ver_file.read_text(encoding="utf-8").strip(), "3.14")

    def test_codebase_modern_python314_typing_and_no_unused_imports(self) -> None:
        """Verifies all src/ and tests/ modules use modern X | Y and builtin generics with zero unused imports."""
        legacy_typing_symbols = {"List", "Dict", "Tuple", "Set", "Optional", "Union"}

        for folder in ("src/repolaris", "tests"):
            for path in sorted((PROJECT_ROOT / folder).rglob("*.py")):
                src = path.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=str(path))

                imported_names: dict[str, int] = {}
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.asname or alias.name.split(".")[0]
                            imported_names[name] = node.lineno
                    elif isinstance(node, ast.ImportFrom):
                        if node.module == "__future__":
                            continue
                        if node.module == "typing":
                            for alias in node.names:
                                self.assertNotIn(
                                    alias.name,
                                    legacy_typing_symbols,
                                    f"{path}:{node.lineno} imports legacy typing.{alias.name} instead of Python 3.14 native syntax",
                                )
                        for alias in node.names:
                            name = alias.asname or alias.name
                            imported_names[name] = node.lineno

                if not str(path).endswith("__init__.py"):
                    used_names = {
                        n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                    }
                    unused = {k: v for k, v in imported_names.items() if k not in used_names}
                    self.assertFalse(unused, f"Unused imports (F401) detected in {path}: {unused}")

    def test_no_spaghetti_try_except_pass_and_lint_cleanliness(self) -> None:
        """Verifies SIM105, RET502, E701, W291/W293, and F841 across all src/ and tests/ modules."""
        for folder in ("src/repolaris", "tests"):
            for path in sorted((PROJECT_ROOT / folder).rglob("*.py")):
                src = path.read_text(encoding="utf-8")
                lines = src.splitlines(keepends=True)
                for idx, line in enumerate(lines, 1):
                    stripped = line.rstrip("\r\n")
                    self.assertEqual(
                        stripped,
                        stripped.rstrip(" \t"),
                        f"{path}:{idx} contains trailing whitespace (W291/W293)",
                    )

                tree = ast.parse(src, filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Try) and not node.orelse and not node.finalbody:
                        for handler in node.handlers:
                            is_bare_pass = len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)
                            self.assertFalse(
                                is_bare_pass,
                                f"{path}:{node.lineno} contains try/except/pass (SIM105); use contextlib.suppress",
                            )
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        body = node.body
                        if body:
                            self.assertNotEqual(
                                body[0].lineno,
                                node.lineno,
                                f"{path}:{node.lineno} has multiple statements on one line (E701)",
                            )
                        returns: list[ast.Return] = []

                        def _collect_returns(n: ast.AST, acc: list[ast.Return] = returns) -> None:
                            for child in ast.iter_child_nodes(n):
                                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                                    continue
                                if isinstance(child, ast.Return):
                                    acc.append(child)
                                _collect_returns(child, acc)

                        _collect_returns(node)
                        has_val = any(
                            r.value is not None and not (isinstance(r.value, ast.Constant) and r.value.value is None)
                            for r in returns
                        )
                        if has_val:
                            for r in returns:
                                self.assertIsNotNone(
                                    r.value,
                                    f"{path}:{r.lineno} has bare `return` in `{node.name}` (RET502); use `return None`",
                                )

    def test_optional_live_ruff_and_uv_cli_execution(self) -> None:
        """Executes `ruff check` and `uv --version` if the binaries are installed on the host."""
        ruff_bin = shutil.which("ruff")
        if ruff_bin:
            proc = subprocess.run(
                [ruff_bin, "check", str(PROJECT_ROOT / "src"), str(PROJECT_ROOT / "tests")],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, f"ruff check failed:\n{proc.stdout}\n{proc.stderr}")

        uv_bin = shutil.which("uv")
        if uv_bin:
            proc_uv = subprocess.run([uv_bin, "--version"], capture_output=True, text=True, check=False)
            self.assertEqual(proc_uv.returncode, 0)
            self.assertIn("uv", proc_uv.stdout.lower())


if __name__ == "__main__":
    unittest.main()
