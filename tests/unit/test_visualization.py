from pathlib import Path

from sckg.frontends.python import PythonFrontend
from sckg.visualization.export import graph_to_visualization, write_graph_html


def test_visualization_export_contains_graph_payload(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def f():\n    return 1\n\ndef g():\n    return f()\n", encoding="utf-8")
    document = PythonFrontend().index_repository(repo, repository_identity="fixture")
    visualization = graph_to_visualization(document.symbols, document.relations)
    assert visualization.nodes
    assert visualization.links
    output = write_graph_html(tmp_path / "graph.html", document.symbols, document.relations)
    html = output.read_text(encoding="utf-8")
    assert "Interactive semantic code graph" in html
    assert 'id="nodeList"' in html
    assert 'id="edgeList"' in html
    assert "link-hit" in html
    assert "relatedBlock" in html
    assert "details-code" in html
    assert "zoomAt(event.clientX, event.clientY" in html
    assert 'id="zoomIn"' in html
    assert 'id="egpotOnly"' in html
    assert 'id="layer"' in html
    assert "useRepulsion = activeNodes.length <= 260" in html
    assert 'return 3.8' in html
    assert "a.g" in html


def test_visualization_can_embed_egpot_trace(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def f():\n    return 1\n\ndef g():\n    return f()\n", encoding="utf-8")
    document = PythonFrontend().index_repository(repo, repository_identity="fixture")
    selected_node = document.symbols[0].id
    selected_edge = document.relations[0].id

    output = write_graph_html(
        tmp_path / "graph.html",
        document.symbols,
        document.relations,
        egpot_trace={
            "query": "trace f",
            "seeds": [selected_node],
            "selected_nodes": [selected_node],
            "selected_edges": [selected_edge],
            "objective_scores": {selected_node: [0.8, -0.1, 1.0, 0.5]},
            "stop_reason": "MAX_HOPS",
        },
    )

    html = output.read_text(encoding="utf-8")
    assert '"egpotSelected":true' in html
    assert '"egpotSeed":true' in html
    assert "EG-POT trace loaded" in html
    assert "Objectives: sem=" in html


def test_visualization_escapes_script_end_sequence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "viewer.py").write_text("def marker():\n    return '</script>'\n", encoding="utf-8")
    document = PythonFrontend().index_repository(repo, repository_identity="fixture")
    output = write_graph_html(tmp_path / "graph.html", document.symbols, document.relations)
    html = output.read_text(encoding="utf-8")
    assert "<\\/script>" in html
    assert html.count("</script>") == 1


def test_comparison_runs_and_ordered_paths_export_safely(tmp_path: Path) -> None:
    import json
    import re
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'a.py').write_text('def f(): return 1')
    document = PythonFrontend().index_repository(repo, repository_identity='fixture')
    node = document.symbols[0].id
    trace = {'selected_nodes': [node], 'seeds': [node], 'selected_edges': [],
             'trajectories': [{'nodes': [node], 'edges': [], 'objectives': []}],
             'search': {'mcts_enabled': True, 'simulations': 64,
                        'embedding_provider': 'hashing', 'hub_suppression_enabled': True,
                        'hub_degree_threshold': 10, 'suppressed_hubs': ['logger']}}
    output = write_graph_html(tmp_path / 'graph.html', document.symbols, [],
                              egpot_trace=trace, comparison_traces={'old </script>': {'selected_nodes': []}})
    text = output.read_text()
    payload = json.loads(re.search(r'const graph = (.*);', text).group(1))
    assert payload['egpot']['runs']['Current run']['trajectories'][0]['nodes'] == [node]
    assert payload['egpot']['runs']['Current run']['search']['simulations'] == 64
    assert 'old </script>' in payload['egpot']['runs']
    assert text.count('</script>') == 1
    assert 'id="runSelect"' in text
    assert 'id="hopStep"' in text
