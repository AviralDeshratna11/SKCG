from dataclasses import replace

import pytest

from sckg.graph.json_store import JsonGraphStore
from sckg.ir.enums import RelationType
from sckg.retrieval.egpot.config import EGPOTConfig
from sckg.retrieval.egpot.explorer import EGPOTTraverser
from sckg.retrieval.egpot.objectives import ObjectiveEvaluator
from sckg.retrieval.seeds import Seed
from test_egpot_objectives import _symbol, _relation


def fixture_graph(tmp_path):
    store = JsonGraphStore(tmp_path / 'graph.json')
    nodes = {name: _symbol(name) for name in ['seed', 'decoy', 'bridge', 'target']}
    store.symbols.update(nodes)
    for source, target, confidence in [('seed', 'decoy', 0.8), ('seed', 'bridge', 1.0),
                                        ('bridge', 'target', 1.0), ('target', 'seed', 0.1)]:
        # The last edge tests cycle rejection without offering a direct target shortcut.
        kind = RelationType.IMPORTS if source == 'target' else RelationType.CALLS
        edge = _relation(nodes[source], nodes[target], kind, confidence)
        store.relations[edge.id] = edge
    seed = Seed(nodes['seed'], 1, 0, 1, ())
    return store, seed


def test_mcts_discovers_known_best_path_and_backpropagates(tmp_path, monkeypatch):
    store, seed = fixture_graph(tmp_path)
    scores = {'seed': 0, 'decoy': 0.8, 'bridge': 0.2, 'target': 1.0}
    monkeypatch.setattr(ObjectiveEvaluator, '_semantic', lambda self, q, s: scores[s.id])
    config = EGPOTConfig(embedding_provider='hashing', beam_width=2, max_hops=2,
                         simulation_budget=16, entropy_enabled=False,
                         objective_weights=(1, 0, 0, 0), allowed_edges=(RelationType.CALLS,))
    result = EGPOTTraverser(store, config).traverse('query', [seed])
    assert result.best_trajectories[0].node_ids == ('seed', 'bridge', 'target')
    assert result.debug['simulations'] == 16
    tree = {tuple(row['path']): row for row in result.debug['tree']}
    assert tree[('seed',)]['visits'] == 16
    assert tree[('seed', 'bridge')]['visits'] > 0
    assert tree[('seed', 'bridge')]['mean_value'] == 1.0
    repeated = EGPOTTraverser(store, config).traverse('query', [seed])
    assert result.debug == repeated.debug
    assert result.best_trajectories == repeated.best_trajectories


@pytest.mark.parametrize('enabled', [False, True])
def test_hops_cycles_empty_seeds_and_budget(tmp_path, enabled):
    store, seed = fixture_graph(tmp_path)
    config = EGPOTConfig(embedding_provider='hashing', mcts_enabled=enabled, max_hops=8)
    traverser = EGPOTTraverser(store, config)
    result = traverser.traverse('target', [seed])
    assert all(len(p.node_ids) == len(set(p.node_ids)) for p in result.candidate_trajectories)
    assert not traverser.traverse('q', []).selected_nodes
    assert traverser.traverse('q', [seed], max_hops=0).best_trajectories[0].depth == 0
    assert all(p.depth <= 1 for p in traverser.traverse('q', [seed], max_hops=1).best_trajectories)
    assert len(traverser.traverse('q', [seed], token_budget=1).selected_nodes) == 1
    for kwargs in [{'max_hops': -1}, {'beam_width': 0}, {'token_budget': 0}]:
        with pytest.raises(ValueError):
            traverser.traverse('q', [seed], **kwargs)


def test_scalarization_weights_change_choice(tmp_path, monkeypatch):
    store, seed = fixture_graph(tmp_path)
    monkeypatch.setattr(ObjectiveEvaluator, '_semantic', lambda self, q, s: 0.9 if s.id == 'decoy' else 0.1)
    config = EGPOTConfig(embedding_provider='hashing', max_hops=1, beam_width=2,
                         entropy_enabled=False, objective_weights=(1, 0, 0, 0),
                         allowed_edges=(RelationType.CALLS,))
    semantic = EGPOTTraverser(store, config).traverse('q', [seed])
    contract = EGPOTTraverser(store, replace(config, objective_weights=(0, 0, 1, 0))).traverse('q', [seed])
    assert semantic.best_trajectories[0].current_node.id == 'decoy'
    assert contract.best_trajectories[0].current_node.id == 'bridge'
