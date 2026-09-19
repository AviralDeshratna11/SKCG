from __future__ import annotations

from dataclasses import dataclass, field

from sckg.ir.enums import SymbolKind


@dataclass(frozen=True)
class LocalSymbol:
    name: str
    qualified_name: str
    kind: SymbolKind
    line: int
    column: int
    end_line: int
    end_column: int
    signature: str | None = None
    parent_qualified_name: str | None = None
    bases: tuple[str, ...] = ()
    calls: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
