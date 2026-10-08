"""Check that public code in src/ follows the project docstring format.
Every public module, class, function and method needs a docstring of exactly three lines of prose
with no Args/Returns/Raises/Yields sections. Exit status 1 lists every violation.
"""

import ast
import sys
from pathlib import Path

SECTIONS = (
    "Args:",
    "Returns:",
    "Raises:",
    "Yields:",
    "Attributes:",
    "Example:",
    "Examples:",
    "Note:",
)
LINES = 3


def prose_lines(docstring: str) -> list[str]:
    """Return the non-empty lines of a docstring, stripped."""
    return [line.strip() for line in docstring.strip().splitlines() if line.strip()]


def check_docstring(label: str, docstring: str | None) -> list[str]:
    """Return the problems found in one docstring, or an empty list."""
    if docstring is None:
        return [f"{label}: missing docstring"]
    lines = prose_lines(docstring)
    problems = []
    if len(lines) != LINES:
        problems.append(f"{label}: docstring has {len(lines)} lines of prose, expected {LINES}")
    if any(line.startswith(SECTIONS) for line in lines):
        problems.append(f"{label}: docstring must not contain Args/Returns/Raises sections")
    return problems


def public_nodes(tree: ast.Module):
    """Yield (name, node) for module-level classes, functions and public methods."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name.startswith("_"):
                continue
            yield node.name, node
            if isinstance(node, ast.ClassDef):
                for member in node.body:
                    if isinstance(
                        member, ast.FunctionDef | ast.AsyncFunctionDef
                    ) and not member.name.startswith("_"):
                        yield f"{node.name}.{member.name}", member


def check_file(path: Path) -> list[str]:
    """Return every docstring problem in one source file."""
    tree = ast.parse(path.read_text(encoding="utf8"))
    problems = check_docstring(f"{path}", ast.get_docstring(tree, clean=False))
    for name, node in public_nodes(tree):
        problems += check_docstring(
            f"{path}:{node.lineno} {name}", ast.get_docstring(node, clean=False)
        )
    return problems


def main(argv: list[str]) -> int:
    """Check the given files, or every .py file under src/ when none are given."""
    files = [Path(a) for a in argv] or sorted(Path("src").rglob("*.py"))
    problems = [p for f in files if f.suffix == ".py" for p in check_file(f)]
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
