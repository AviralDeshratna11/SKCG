from pathlib import Path

from sckg.frontends.python import PythonFrontend
from sckg.graph.builder import GraphBuilder
from sckg.graph.json_store import JsonGraphStore


def test_json_graph_store_is_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def f():\n    return 1\n\ndef g():\n    return f()\n", encoding="utf-8")
    store = JsonGraphStore(tmp_path / "graph.json")
    doc = PythonFrontend().index_repository(repo, repository_identity="fixture")
    first = GraphBuilder(store).build(doc)
    second = GraphBuilder(store).build(doc)
    assert first == second
    assert store.stats()["symbols"] == len(doc.symbols)
    assert store.get_callees("a.g")[0].qualified_name == "a.f"


def test_json_graph_store_replaces_stale_document_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "a.py"
    source.write_text("def old():\n    return 1\n", encoding="utf-8")
    store = JsonGraphStore(tmp_path / "graph.json")
    GraphBuilder(store).build(PythonFrontend().index_repository(repo, repository_identity="fixture"))
    assert store.find_symbol("a.old")

    source.write_text("def new():\n    return 2\n", encoding="utf-8")
    GraphBuilder(store).build(PythonFrontend().index_repository(repo, repository_identity="fixture"))
    assert not store.find_symbol("a.old")
    assert store.find_symbol("a.new")
