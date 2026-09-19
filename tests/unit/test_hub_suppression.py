from dataclasses import replace

import pytest

from sckg.graph.json_store import JsonGraphStore
from sckg.ir.enums import RelationType
from sckg.retrieval.egpot.config import EGPOTConfig
from sckg.retrieval.egpot.explorer import EGPOTTraverser
from sckg.retrieval.egpot.hub_suppression import HubSuppressor
from sckg.retrieval.egpot.objectives import StructuralEntropyEstimator
from sckg.retrieval.seeds import Seed
from sckg.retrieval.traversal import expand_seeds
from test_egpot_objectives import _symbol, _relation


def hub_graph(tmp_path):
    store = JsonGraphStore(tmp_path / 'hub.json')
    nodes = {name: _symbol(name) for name in ['logger', 'useful', 'x', 'y'] + [f'caller{i}' for i in range(50)]}
    store.symbols.update(nodes)
    pairs = [(f'caller{i}', 'logger', RelationType.CALLS) for i in range(50)]
    pairs += [('caller0', 'useful', RelationType.CALLS), ('logger', 'x', RelationType.CALLS),
              ('logger', 'y', RelationType.REFERENCES)]
    for a, b, kind in pairs:
        edge = _relation(nodes[a], nodes[b], kind)
        store.relations[edge.id] = edge
    return store, Seed(nodes['caller0'], 1, 1, 1, ())


@pytest.mark.parametrize('mcts', [False, True])
def test_fifty_in_degree_logger_excluded_from_top_beam(tmp_path, mcts):
    store, seed = hub_graph(tmp_path)
    config = EGPOTConfig(embedding_provider='hashing', mcts_enabled=mcts, max_hops=1,
                         beam_width=1, semantic_enabled=False, hub_suppression_enabled=False)
    off = EGPOTTraverser(store, config).traverse('q', [seed])
    on = EGPOTTraverser(store, replace(config, hub_suppression_enabled=True)).traverse('q', [seed])
    assert off.best_trajectories[0].current_node.id == 'logger'
    assert on.best_trajectories[0].current_node.id == 'useful'
    assert 'logger' not in {n.id for n in on.visited_nodes}


def test_entropy_discount_threshold_and_hybrid_expansion(tmp_path):
    store, seed = hub_graph(tmp_path)
    hubs = HubSuppressor(store, threshold=10)
    assert hubs.in_degree('logger') == 50
    logger = store.symbols['logger']
    assert StructuralEntropyEstimator(store).entropy(logger) == 1
    assert StructuralEntropyEstimator(store, hubs).entropy(logger) == pytest.approx(0.2)
    assert not HubSuppressor(store, threshold=50).is_hub('logger')
    nodes, edges = expand_seeds(store, [seed], depth=3, hubs=hubs)
    assert {n.id for n in nodes} == {'caller0', 'useful'}
    assert all('logger' not in (e.source_symbol_id, e.target_symbol_id) for e in edges)


def test_generic_store_degree_matches_json(tmp_path):
    store, _ = hub_graph(tmp_path)
    class NeighborsOnly:
        def get_neighbors(self, *args, **kwargs):
            return store.get_neighbors(*args, **kwargs)
    assert HubSuppressor(NeighborsOnly()).in_degree('logger') == 50
