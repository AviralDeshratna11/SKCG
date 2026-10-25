"""Structural traversal checks for the deployed graph; no invented relevance gold."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from sckg.graph.import_graph import import_graph, audit_graph
from sckg.graph.json_store import JsonGraphStore
from sckg.retrieval.egpot import EGPOTConfig, EGPOTTraverser
from sckg.retrieval.pipeline import RetrievalPipeline
from sckg.retrieval.seeds import Seed


def main() -> None:
    output = Path('output/benchmarks/deployed')
    output.mkdir(parents=True, exist_ok=True)
    doc = import_graph(Path('tmp/deployed-graph.json'))
    store = JsonGraphStore(output / 'graph.json')
    store.replace_document(doc)
    cfg = EGPOTConfig(embedding_provider='hashing', max_hops=3, node_budget=40)
    checks = []
    for kind in sorted({r.relation_type for r in doc.relations}):
        for direction in ['both', 'incoming', 'outgoing']:
            edge = next(e for e in doc.relations if e.relation_type == kind
                        and e.source_symbol_id != e.target_symbol_id)
            start = edge.target_symbol_id if direction == 'incoming' else edge.source_symbol_id
            symbol = store.symbols[start]
            config = replace(cfg, allowed_edges=(kind,), direction=direction,
                             hub_suppression_enabled=False)
            result = EGPOTTraverser(store, config).traverse(
                symbol.name, [Seed(symbol, 1, 0, 1, ())])
            assert result.selected_nodes
            assert len(result.visited_nodes) <= 40
            for path in result.best_trajectories:
                assert len(set(path.node_ids)) == len(path.node_ids)
                assert path.depth <= 3
                for hop in path.hops:
                    assert hop.relation.relation_type == kind
                    source, target = hop.relation.source_symbol_id, hop.relation.target_symbol_id
                    assert {source, target} == {hop.source.id, hop.target.id}
                    if direction == 'outgoing':
                        assert source == hop.source.id
                    elif direction == 'incoming':
                        assert target == hop.source.id
            checks.append({'relation': kind.value, 'direction': direction,
                           'visited': len(result.visited_nodes), 'selected': len(result.selected_nodes),
                           'stop_reason': result.stop_reason.value, 'passed': True})
    # End-to-end localization, search, context packing, and trace serialization.
    pipeline = RetrievalPipeline(store, Path('.'), {'egpot': {
        'embedding_provider': 'hashing', 'node_budget': 60}})
    retrieval = pipeline.retrieve('Where is order payment status updated?', strategy='egpot')
    assert retrieval.egpot_result and retrieval.context and retrieval.ranked_symbols
    EGPOTTraverser(store, cfg).write_trace(retrieval.egpot_result, output / 'retrieval-trace.json')
    from sckg.visualization.export import write_graph_html
    trace = json.loads((output / 'retrieval-trace.json').read_text(encoding='utf-8'))
    write_graph_html(output / 'traversal.html', list(store.symbols.values()),
                     list(store.relations.values()), 'Deployed graph: EG-POT traversal',
                     egpot_trace=trace)
    report = {'audit': audit_graph(doc), 'structural_checks': checks,
              'end_to_end': {'passed': True, 'ranked_symbols': len(retrieval.ranked_symbols),
                             'context': retrieval.context},
              'limitation': 'Structural compatibility only. No semantic ground truth or source snippets were supplied by the endpoint.'}
    (output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'{len(checks)} structural checks and end-to-end retrieval passed')


if __name__ == '__main__':
    main()
