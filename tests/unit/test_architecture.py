import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "livestocks"

# Subsystem -> the subsystems and shared modules it may import (top-level modules may import all).
ALLOWED = {
    "domain": set(),
    "crawler": {"domain"},
    "storage": {"domain"},
    "services": {"domain", "crawler", "storage", "config"},
    "api": {"domain", "services", "config"},
    "ui": {"domain", "services", "config"},
}
FIXED_FILES = ("__init__.py", "models.py", "errors.py")


def subsystems() -> list[str]:
    return sorted(p.name for p in SRC.iterdir() if p.is_dir() and (p / "__init__.py").exists())


def imported_modules(path: Path) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{path}:{node.lineno} uses a relative import"
            found.append((node.lineno, node.module or ""))
    return [(line, m) for line, m in found if m == "livestocks" or m.startswith("livestocks.")]


def violations(root: Path, allowed: dict[str, set[str]]) -> list[str]:
    problems = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        owner = relative.parts[0] if len(relative.parts) > 1 else None
        for line, module in imported_modules(path):
            parts = module.split(".")
            target = parts[1] if len(parts) > 1 else None
            if owner is None or target is None or target == owner:
                continue
            where = f"{relative}:{line} imports {module}"
            if target not in allowed[owner]:
                problems.append(f"{where}: {owner} must not depend on {target}")
            elif target in allowed and len(parts) > 2:
                problems.append(
                    f"{where}: import from the package root livestocks.{target} instead"
                )
    return problems


class TestLayering:
    def test_source_tree_respects_the_layer_rules(self):
        assert violations(SRC, ALLOWED) == []

    def test_a_ui_import_of_storage_is_reported(self, tmp_path):
        (tmp_path / "ui").mkdir()
        (tmp_path / "ui" / "pages.py").write_text("from livestocks.storage import Store\n")

        page = Path("ui") / "pages.py"
        assert violations(tmp_path, ALLOWED) == [
            f"{page}:1 imports livestocks.storage: ui must not depend on storage"
        ]

    def test_a_deep_cross_package_import_is_reported(self, tmp_path):
        (tmp_path / "services").mkdir()
        (tmp_path / "services" / "forecasts.py").write_text(
            "from livestocks.storage.store import Store\n"
        )

        [problem] = violations(tmp_path, ALLOWED)

        assert "import from the package root livestocks.storage" in problem

    def test_imports_inside_one_package_may_name_modules(self, tmp_path):
        (tmp_path / "crawler").mkdir()
        (tmp_path / "crawler" / "pipeline.py").write_text(
            "from livestocks.crawler.errors import CrawlError\n"
        )

        assert violations(tmp_path, ALLOWED) == []


class TestFixedFiles:
    @pytest.mark.parametrize("subsystem", subsystems())
    def test_every_subsystem_has_init_models_and_errors(self, subsystem):
        missing = [name for name in FIXED_FILES if not (SRC / subsystem / name).exists()]

        assert missing == []

    def test_every_subsystem_is_covered_by_the_layer_rules(self):
        assert set(subsystems()) <= set(ALLOWED)

    def test_no_relative_imports_anywhere(self):
        for path in SRC.rglob("*.py"):
            imported_modules(path)  # asserts on any relative import
