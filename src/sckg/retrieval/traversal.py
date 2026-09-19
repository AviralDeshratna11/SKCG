from __future__ import annotations

from sckg.graph.store import GraphStore
from sckg.ir.enums import RelationType
from sckg.ir.models import Relation, Symbol
from sckg.retrieval.seeds import Seed
from sckg.retrieval.egpot.hub_suppression import HubSuppressor


DEFAULT_EXPANSION = [
    RelationType.CALLS,
    RelationType.REFERENCES,
    RelationType.IMPORTS,
    RelationType.INHERITS,
    RelationType.IMPLEMENTS,
    RelationType.OVERRIDES,
    RelationType.CONTAINS,
]


def expand_seeds(
    store: GraphStore,
    seeds: list[Seed],
    relation_types: list[RelationType] | None = None,
    depth: int = 1,
    hubs: HubSuppressor | None = None,
) -> tuple[list[Symbol], list[Relation]]:
    symbols = {seed.symbol.id: seed.symbol for seed in seeds
               if hubs is None or not hubs.is_hub(seed.symbol.id)}
    relations: dict[str, Relation] = {}
    frontier = list(symbols)
    for _ in range(depth):
        following: list[str] = []
        for symbol_id in frontier:
            nodes, edges = store.get_neighbors(symbol_id, relation_types or DEFAULT_EXPANSION, 1)
            accepted = {node.id: node for node in nodes
                        if hubs is None or not hubs.is_hub(node.id)}
            for node_id, node in accepted.items():
                if node_id not in symbols:
                    following.append(node_id)
                    symbols[node_id] = node
            for edge in edges:
                if edge.source_symbol_id in symbols and edge.target_symbol_id in symbols:
                    relations[edge.id] = edge
        frontier = following
    return list(symbols.values()), list(relations.values())
