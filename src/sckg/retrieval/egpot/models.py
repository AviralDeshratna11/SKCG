from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import perf_counter

from sckg.ir.models import Relation, Symbol
from sckg.retrieval.seeds import Seed


class StopReason(StrEnum):
    MAX_HOPS = "MAX_HOPS"
    NO_CANDIDATES = "NO_CANDIDATES"
    TOKEN_BUDGET = "TOKEN_BUDGET"


class ContractStatus(StrEnum):
    EXACT = "EXACT"
    COMPATIBLE = "COMPATIBLE"
    UNKNOWN = "UNKNOWN"
    INCONSISTENT = "INCONSISTENT"


@dataclass(frozen=True)
class ContractScore:
    score: float
    status: ContractStatus
    evidence: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObjectiveVector:
    semantic_relevance: float
    hop_efficiency: float
    contract_consistency: float
    information_gain: float

    def values(self) -> tuple[float, float, float, float]:
        return (
            self.semantic_relevance,
            self.hop_efficiency,
            self.contract_consistency,
            self.information_gain,
        )


@dataclass(frozen=True)
class Hop:
    source: Symbol
    relation: Relation
    target: Symbol
    hop_number: int
    objective_vector: ObjectiveVector
    entropy: float
    novelty: float
    contract: ContractScore
    reason: str
    pareto_rank: int | None = None
    crowding_distance: float = 0.0


@dataclass(frozen=True)
class Trajectory:
    nodes: tuple[Symbol, ...]
    hops: tuple[Hop, ...] = ()

    @property
    def current_node(self) -> Symbol:
        return self.nodes[-1]

    @property
    def depth(self) -> int:
        return len(self.hops)

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.id for node in self.nodes)

    def creates_cycle(self, symbol: Symbol) -> bool:
        return symbol.id in self.node_ids

    def extend(
        self,
        relation: Relation,
        target: Symbol,
        objectives: ObjectiveVector,
        entropy: float,
        novelty: float,
        contract: ContractScore,
        reason: str,
    ) -> Trajectory:
        hop = Hop(
            source=self.current_node,
            relation=relation,
            target=target,
            hop_number=self.depth + 1,
            objective_vector=objectives,
            entropy=entropy,
            novelty=novelty,
            contract=contract,
            reason=reason,
        )
        return Trajectory(nodes=(*self.nodes, target), hops=(*self.hops, hop))


@dataclass
class TraversalState:
    trajectory: Trajectory
    objective_vector: ObjectiveVector
    estimated_tokens: int = 0
    pareto_rank: int = 0
    crowding_distance: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def current_node(self) -> Symbol:
        return self.trajectory.current_node

    @property
    def depth(self) -> int:
        return self.trajectory.depth


@dataclass(frozen=True)
class ContextSubgraph:
    nodes: tuple[Symbol, ...]
    edges: tuple[Relation, ...]


@dataclass(frozen=True)
class TraversalResult:
    query: str
    seed_nodes: tuple[Seed, ...]
    visited_nodes: tuple[Symbol, ...]
    selected_nodes: tuple[Symbol, ...]
    selected_edges: tuple[Relation, ...]
    candidate_trajectories: tuple[Trajectory, ...]
    best_trajectories: tuple[Trajectory, ...]
    pareto_front: tuple[TraversalState, ...]
    context_subgraph: ContextSubgraph
    objective_scores: dict[str, ObjectiveVector]
    entropy_values: dict[str, float]
    redundancy_statistics: dict[str, float]
    traversal_time: float
    stop_reason: StopReason
    debug: dict[str, object] = field(default_factory=dict)


class Timer:
    def __enter__(self) -> Timer:
        self.start = perf_counter()
        self.elapsed = 0.0
        return self

    def __exit__(self, *_: object) -> None:
        self.elapsed = perf_counter() - self.start
