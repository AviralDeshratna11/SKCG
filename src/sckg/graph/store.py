from __future__ import annotations

from abc import ABC, abstractmethod

from sckg.ir.enums import RelationType
from sckg.ir.models import FileNode, LNIRDocument, Relation, RepositoryNode, Symbol


class GraphStore(ABC):
    @abstractmethod
    def upsert_repository(self, repository: RepositoryNode) -> None: ...

    @abstractmethod
    def upsert_file(self, file: FileNode) -> None: ...

    @abstractmethod
    def upsert_symbol(self, symbol: Symbol) -> None: ...

    def upsert_symbols(self, symbols: list[Symbol]) -> None:
        for symbol in symbols:
            self.upsert_symbol(symbol)

    @abstractmethod
    def upsert_relation(self, relation: Relation) -> None: ...

    def upsert_relations(self, relations: list[Relation]) -> None:
        for relation in relations:
            self.upsert_relation(relation)

    @abstractmethod
    def find_symbol(self, query: str, limit: int = 20) -> list[Symbol]: ...

    @abstractmethod
    def get_symbol(self, symbol: str) -> Symbol | None: ...

    @abstractmethod
    def get_neighbors(
        self, symbol: str, relation_types: list[RelationType] | None = None, depth: int = 1
    ) -> tuple[list[Symbol], list[Relation]]: ...

    @abstractmethod
    def get_callers(self, symbol: str) -> list[Symbol]: ...

    @abstractmethod
    def get_callees(self, symbol: str) -> list[Symbol]: ...

    @abstractmethod
    def get_references(self, symbol: str) -> list[Symbol]: ...

    @abstractmethod
    def get_definition(self, symbol: str) -> Symbol | None: ...

    @abstractmethod
    def get_file_symbols(self, path: str) -> list[Symbol]: ...

    @abstractmethod
    def get_subgraph(
        self, seeds: list[str], relations: list[RelationType] | None = None, depth: int = 1
    ) -> tuple[list[Symbol], list[Relation]]: ...

    @abstractmethod
    def explain_path(self, source: str, target: str, max_depth: int = 4) -> list[Relation]: ...

    @abstractmethod
    def stats(self) -> dict[str, int]: ...


def upsert_document(store: GraphStore, document: LNIRDocument) -> None:
    replace_document = getattr(store, "replace_document", None)
    if callable(replace_document):
        replace_document(document)
        return
    store.upsert_repository(document.repository)
    for file in document.files:
        store.upsert_file(file)
    store.upsert_symbols(document.symbols)
    store.upsert_relations(document.relations)
