"""Query-scoped adjacency: O(E) construction, O(degree) expansion.

The snapshot is rebuilt for each query so mutable JSON stores never leave stale indexes.
Parallel relation evidence is retained in storage and collapsed only for scoring.
"""
from __future__ import annotations

from collections import defaultdict

from sckg.graph.json_store import JsonGraphStore
from sckg.graph.store import GraphStore
from sckg.ir.models import Relation


class Adjacency:
    def __init__(self, store: GraphStore) -> None:
        self.store = store
        self.incident: dict[str, list[Relation]] | None = None
        if isinstance(store, JsonGraphStore):
            self.incident = defaultdict(list)
            for relation in store.relations.values():
                self.incident[relation.source_symbol_id].append(relation)
                if relation.target_symbol_id != relation.source_symbol_id:
                    self.incident[relation.target_symbol_id].append(relation)

    def edges(self, node_id: str) -> list[Relation]:
        if self.incident is not None:
            return self.incident.get(node_id, [])
        return self.store.get_neighbors(node_id, depth=1)[1]
