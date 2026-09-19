from __future__ import annotations

from pathlib import Path

DEFAULT_IGNORES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def should_ignore(path: Path, root: Path, ignore_names: set[str] | None = None) -> bool:
    ignores = ignore_names or DEFAULT_IGNORES
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(part in ignores for part in relative.parts)
