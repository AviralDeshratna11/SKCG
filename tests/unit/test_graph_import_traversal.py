from __future__ import annotations

import json
from dataclasses import replace

import pytest

from sckg.graph.import_graph import import_graph, audit_graph
from sckg.graph.json_store import JsonGraphStore
from sckg.ir.enums import RelationType
from sckg.retrieval.egpot import EGPOTConfig, EGPOTTraverser
from sckg.retrieval.egpot.models import StopReason
from sckg.retrieval.seeds import Seed


def fixture(tmp_path):
    data = {'nodes': [{'id': 'caller', 'name': 'caller', 'type': 'function',
                       'file': 'a.ts', 'line': 8},
                      {'id': 'contract', 'label': 'Contract', 'type': 'rpc_contract', 'line': 0},
                      {'id': 'impl', 'name': 'impl', 'type': 'function', 'file': 'b.py', 'line': 30}],
            'edges': [{'source': 'caller', 'target': 'contract', 'relation': 'CONSUMES'},
                      {'source': 'impl', 'target': 'contract', 'relation': 'IMPLEMENTS',
                       'confidence': 1.0},
                      {'source': 'impl', 'target': 'contract', 'relation': 'IMPLEMENTS',
                       'confidence': 1.0}]}
    path = tmp_path / 'export.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    document = import_graph(path)
    store = JsonGraphStore(tmp_path / 'store.json')
    store.replace_document(document)
    return path, document, store


def test_export_preserves_ids_lines_parallel_evidence_and_missing_confidence(tmp_path):
    _, doc, store = fixture(tmp_path)
    assert store.get_symbol('caller').start_line == 8
    assert store.get_symbol('contract').start_line == 1
    assert doc.relations[0].confidence == 0.6
    assert audit_graph(doc)['parallel_edges'] == 1
    assert audit_graph(doc)['missing_confidence'] == 1
    assert len(JsonGraphStore(store.path).relations) == 3


@pytest.mark.parametrize('mcts', [True, False])
def test_contract_bridge_reverse_edge_budget_and_dedup(tmp_path, mcts):
    _, _, store = fixture(tmp_path)
    cfg = EGPOTConfig(embedding_provider='hashing', mcts_enabled=mcts,
                      max_hops=2, hub_suppression_enabled=False)
    seed = Seed(store.symbols['caller'], 1, 0, 1, ())
    result = EGPOTTraverser(store, cfg).traverse('impl', [seed])
    assert result.best_trajectories[0].node_ids == ('caller', 'contract', 'impl')
    assert len(result.candidate_trajectories) == 2  # duplicate evidence is one action
    limited = EGPOTTraverser(store, replace(cfg, node_budget=2)).traverse('impl', [seed])
    assert len(limited.visited_nodes) <= 2
    assert limited.stop_reason == StopReason.NODE_BUDGET
    outgoing = EGPOTTraverser(store, replace(cfg, direction='outgoing')).traverse('impl', [seed])
    assert 'impl' not in {n.id for n in outgoing.selected_nodes}


@pytest.mark.parametrize('case', ['dangling', 'unknown', 'duplicate'])
def test_bad_export_rejected(tmp_path, case):
    path, _, _ = fixture(tmp_path)
    data = json.loads(path.read_text())
    if case == 'dangling':
        data['edges'][0]['target'] = 'missing'
    elif case == 'unknown':
        data['edges'][0]['relation'] = 'MAGIC'
    else:
        data['nodes'].append(data['nodes'][0])
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        import_graph(path)


def test_config_limits_and_empty_allowed_edges(tmp_path):
    for kwargs in [{'node_budget': 0}, {'direction': 'forward'}]:
        with pytest.raises(ValueError):
            EGPOTConfig(**kwargs)
    _, _, store = fixture(tmp_path)
    cfg = EGPOTConfig(embedding_provider='hashing', allowed_edges=())
    seed = Seed(store.symbols['caller'], 1, 0, 1, ())
    result = EGPOTTraverser(store, cfg).traverse('impl', [seed])
    assert [n.id for n in result.selected_nodes] == ['caller']


def test_graph_mutation_between_queries_rebuilds_adjacency(tmp_path):
    _, _, store = fixture(tmp_path)
    cfg = EGPOTConfig(embedding_provider='hashing')
    traverser = EGPOTTraverser(store, cfg)
    seed = Seed(store.symbols['caller'], 1, 0, 1, ())
    assert traverser.traverse('impl', [seed]).selected_edges
    store.relations.clear()
    assert not traverser.traverse('impl', [seed]).selected_edges


def test_scoring_exact_nodes_and_ordered_path_are_separate():
    pytest.importorskip('networkx')
    pytest.importorskip('numpy')
    from sckg.eval.graph_benchmark import score_result
    gold = {'target': 'impl', 'path': ['caller', 'contract', 'impl']}
    result = {'selected': ['impl_extra', 'caller', 'contract', 'impl'],
              'paths': [('caller', 'impl', 'contract')], 'latency_ms': 1, 'visited': 4}
    scores = score_result(result, gold)
    assert scores['mrr_at_5'] == 0.25
    assert scores['path_coverage'] == 1
    assert scores['ordered_path'] == 0
    result['selected'] = ['impl_extra']
    assert score_result(result, gold)['hit'] == 0


def test_all_benchmark_methods_obey_admission_budgets(tmp_path):
    pytest.importorskip('networkx')
    pytest.importorskip('numpy')
    from sckg.eval.graph_benchmark import Benchmark, METHODS
    from sckg.retrieval.semantic import HashingEmbeddingProvider
    _, _, store = fixture(tmp_path)
    benchmark = Benchmark(store, HashingEmbeddingProvider())
    for method in METHODS:
        result = benchmark.run(method, 'impl', 'caller', 2, 0)
        assert result['visited'] <= result['effective_budget']
        assert len(result['selected']) <= result['effective_budget']
        assert set(result['selected']) <= store.symbols.keys()


def test_low_similarity_contract_bridge_survives_layer_pruning(tmp_path, monkeypatch):
    from sckg.retrieval.egpot.objectives import ObjectiveEvaluator
    from sckg.ir.models import Relation
    from sckg.ir.enums import Provenance
    _, _, store = fixture(tmp_path)
    # A stronger immediate candidate in another layer must not discard the
    # contract route before its implementation can be explored.
    decoy = store.symbols['impl'].model_copy(update={'id': 'decoy', 'name': 'decoy'})
    store.symbols[decoy.id] = decoy
    edge = Relation(id='decoy-edge', repository_id='export', commit_id='snapshot',
                    source_symbol_id='caller', target_symbol_id='decoy',
                    relation_type=RelationType.CALLS, provenance=Provenance.STATIC_ANALYSIS,
                    metadata={'layer': 'Ldep'})
    store.relations[edge.id] = edge
    for key, relation in list(store.relations.items()):
        if key != edge.id:
            store.relations[key] = relation.model_copy(update={'metadata': {'layer': 'Lcontract'}})
    monkeypatch.setattr(ObjectiveEvaluator, '_semantic',
                        lambda self, q, s: {'caller': 0, 'contract': 0.1, 'decoy': 0.9, 'impl': 1}[s.id])
    config = EGPOTConfig(embedding_provider='hashing', beam_width=2, max_hops=2,
                         entropy_enabled=False, contract_enabled=False, hop_enabled=False,
                         objective_weights=(1, 0, 0, 0))
    result = EGPOTTraverser(store, config).traverse('query', [Seed(store.symbols['caller'], 0, 0, 0, ())])
    assert result.best_trajectories[0].node_ids == ('caller', 'contract', 'impl')
