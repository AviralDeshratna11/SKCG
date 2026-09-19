from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sckg.frontends.python import PythonFrontend
from sckg.graph.builder import GraphBuildReport, GraphBuilder
from sckg.graph.store import GraphStore
from sckg.indexing.manifest import create_manifest
from sckg.ir.models import IndexManifest, LNIRDocument


@dataclass(frozen=True)
class IndexReport:
    document: LNIRDocument
    build: GraphBuildReport
    manifest: IndexManifest


class IndexingPipeline:
    def __init__(self, store: GraphStore, config: dict[str, object] | None = None) -> None:
        self.store = store
        self.config = config or {}
        self.frontend = PythonFrontend()

    def index(self, repo_path: Path) -> IndexReport:
        document = self.frontend.index_repository(repo_path)
        build = GraphBuilder(self.store).build(document)
        manifest = create_manifest(document, self.config)
        return IndexReport(document=document, build=build, manifest=manifest)
