from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from sckg.indexing.ignore import should_ignore


def discover_files(root: Path, suffixes: Iterable[str]) -> list[Path]:
    suffix_set = set(suffixes)
    files: list[Path] = []
    for path in root.rglob("*"):
        if should_ignore(path, root):
            continue
        if path.is_file() and path.suffix in suffix_set:
            files.append(path)
    return sorted(files)
