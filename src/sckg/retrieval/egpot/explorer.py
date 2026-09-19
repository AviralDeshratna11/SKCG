from __future__ import annotations

import json
from pathlib import Path

from sckg.graph.json_store import JsonGraphStore
from sckg.graph.store import GraphStore
from sckg.ir.models import Relation, Symbol
from sckg.retrieval.egpot.config import EGPOTConfig
from sckg.retrieval.egpot.models import (
    ContextSubgraph,
    ObjectiveVector,
    StopReason,
    Timer,
    Trajectory,
    TraversalResult,
    TraversalState,
)
from sckg.retrieval.egpot.objectives import ObjectiveEvaluator
from sckg.retrieval.egpot.pareto import extract_pareto_frontier, non_dominated_sort, select_by_fronts
from sckg.retrieval.seeds import Seed
from sckg.retrieval.semantic import EmbeddingProvider
from sckg.retrieval.egpot.mcts import BeamMCTS


class EGPOTTraverser:
    def __init__(self, store: GraphStore, config: EGPOTConfig | None = None,
                 provider: EmbeddingProvider | None = None) -> None:
        self.store = store
        self.config = config or EGPOTConfig()
        self.provider = provider
        self.objectives = ObjectiveEvaluator(store, self.config, provider)

    def traverse(
        self,
        query: str,
        seed_nodes: list[Seed],
        *,
        max_hops: int | None = None,
        beam_width: int | None = None,
        token_budget: int | None = None,
    ) -> TraversalResult:
        max_depth = max_hops if max_hops is not None else self.config.max_hops
        width = beam_width if beam_width is not None else self.config.beam_width
        budget = token_budget if token_budget is not None else self.config.token_budget
        if max_depth < 0 or width < 1 or budget < 1:
            raise ValueError("max_hops must be nonnegative; beam_width and token_budget positive")
        self.objectives = ObjectiveEvaluator(self.store, self.config, self.provider)
        seeds = [seed for seed in seed_nodes
                 if not self.objectives.hubs.is_hub(seed.symbol.id)
                 and self._estimate_tokens(Trajectory((seed.symbol,))) <= budget][
                     : self.config.seed_max_seeds]
        beam = [
            TraversalState(Trajectory((seed.symbol,)), ObjectiveVector(seed.semantic_score, 0.0, 1.0, 0.0))
            for seed in seeds
        ]
        visited_nodes: dict[str, Symbol] = {seed.symbol.id: seed.symbol for seed in seeds}
        visited_edges: dict[str, Relation] = {}
        objective_scores: dict[str, ObjectiveVector] = {
            state.current_node.id: state.objective_vector for state in beam
        }
        entropy_values: dict[str, float] = {}
        all_candidates: list[TraversalState] = []
        trace: list[dict[str, object]] = []
        stop_reason = StopReason.MAX_HOPS
        if not beam:
            stop_reason = (StopReason.TOKEN_BUDGET if any(
                not self.objectives.hubs.is_hub(seed.symbol.id)
                and self._estimate_tokens(Trajectory((seed.symbol,))) > budget
                for seed in seed_nodes) else StopReason.NO_CANDIDATES)
        def expand(state: TraversalState) -> list[TraversalState]:
            nonlocal stop_reason
            candidates: list[TraversalState] = []
            for relation, candidate in self._expand(state.current_node):
                if state.trajectory.creates_cycle(candidate):
                    continue
                vector, entropy, novelty, contract = self.objectives.evaluate(
                    query, state.trajectory, relation, candidate)
                extended = state.trajectory.extend(
                    relation, candidate, vector, entropy, novelty, contract,
                    self._reason(vector, entropy, novelty, relation))
                candidate_state = TraversalState(
                    extended, vector, estimated_tokens=self._estimate_tokens(extended),
                    metadata={"entropy": entropy, "novelty": novelty})
                if candidate_state.estimated_tokens > budget:
                    stop_reason = StopReason.TOKEN_BUDGET
                    continue
                candidates.append(candidate_state)
                all_candidates.append(candidate_state)
                visited_nodes[candidate.id] = candidate
                visited_edges[relation.id] = relation
                objective_scores[candidate.id] = vector
                entropy_values[candidate.id] = entropy
            return candidates

        mcts: BeamMCTS | None = None
        with Timer() as timer:
            if self.config.mcts_enabled and beam and max_depth:
                mcts = BeamMCTS(self.config, max_depth, width)
                beam = mcts.search(beam, expand)
                trace = mcts.trace
                if stop_reason != StopReason.TOKEN_BUDGET:
                    stop_reason = (StopReason.MAX_HOPS if any(s.depth == max_depth for s in beam)
                                   else StopReason.NO_CANDIDATES)
            else:
                for depth in range(max_depth):
                    candidates = [candidate for state in beam for candidate in expand(state)]
                    if not candidates:
                        if stop_reason != StopReason.TOKEN_BUDGET:
                            stop_reason = StopReason.NO_CANDIDATES
                        break
                    fronts = (non_dominated_sort(candidates, self.config.pareto_epsilon)
                              if self.config.pareto_enabled else [candidates])
                    beam = (select_by_fronts(fronts, width) if self.config.crowding_enabled
                            else list(fronts[0])[:width])
                    trace.append({"hop": depth + 1, "candidate_count": len(candidates),
                                  "front_sizes": [len(front) for front in fronts],
                                  "selected": [state.current_node.id for state in beam]})
            # The token budget also bounds the union of selected trajectories.
            packed: list[TraversalState] = []
            for state in beam:
                union = self._selected_subgraph([*packed, state])
                if self._estimate_tokens(Trajectory(union.nodes)) <= budget:
                    packed.append(state)
                else:
                    stop_reason = StopReason.TOKEN_BUDGET
            beam = packed
            selected = self._selected_subgraph(beam)
            pareto_front = tuple(extract_pareto_frontier(all_candidates, self.config.pareto_epsilon))
        selected_ids = {node.id for node in selected.nodes}
        redundancy = {
            "visited_nodes": float(len(visited_nodes)),
            "selected_nodes": float(len(selected.nodes)),
            "pruned_nodes": float(max(0, len(visited_nodes) - len(selected_ids))),
        }
        return TraversalResult(
            query=query,
            seed_nodes=tuple(seeds),
            visited_nodes=tuple(visited_nodes.values()),
            selected_nodes=selected.nodes,
            selected_edges=selected.edges,
            candidate_trajectories=tuple(state.trajectory for state in all_candidates),
            best_trajectories=tuple(state.trajectory for state in beam),
            pareto_front=pareto_front,
            context_subgraph=selected,
            objective_scores=objective_scores,
            entropy_values=entropy_values,
            redundancy_statistics=redundancy,
            traversal_time=timer.elapsed,
            stop_reason=stop_reason,
            debug={"trace": trace, "mcts_enabled": self.config.mcts_enabled,
                   "simulations": mcts.simulations if mcts else 0,
                   "tree": mcts.statistics() if mcts else [],
                   "embedding_provider": self.config.embedding_provider,
                   "hub_suppression_enabled": self.config.hub_suppression_enabled,
                   "hub_degree_threshold": self.config.hub_degree_threshold,
                   "suppressed_hubs": sorted(self.objectives.hubs.suppressed)},
        )

    def write_trace(self, result: TraversalResult, output: Path) -> Path:
        payload = {
            "query": result.query,
            "seeds": [seed.symbol.id for seed in result.seed_nodes],
            "stop_reason": result.stop_reason.value,
            "selected_nodes": [node.id for node in result.selected_nodes],
            "selected_edges": [edge.id for edge in result.selected_edges],
            "objective_scores": {
                node_id: vector.values() for node_id, vector in result.objective_scores.items()
            },
            "trace": result.debug.get("trace", []),
            "search": result.debug,
            "trajectories": [{
                "nodes": list(path.node_ids),
                "edges": [hop.relation.id for hop in path.hops],
                "objectives": [list(hop.objective_vector.values()) for hop in path.hops],
            } for path in result.best_trajectories],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output

    def _expand(self, symbol: Symbol) -> list[tuple[Relation, Symbol]]:
        _, relations = self.store.get_neighbors(symbol.id, list(self.config.allowed_edges), depth=1)
        expanded: list[tuple[Relation, Symbol]] = []
        for relation in sorted(relations, key=lambda item: (item.relation_type.value, item.id)):
            target_id = (
                relation.target_symbol_id
                if relation.source_symbol_id == symbol.id
                else relation.source_symbol_id
            )
            target = self._get_symbol_by_id(target_id)
            if target is not None and not self.objectives.hubs.is_hub(target.id):
                expanded.append((relation, target))
        return expanded

    def _get_symbol_by_id(self, symbol_id: str) -> Symbol | None:
        if isinstance(self.store, JsonGraphStore):
            return self.store.symbols.get(symbol_id)
        return self.store.get_symbol(symbol_id)

    def _selected_subgraph(self, states: list[TraversalState]) -> ContextSubgraph:
        nodes: dict[str, Symbol] = {}
        edges: dict[str, Relation] = {}
        for state in states:
            nodes.update({node.id: node for node in state.trajectory.nodes})
            edges.update({hop.relation.id: hop.relation for hop in state.trajectory.hops})
        return ContextSubgraph(tuple(nodes.values()), tuple(edges.values()))

    def _estimate_tokens(self, trajectory: Trajectory) -> int:
        text = " ".join(
            " ".join(filter(None, [node.qualified_name, node.signature or "", node.source_text or ""]))
            for node in trajectory.nodes
        )
        return max(1, len(text.split()))

    def _reason(
        self, vector: ObjectiveVector, entropy: float, novelty: float, relation: Relation
    ) -> str:
        return (
            f"{relation.relation_type.value}: semantic={vector.semantic_relevance:.3f}, "
            f"hop={vector.hop_efficiency:.3f}, contract={vector.contract_consistency:.3f}, "
            f"entropy={entropy:.3f}, novelty={novelty:.3f}, info={vector.information_gain:.3f}"
        )
