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
        architecture = self.config.get("architecture", "lnir")
        if architecture == "graft":
            from sckg.graft.adapter import graph_to_document
            try:
                from sckg.graft.graft_ckg import CKGBuilder
            except ImportError as exc:
                raise RuntimeError('GRAFT build needs: pip install -e ".[graft]"') from exc
            builder = CKGBuilder(str(repo_path))
            graph = builder.build()
            if self.config.get("lineage"):
                from sckg.graft.lineage import LineageLayer
                LineageLayer(builder).ingest(max_commits=int(self.config.get("max_commits", 200)))
            document = graph_to_document(graph, repo_path)
        elif architecture == "lnir":
            document = self.frontend.index_repository(repo_path)
        else:
            raise ValueError(f"unknown graph architecture: {architecture}")
        build = GraphBuilder(self.store).build(document)
        manifest = create_manifest(document, self.config)
        return IndexReport(document=document, build=build, manifest=manifest)

    def index_workspace(self, workspace_path: Path) -> IndexReport:
        from sckg.graft.adapter import graph_to_document
        try:
            from sckg.graft.multi_repo import WorkspaceCKGBuilder
        except ImportError as exc:
            raise RuntimeError('GRAFT workspace build needs: pip install -e ".[graft]"') from exc
        builder = WorkspaceCKGBuilder(str(workspace_path))
        graph = builder.build()
        if self.config.get("lineage"):
            from sckg.graft.lineage import LineageLayer
            for repo_builder in builder.repo_builders.values():
                LineageLayer(repo_builder).ingest(max_commits=int(self.config.get("max_commits", 200)))
                for node, data in repo_builder.graph.nodes(data=True):
                    if data.get("layer") == "Llineage":
                        graph.add_node(node, **data)
                for source, target, key, data in repo_builder.graph.edges(keys=True, data=True):
                    if data.get("layer") == "Llineage":
                        graph.add_edge(source, target, key=f"lineage_{repo_builder.repo_id}_{key}",
                                       **data)
        source_roots = {repo.id: Path(builder._resolve_path(repo.path))
                        for repo in builder.config.repositories}
        document = graph_to_document(graph, workspace_path.parent,
                                     identity=str(workspace_path.resolve()),
                                     source_roots=source_roots)
        build = GraphBuilder(self.store).build(document)
        manifest = create_manifest(document, {**self.config, "architecture": "graft-workspace"})
        return IndexReport(document=document, build=build, manifest=manifest)
