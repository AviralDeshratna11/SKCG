from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedTarget:
    qualified_name: str
    exact: bool


class PythonSemanticResolver:
    """Conservative module-local and import-aware resolver for Phase 1."""

    def __init__(self, known_qualified_names: set[str], imports: dict[str, str]) -> None:
        self.known_qualified_names = known_qualified_names
        self.imports = imports

    def resolve_reference(self, current_scope: str, name: str) -> ResolvedTarget | None:
        expanded = self._expand_import_alias(name)
        if expanded and expanded in self.known_qualified_names:
            return ResolvedTarget(expanded, exact=True)
        if name in self.imports:
            return ResolvedTarget(self.imports[name], exact=True)
        if name in self.known_qualified_names:
            return ResolvedTarget(name, exact=True)
        parts = current_scope.split(".")
        for index in range(len(parts), 0, -1):
            candidate = ".".join([*parts[:index], name])
            if candidate in self.known_qualified_names:
                return ResolvedTarget(candidate, exact=True)
        candidates = [qualified for qualified in self.known_qualified_names if qualified.endswith(f".{name}")]
        if len(candidates) == 1:
            return ResolvedTarget(candidates[0], exact=True)
        return None

    def resolve_call(self, current_scope: str, call_name: str) -> ResolvedTarget | None:
        return self.resolve_reference(current_scope, call_name)

    def resolve_import(self, alias: str) -> ResolvedTarget | None:
        target = self.imports.get(alias)
        return ResolvedTarget(target, exact=True) if target else None

    def resolve_type(self, current_scope: str, type_name: str) -> ResolvedTarget | None:
        return self.resolve_reference(current_scope, type_name)

    def _expand_import_alias(self, name: str) -> str | None:
        head, dot, tail = name.partition(".")
        if not dot:
            return None
        imported = self.imports.get(head)
        if not imported:
            return None
        return f"{imported}.{tail}"
