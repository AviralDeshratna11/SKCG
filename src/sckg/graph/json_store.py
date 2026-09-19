from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

from sckg.graph.store import GraphStore
from sckg.ir.enums import RelationType
from sckg.ir.models import FileNode, LNIRDocument, Relation, RepositoryNode, Symbol


class JsonGraphStore(GraphStore):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.repositories: dict[str, RepositoryNode] = {}
        self.files: dict[str, FileNode] = {}
        self.symbols: dict[str, Symbol] = {}
        self.relations: dict[str, Relation] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.repositories = {
            item["id"]: RepositoryNode.model_validate(item) for item in data.get("repositories", [])
        }
        self.files = {item["id"]: FileNode.model_validate(item) for item in data.get("files", [])}
        self.symbols = {item["id"]: Symbol.model_validate(item) for item in data.get("symbols", [])}
        self.relations = {
            item["id"]: Relation.model_validate(item) for item in data.get("relations", [])
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "repositories": [item.model_dump(mode="json") for item in self.repositories.values()],
            "files": [item.model_dump(mode="json") for item in self.files.values()],
            "symbols": [item.model_dump(mode="json") for item in self.symbols.values()],
            "relations": [item.model_dump(mode="json") for item in self.relations.values()],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def upsert_repository(self, repository: RepositoryNode) -> None:
        self.repositories[repository.id] = repository
        self._save()

    def upsert_file(self, file: FileNode) -> None:
        self.files[file.id] = file
        self._save()

    def upsert_symbol(self, symbol: Symbol) -> None:
        self.symbols[symbol.id] = symbol
        self._save()

    def upsert_relation(self, relation: Relation) -> None:
        self.relations[relation.id] = relation
        self._save()

    def replace_document(self, document: LNIRDocument) -> None:
        repo_id = document.repository.id
        commit_id = document.repository.commit_id
        self.repositories[repo_id] = document.repository
        self.files = {
            key: value
            for key, value in self.files.items()
            if not (value.repository_id == repo_id and value.commit_id == commit_id)
        }
        self.symbols = {
            key: value
            for key, value in self.symbols.items()
            if not (value.repository_id == repo_id and value.commit_id == commit_id)
        }
        self.relations = {
            key: value
            for key, value in self.relations.items()
            if not (value.repository_id == repo_id and value.commit_id == commit_id)
        }
        self.files.update({file.id: file for file in document.files})
        self.symbols.update({symbol.id: symbol for symbol in document.symbols})
        self.relations.update({relation.id: relation for relation in document.relations})
        self._save()

    def find_symbol(self, query: str, limit: int = 20) -> list[Symbol]:
        query_lower = query.lower()
        scored = []
        for symbol in self.symbols.values():
            haystack = f"{symbol.qualified_name} {symbol.name} {symbol.file_path}".lower()
            if query_lower in haystack:
                scored.append((0 if symbol.qualified_name.lower() == query_lower else 1, symbol))
        return [symbol for _, symbol in sorted(scored, key=lambda item: (item[0], item[1].qualified_name))[:limit]]

    def get_symbol(self, symbol: str) -> Symbol | None:
        if symbol in self.symbols:
            return self.symbols[symbol]
        matches = self.find_symbol(symbol, limit=1)
        return matches[0] if matches else None

    def get_neighbors(
        self, symbol: str, relation_types: list[RelationType] | None = None, depth: int = 1
    ) -> tuple[list[Symbol], list[Relation]]:
        start = self.get_symbol(symbol)
        if start is None:
            return [], []
        allowed = set(relation_types) if relation_types else None
        seen = {start.id}
        queue: deque[tuple[str, int]] = deque([(start.id, 0)])
        relation_hits: dict[str, Relation] = {}
        while queue:
            current, distance = queue.popleft()
            if distance >= depth:
                continue
            for relation in self.relations.values():
                if allowed and relation.relation_type not in allowed:
                    continue
                if relation.source_symbol_id == current:
                    neighbor = relation.target_symbol_id
                elif relation.target_symbol_id == current:
                    neighbor = relation.source_symbol_id
                else:
                    continue
                relation_hits[relation.id] = relation
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, distance + 1))
        return [self.symbols[item] for item in seen if item in self.symbols], list(relation_hits.values())

    def get_callers(self, symbol: str) -> list[Symbol]:
        target = self.get_symbol(symbol)
        if target is None:
            return []
        return [
            self.symbols[relation.source_symbol_id]
            for relation in self.relations.values()
            if relation.relation_type == RelationType.CALLS
            and relation.target_symbol_id == target.id
            and relation.source_symbol_id in self.symbols
        ]

    def get_callees(self, symbol: str) -> list[Symbol]:
        source = self.get_symbol(symbol)
        if source is None:
            return []
        return [
            self.symbols[relation.target_symbol_id]
            for relation in self.relations.values()
            if relation.relation_type == RelationType.CALLS
            and relation.source_symbol_id == source.id
            and relation.target_symbol_id in self.symbols
        ]

    def get_references(self, symbol: str) -> list[Symbol]:
        target = self.get_symbol(symbol)
        if target is None:
            return []
        return [
            self.symbols[relation.source_symbol_id]
            for relation in self.relations.values()
            if relation.relation_type == RelationType.REFERENCES
            and relation.target_symbol_id == target.id
            and relation.source_symbol_id in self.symbols
        ]

    def get_definition(self, symbol: str) -> Symbol | None:
        return self.get_symbol(symbol)

    def get_file_symbols(self, path: str) -> list[Symbol]:
        return [symbol for symbol in self.symbols.values() if symbol.file_path == path]

    def get_subgraph(
        self, seeds: list[str], relations: list[RelationType] | None = None, depth: int = 1
    ) -> tuple[list[Symbol], list[Relation]]:
        symbols: dict[str, Symbol] = {}
        edges: dict[str, Relation] = {}
        for seed in seeds:
            hits, rels = self.get_neighbors(seed, relations, depth)
            symbols.update({symbol.id: symbol for symbol in hits})
            edges.update({relation.id: relation for relation in rels})
        return list(symbols.values()), list(edges.values())

    def explain_path(self, source: str, target: str, max_depth: int = 4) -> list[Relation]:
        source_symbol = self.get_symbol(source)
        target_symbol = self.get_symbol(target)
        if source_symbol is None or target_symbol is None:
            return []
        queue: deque[tuple[str, list[Relation]]] = deque([(source_symbol.id, [])])
        seen = {source_symbol.id}
        while queue:
            current, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for relation in self.relations.values():
                if relation.source_symbol_id != current:
                    continue
                if relation.target_symbol_id == target_symbol.id:
                    return [*path, relation]
                if relation.target_symbol_id not in seen:
                    seen.add(relation.target_symbol_id)
                    queue.append((relation.target_symbol_id, [*path, relation]))
        return []

    def stats(self) -> dict[str, int]:
        return {
            "repositories": len(self.repositories),
            "files": len(self.files),
            "symbols": len(self.symbols),
            "relations": len(self.relations),
        }
