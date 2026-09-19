from __future__ import annotations

from pathlib import Path

from sckg.graph.store import GraphStore
from sckg.retrieval.pipeline import RetrievalPipeline


class SCKGTools:
    def __init__(self, store: GraphStore, repo_path: Path) -> None:
        self.store = store
        self.repo_path = repo_path

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

    def get_neighbors(self, symbol: str, relation_types=None, depth: int = 1):
        return self.store.get_neighbors(symbol, relation_types, depth)

    def get_file_symbols(self, path: str):
        return self.store.get_file_symbols(path)

    def search_code(self, query: str):
        return self.store.find_symbol(query)

    def get_subgraph(self, seed_symbols: list[str], relations=None, depth: int = 1):
        return self.store.get_subgraph(seed_symbols, relations, depth)

    def explain_path(self, source: str, target: str):
        return self.store.explain_path(source, target)

    def retrieve_context(self, issue: str, token_budget: int = 8000) -> str:
        return RetrievalPipeline(self.store, self.repo_path).retrieve(issue, token_budget).context
