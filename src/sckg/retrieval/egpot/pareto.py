from __future__ import annotations

import math
from collections.abc import Sequence

from sckg.retrieval.egpot.models import ObjectiveVector, TraversalState


def dominates(left: ObjectiveVector, right: ObjectiveVector, epsilon: float = 1e-8) -> bool:
    left_values = left.values()
    right_values = right.values()
    at_least_as_good = all(a + epsilon >= b for a, b in zip(left_values, right_values, strict=True))
    strictly_better = any(a > b + epsilon for a, b in zip(left_values, right_values, strict=True))
    return at_least_as_good and strictly_better


def extract_pareto_frontier(
    candidates: Sequence[TraversalState], epsilon: float = 1e-8
) -> list[TraversalState]:
    return [
        candidate
        for candidate in candidates
        if not any(
            other is not candidate
            and dominates(other.objective_vector, candidate.objective_vector, epsilon)
            for other in candidates
        )
    ]


def non_dominated_sort(
    candidates: Sequence[TraversalState], epsilon: float = 1e-8
) -> list[list[TraversalState]]:
    remaining = list(candidates)
    fronts: list[list[TraversalState]] = []
    rank = 0
    while remaining:
        front = extract_pareto_frontier(remaining, epsilon)
        ranked = [_replace_rank(item, rank) for item in front]
        fronts.append(ranked)
        front_ids = {id(item) for item in front}
        remaining = [item for item in remaining if id(item) not in front_ids]
        rank += 1
    return fronts


def assign_crowding_distance(front: Sequence[TraversalState]) -> list[TraversalState]:
    if not front:
        return []
    if len(front) <= 2:
        return [_replace_crowding(item, math.inf) for item in front]
    distances = [0.0 for _ in front]
    dimensions = list(zip(*(item.objective_vector.values() for item in front), strict=True))
    for values in dimensions:
        order = sorted(range(len(front)), key=lambda index: values[index])
        distances[order[0]] = math.inf
        distances[order[-1]] = math.inf
        minimum = values[order[0]]
        maximum = values[order[-1]]
        if math.isclose(minimum, maximum):
            continue
        for pos in range(1, len(order) - 1):
            previous_value = values[order[pos - 1]]
            next_value = values[order[pos + 1]]
            if not math.isinf(distances[order[pos]]):
                distances[order[pos]] += (next_value - previous_value) / (maximum - minimum)
    return [_replace_crowding(item, distances[index]) for index, item in enumerate(front)]


def select_by_fronts(fronts: Sequence[Sequence[TraversalState]], width: int) -> list[TraversalState]:
    selected: list[TraversalState] = []
    for front in fronts:
        crowded = assign_crowding_distance(front)
        ordered = sorted(
            crowded,
            key=lambda item: (
                item.pareto_rank,
                -_finite_crowding(item.crowding_distance),
                -sum(item.objective_vector.values()),
                item.current_node.qualified_name,
            ),
        )
        for item in ordered:
            if len(selected) >= width:
                return selected
            selected.append(item)
    return selected


def _finite_crowding(value: float) -> float:
    return 1e12 if math.isinf(value) else value


def _replace_rank(item: TraversalState, rank: int) -> TraversalState:
    return TraversalState(
        trajectory=item.trajectory,
        objective_vector=item.objective_vector,
        estimated_tokens=item.estimated_tokens,
        pareto_rank=rank,
        crowding_distance=item.crowding_distance,
        metadata=item.metadata,
    )


def _replace_crowding(item: TraversalState, crowding: float) -> TraversalState:
    return TraversalState(
        trajectory=item.trajectory,
        objective_vector=item.objective_vector,
        estimated_tokens=item.estimated_tokens,
        pareto_rank=item.pareto_rank,
        crowding_distance=crowding,
        metadata=item.metadata,
    )
