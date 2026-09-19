import math

from sckg.ir.enums import Language, Provenance, SymbolKind
from sckg.ir.models import Symbol
from sckg.retrieval.egpot.models import ObjectiveVector, Trajectory, TraversalState
from sckg.retrieval.egpot.pareto import (
    assign_crowding_distance,
    dominates,
    extract_pareto_frontier,
    non_dominated_sort,
)


def _state(name: str, vector: ObjectiveVector) -> TraversalState:
    symbol = Symbol(
        id=name,
        repository_id="repo",
        commit_id="commit",
        language=Language.PYTHON,
        kind=SymbolKind.FUNCTION,
        name=name,
        qualified_name=name,
        file_path="a.py",
        start_line=1,
        start_column=0,
        end_line=1,
        end_column=1,
        provenance=Provenance.AST,
    )
    return TraversalState(Trajectory((symbol,)), vector)


def test_pareto_dominance_equality_and_tradeoff() -> None:
    strong = ObjectiveVector(0.9, -0.1, 1.0, 1.0)
    weak = ObjectiveVector(0.8, -0.2, 0.6, 0.5)
    equal = ObjectiveVector(0.9, -0.1, 1.0, 1.0)
    tradeoff = ObjectiveVector(0.95, -0.3, 0.6, 0.4)

    assert dominates(strong, weak)
    assert not dominates(strong, equal)
    assert not dominates(strong, tradeoff)


def test_non_dominated_sort_multiple_fronts_with_negative_hop() -> None:
    best = _state("best", ObjectiveVector(0.9, -0.1, 1.0, 1.0))
    middle = _state("middle", ObjectiveVector(0.8, -0.2, 0.8, 0.8))
    worst = _state("worst", ObjectiveVector(0.7, -0.3, 0.6, 0.6))
    tradeoff = _state("tradeoff", ObjectiveVector(0.95, -0.4, 0.5, 1.2))

    fronts = non_dominated_sort([worst, middle, best, tradeoff])

    assert {item.current_node.id for item in fronts[0]} == {"best", "tradeoff"}
    assert {item.current_node.id for item in fronts[1]} == {"middle"}
    assert {item.current_node.id for item in fronts[2]} == {"worst"}


def test_extract_pareto_frontier() -> None:
    best = _state("best", ObjectiveVector(1.0, -0.1, 1.0, 1.0))
    dominated = _state("dominated", ObjectiveVector(0.5, -0.5, 0.5, 0.5))
    frontier = extract_pareto_frontier([dominated, best])
    assert [item.current_node.id for item in frontier] == ["best"]


def test_crowding_distance_edge_cases() -> None:
    one = assign_crowding_distance([_state("one", ObjectiveVector(1, 1, 1, 1))])
    assert math.isinf(one[0].crowding_distance)

    identical = assign_crowding_distance(
        [
            _state("a", ObjectiveVector(1, 1, 1, 1)),
            _state("b", ObjectiveVector(1, 1, 1, 1)),
            _state("c", ObjectiveVector(1, 1, 1, 1)),
        ]
    )
    assert math.isinf(identical[0].crowding_distance)
    assert identical[1].crowding_distance == 0.0
    assert math.isinf(identical[2].crowding_distance)


def test_mcts_expansion_prunes_dominated_states_and_bounds_beam():
    from sckg.retrieval.egpot.config import EGPOTConfig
    from sckg.retrieval.egpot.mcts import BeamMCTS

    states = [
        _state("semantic", ObjectiveVector(1, 0, 0, 0)),
        _state("contract", ObjectiveVector(0, 0, 1, 0)),
        _state("weak", ObjectiveVector(0, -1, 0, 0)),
    ]
    search = BeamMCTS(EGPOTConfig(embedding_provider="hashing"), max_hops=2, width=2)
    children = search._children(states)
    assert {c.state.current_node.id for c in children} == {"semantic", "contract"}
    assert math.isclose(sum(c.prior for c in children), 1)
    search.width = 1
    assert len(search._children(states)) == 1
