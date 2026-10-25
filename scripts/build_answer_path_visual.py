"""Create a focused, replayable view of the recorded contract consumer answer."""

from __future__ import annotations

import json
from pathlib import Path

from sckg.graph.json_store import JsonGraphStore
from sckg.ir.enums import RelationType
from sckg.visualization.export import write_graph_html


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "output" / "graph" / "sample-workspace.json"
TRACE = ROOT / "output" / "graph" / "sample-egpot-trace.json"
OUTPUT = ROOT / "output" / "graph" / "multi-repo-answer-path.html"


def main() -> None:
    store = JsonGraphStore(GRAPH)
    trace = json.loads(TRACE.read_text(encoding="utf-8"))
    paths = []
    for path in trace["trajectories"]:
        for index, edge_id in enumerate(path["edges"]):
            if store.relations[edge_id].relation_type == RelationType.CONSUMES:
                paths.append({
                    "nodes": path["nodes"][: index + 2],
                    "edges": path["edges"][: index + 1],
                    "objectives": path["objectives"][: index + 1],
                })
                break
    if not paths:
        raise ValueError("recorded traversal has no CONSUMES path")
    answer = min(paths, key=lambda path: (len(path["edges"]), path["nodes"]))
    focused = {**trace, "trajectories": [answer],
               "selected_nodes": answer["nodes"], "selected_edges": answer["edges"],
               "seeds": [node for node in trace["seeds"] if node in answer["nodes"]]}
    write_graph_html(OUTPUT, list(store.symbols.values()), list(store.relations.values()),
                     "Which service consumes ShippingService.GetQuote?", focused)
    print(f"wrote {OUTPUT} with {len(answer['nodes'])} answer nodes and "
          f"{len(answer['edges'])} answer edge")


if __name__ == "__main__":
    main()
