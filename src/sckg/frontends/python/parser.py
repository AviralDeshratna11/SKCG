from __future__ import annotations

import ast
from pathlib import Path


def parse_python(path: Path) -> ast.Module:
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path), type_comments=True)
