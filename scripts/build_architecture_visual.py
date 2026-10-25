"""Export a readable view of SCKG's build and EG-POT implementation graph."""

from __future__ import annotations

from pathlib import Path

from sckg.graph.json_store import JsonGraphStore
from sckg.visualization.export import write_graph_html


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "output" / "graph" / "sckg-graft.json"
OUTPUT = ROOT / "output" / "graph" / "sckg-architecture.html"
PREFIXES = (
    "src/sckg/indexing/", "src/sckg/graph/", "src/sckg/ir/",
    "src/sckg/retrieval/egpot/",
)
EXACT = {
    "src/sckg/graft/adapter.py", "src/sckg/cli/main.py",
    "src/sckg/visualization/export.py",
}
KINDS = {"file", "class", "function", "method", "module"}


def main() -> None:
    store = JsonGraphStore(STORE)
    symbols = [
        symbol for symbol in store.symbols.values()
        if (symbol.file_path.startswith(PREFIXES) or symbol.file_path in EXACT)
        and symbol.kind.value in KINDS
    ]
    ids = {symbol.id for symbol in symbols}
    relations = [
        relation for relation in store.relations.values()
        if relation.source_symbol_id in ids and relation.target_symbol_id in ids
    ]
    write_graph_html(OUTPUT, symbols, relations, "SCKG: GRAFT Build and EG-POT Architecture")
    print(f"wrote {OUTPUT} with {len(symbols)} nodes and {len(relations)} relations")


if __name__ == "__main__":
    main()
