from __future__ import annotations

from sckg.graph.json_store import JsonGraphStore
from sckg.graph.store import GraphStore


class HubSuppressor:
    """Count distinct incoming neighbours; self loops are not hub evidence.

    Instances are scoped to a retrieval so mutations between queries are reflected.
    """

    def __init__(self, store: GraphStore, enabled: bool = True, threshold: int = 10) -> None:
        if threshold < 1:
            raise ValueError("hub_degree_threshold must be positive")
        self.store = store
        self.enabled = enabled
        self.threshold = threshold
        self.suppressed: set[str] = set()
        self._degrees: dict[str, int] = {}
        if enabled and isinstance(store, JsonGraphStore):
            incoming: dict[str, set[str]] = {}
            for edge in store.relations.values():
                if edge.source_symbol_id != edge.target_symbol_id:
                    incoming.setdefault(edge.target_symbol_id, set()).add(edge.source_symbol_id)
            self._degrees = {key: len(value) for key, value in incoming.items()}

    def in_degree(self, symbol_id: str) -> int:
        if symbol_id not in self._degrees:
            if isinstance(self.store, JsonGraphStore):
                self._degrees[symbol_id] = 0
            else:
                _, edges = self.store.get_neighbors(symbol_id, depth=1)
                self._degrees[symbol_id] = len({
                    edge.source_symbol_id for edge in edges
                    if edge.target_symbol_id == symbol_id and edge.source_symbol_id != symbol_id
                })
        return self._degrees[symbol_id]

    def is_hub(self, symbol_id: str) -> bool:
        suppressed = self.enabled and self.in_degree(symbol_id) > self.threshold
        if suppressed:
            self.suppressed.add(symbol_id)
        return suppressed

    def discount(self, symbol_id: str) -> float:
        return self.threshold / self.in_degree(symbol_id) if self.is_hub(symbol_id) else 1.0
