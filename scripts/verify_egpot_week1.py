"""Re-run the saved example query with both providers and compare its old trace.

Run from the repository root with PYTHONPATH=src, or after installing sckg.
The original graph and baseline trace are read-only inputs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sckg.graph.json_store import JsonGraphStore
from sckg.retrieval.egpot import EGPOTConfig, EGPOTTraverser
from sckg.ir.enums import Language, Provenance, RelationType, SymbolKind
from sckg.ir.models import Symbol, Relation
from sckg.retrieval.seeds import Seed
from sckg.visualization.export import write_graph_html
from sckg.retrieval.pipeline import RetrievalPipeline
from sckg.utils.config import load_yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', type=Path, default=Path('.sckg/auth-service-graph.json'))
    parser.add_argument('--baseline', type=Path, default=Path('.sckg/egpot-trace.json'))
    parser.add_argument('--repo', type=Path, default=Path('examples/auth_service_repo'))
    parser.add_argument('--config', type=Path, default=Path('configs/egpot.yaml'))
    parser.add_argument('--output', type=Path, default=Path('.sckg/week1-validation'))
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
    if not args.store.exists():
        raise FileNotFoundError(args.store)
    store = JsonGraphStore(args.store)
    report = {'query': baseline['query'], 'baseline': str(args.baseline), 'providers': {}}
    for provider in ['hashing', 'sentence-transformers']:
        config = load_yaml(args.config)
        config['egpot']['embedding_provider'] = provider
        config['egpot']['embedding_local_files_only'] = True
        result = RetrievalPipeline(store, args.repo.resolve(), config).retrieve(
            baseline['query'], strategy='egpot').egpot_result
        assert result is not None and result.best_trajectories
        assert result.debug['simulations'] == config['egpot']['simulation_budget']
        trace = args.output / f'{provider}-trace.json'
        EGPOTTraverser(store).write_trace(result, trace)
        old = set(baseline['selected_nodes'])
        new = {node.id for node in result.selected_nodes}
        report['providers'][provider] = {
            'simulations': result.debug['simulations'],
            'selected_nodes': len(new), 'baseline_selected_nodes': len(old),
            'added': sorted(new - old), 'removed': sorted(old - new),
            'trace_changed': baseline['trace'] != result.debug['trace'],
            'trajectories': [[n.qualified_name for n in p.nodes] for p in result.best_trajectories],
            'trace': str(trace),
        }
    trained = json.loads((args.output / 'sentence-transformers-trace.json').read_text())
    hashed = json.loads((args.output / 'hashing-trace.json').read_text())
    write_graph_html(args.output / 'graph.html', list(store.symbols.values()),
                     list(store.relations.values()), 'Auth service | EG-POT Week 1', trained,
                     {'MCTS + hashing': hashed, 'Original baseline': baseline})
    report['hub_demo'] = build_hub_demo(args.output)
    output = args.output / 'comparison.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(output)


def build_hub_demo(output: Path) -> dict[str, object]:
    """Run the real traverser on a clearly labelled synthetic 50-caller fixture."""
    store = JsonGraphStore(output / 'hub-fixture.json')
    names = ['logger', 'useful', 'sink', 'config'] + [f'caller{i}' for i in range(50)]
    store.symbols = {name: Symbol(
        id=name, name=name, qualified_name=name, repository_id='hub-demo', commit_id='fixture',
        language=Language.PYTHON, kind=SymbolKind.FUNCTION, file_path=f'{name}.py',
        start_line=1, end_line=2, start_column=0, end_column=0,
        source_text=f'def {name}(): pass', provenance=Provenance.AST) for name in names}
    pairs = [(f'caller{i}', 'logger', RelationType.CALLS) for i in range(50)]
    pairs += [('caller0', 'useful', RelationType.CALLS), ('logger', 'sink', RelationType.CALLS),
              ('logger', 'config', RelationType.REFERENCES)]
    store.relations = {}
    for a, b, kind in pairs:
        edge = Relation(id=f'{a}-{b}', repository_id='hub-demo', commit_id='fixture',
                        source_symbol_id=a, target_symbol_id=b, relation_type=kind,
                        confidence=1, provenance=Provenance.STATIC_ANALYSIS)
        store.relations[edge.id] = edge
    traces = {}
    for enabled in [False, True]:
        cfg = EGPOTConfig(embedding_provider='hashing', semantic_enabled=False,
                          hub_suppression_enabled=enabled, max_hops=1, beam_width=1)
        traverser = EGPOTTraverser(store, cfg)
        result = traverser.traverse('Synthetic hub fixture: logger versus useful dependency',
                                    [Seed(store.symbols['caller0'], 1, 0, 1, ())])
        key = 'on' if enabled else 'off'
        trace_path = output / f'hub-{key}-trace.json'
        traverser.write_trace(result, trace_path)
        traces[key] = json.loads(trace_path.read_text())
    assert 'logger' in traces['off']['selected_nodes']
    assert 'logger' not in traces['on']['selected_nodes']
    assert 'useful' in traces['on']['selected_nodes']
    write_graph_html(output / 'hub-suppression.html', list(store.symbols.values()),
                     list(store.relations.values()), 'Synthetic demo | 50-caller logger',
                     traces['on'], {'Suppression OFF': traces['off']})
    return {'logger_in_degree': 50, 'logger_selected_off': True, 'logger_selected_on': False,
            'visual': str(output / 'hub-suppression.html')}


if __name__ == '__main__':
    main()
