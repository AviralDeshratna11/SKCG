from __future__ import annotations

from sckg.graph.store import GraphStore
from sckg.ir.enums import RelationType


class GraphQueries:
    def __init__(self, store: GraphStore) -> None:
        self.store = store

    def find_symbol(self, query: str):
        return self.store.find_symbol(query)

    def get_definition(self, symbol: str):
        return self.store.get_definition(symbol)

    def get_references(self, symbol: str):
        return self.store.get_references(symbol)

    def get_callers(self, symbol: str):
        return self.store.get_callers(symbol)

    def get_callees(self, symbol: str):
        return self.store.get_callees(symbol)

    def get_neighbors(self, symbol: str, relation_types: list[RelationType] | None = None, depth: int = 1):
        return self.store.get_neighbors(symbol, relation_types, depth)
