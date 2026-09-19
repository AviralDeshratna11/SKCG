from __future__ import annotations

from dataclasses import dataclass

from sckg.graph.store import GraphStore, upsert_document
from sckg.ir.models import LNIRDocument
from sckg.ir.validation import validate_unique_ids


@dataclass(frozen=True)
class GraphBuildReport:
    repositories: int
    files: int
    symbols: int
    relations: int


class GraphBuilder:
    def __init__(self, store: GraphStore) -> None:
        self.store = store

    def build(self, document: LNIRDocument) -> GraphBuildReport:
        validate_unique_ids(document)
        upsert_document(self.store, document)
        return GraphBuildReport(
            repositories=1,
            files=len(document.files),
            symbols=len(document.symbols),
            relations=len(document.relations),
        )
