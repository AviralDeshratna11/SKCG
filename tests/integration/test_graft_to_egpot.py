from __future__ import annotations

from pathlib import Path

import pytest

from sckg.graph.json_store import JsonGraphStore
from sckg.indexing.pipeline import IndexingPipeline
from sckg.ir.enums import RelationType
from sckg.retrieval.egpot.config import EGPOTConfig


def test_graft_build_feeds_egpot(tmp_path: Path) -> None:
    pytest.importorskip("tree_sitter_javascript")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text(
        "def helper(value):\n    return value\n\n"
        "def process(value):\n    return helper(value)\n", encoding="utf-8"
    )
    store = JsonGraphStore(tmp_path / "graph.json")
    report = IndexingPipeline(store, {"architecture": "graft"}).index(repo)
    assert report.build.files == 1
    assert any(rel.relation_type == RelationType.CALLS for rel in report.document.relations)
    assert any(rel.metadata.get("layer") == "Lflow" for rel in report.document.relations)
    assert any(rel.metadata.get("hyperedge") for rel in report.document.relations)
    assert RelationType.FLOWS_TO in EGPOTConfig().allowed_edges
    assert RelationType.CONSUMES in EGPOTConfig().allowed_edges
    assert all(store.get_symbol(rel.source_symbol_id) and store.get_symbol(rel.target_symbol_id)
               for rel in report.document.relations)


def test_workspace_paths_resolve_to_source_files(tmp_path: Path) -> None:
    pytest.importorskip("tree_sitter_javascript")
    service = tmp_path / "services" / "backend"
    service.mkdir(parents=True)
    (service / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    workspace = tmp_path / "workspace.yaml"
    workspace.write_text("name: demo\nrepositories:\n  - id: backend\n    path: services/backend\n",
                         encoding="utf-8")
    store = JsonGraphStore(tmp_path / "workspace-graph.json")
    report = IndexingPipeline(store, {"architecture": "graft"}).index_workspace(workspace)
    assert any(file.normalized_path == "backend/app.py" for file in report.document.files)
    assert any(symbol.file_path == "backend/app.py" for symbol in report.document.symbols)
