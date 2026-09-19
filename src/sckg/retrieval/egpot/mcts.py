"""Deterministic Beam-MCTS with Pareto pruning and terminal-value rollouts."""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from sckg.retrieval.egpot.config import EGPOTConfig
from sckg.retrieval.egpot.models import TraversalState
from sckg.retrieval.egpot.pareto import non_dominated_sort, select_by_fronts


@dataclass
class SearchNode:
    state: TraversalState
    prior: float = 1.0
    visits: int = 0
    value_sum: float = 0.0
    children: list[SearchNode] = field(default_factory=list)
    expanded: bool = False

    @property
    def mean_value(self) -> float:
        return self.value_sum / self.visits if self.visits else 0.0


class BeamMCTS:
    """Budget is simulations per query, each bounded by max_hops.

    Each expansion keeps only the first non-dominated front, crowding-pruned to
    beam_width. PUCT selects visited-tree branches; an unvisited branch rolls out
    greedily by scalarized terminal value. The same tree stores rollout nodes, so
    later simulations can explore alternatives. Terminal reward is backpropagated
    to every ancestor. Output is the best sampled terminal paths, not a global
    optimality guarantee: Pareto/beam pruning and finite budgets can miss paths.
    """

    def __init__(self, config: EGPOTConfig, max_hops: int, width: int) -> None:
        self.config = config
        self.max_hops = max_hops
        self.width = width
        self.roots: list[SearchNode] = []
        self.trace: list[dict[str, object]] = []
        self.simulations = 0

    def value(self, state: TraversalState) -> float:
        return sum(w * v for w, v in zip(
            self.config.objective_weights, state.objective_vector.values(), strict=True))

    def _children(self, states: list[TraversalState]) -> list[SearchNode]:
        if not states:
            return []
        fronts = (non_dominated_sort(states, self.config.pareto_epsilon)
                  if self.config.pareto_enabled else [states])
        survivors = (select_by_fronts(fronts[:1], self.width) if self.config.crowding_enabled
                     else sorted(fronts[0], key=lambda s: (-self.value(s), s.trajectory.node_ids))[:self.width])
        peak = max(self.value(s) for s in survivors)
        priors = [math.exp(self.value(s) - peak) for s in survivors]
        total = sum(priors)
        return [SearchNode(s, p / total) for s, p in zip(survivors, priors, strict=True)]

    def _select(self, children: list[SearchNode], visits: int) -> SearchNode:
        # Visit each retained branch once before applying PUCT.
        unseen = [child for child in children if not child.visits]
        if unseen:
            return max(unseen, key=lambda child: child.prior)
        return max(children, key=lambda child: (
            child.mean_value + self.config.ucb_c * child.prior
            * math.sqrt(max(1, visits)) / (1 + child.visits)))

    def search(self, seeds: list[TraversalState],
               expand: Callable[[TraversalState], list[TraversalState]]) -> list[TraversalState]:
        self.roots = [SearchNode(s, 1 / len(seeds)) for s in seeds]
        self.trace = []
        self.simulations = 0
        terminals: dict[tuple[str, ...], TraversalState] = {}
        if not seeds:
            return []
        for simulation in range(self.config.simulation_budget):
            node = self._select(self.roots, simulation)
            path = [node]
            rollout = node.visits == 0
            while node.state.depth < self.max_hops:
                if not node.expanded:
                    candidates = expand(node.state)
                    node.children = self._children(candidates)
                    node.expanded = True
                    self.trace.append({
                        "hop": node.state.depth + 1,
                        "path": list(node.state.trajectory.node_ids),
                        "candidate_count": len(candidates),
                        "selected": [c.state.current_node.id for c in node.children],
                    })
                if not node.children:
                    break
                node = (max(node.children, key=lambda c: self.value(c.state)) if rollout
                        else self._select(node.children, node.visits))
                rollout = rollout or node.visits == 0
                path.append(node)
            reward = self.value(node.state)
            for ancestor in path:
                ancestor.visits += 1
                ancestor.value_sum += reward
            terminals[node.state.trajectory.node_ids] = node.state
            self.simulations += 1
        return sorted(terminals.values(), key=lambda s: (
            -self.value(s), s.trajectory.node_ids))[:self.width]

    def statistics(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        pending = list(self.roots)
        while pending:
            node = pending.pop(0)
            result.append({"path": list(node.state.trajectory.node_ids), "visits": node.visits,
                           "mean_value": node.mean_value, "prior": node.prior})
            pending.extend(node.children)
        return result
