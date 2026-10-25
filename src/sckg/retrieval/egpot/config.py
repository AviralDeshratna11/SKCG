from __future__ import annotations

from dataclasses import dataclass, field
import math

from sckg.ir.enums import RelationType


@dataclass(frozen=True)
class EGPOTConfig:
    beam_width: int = 5
    max_hops: int = 5
    token_budget: int = 8192
    node_budget: int | None = None
    direction: str = "both"
    seed_max_seeds: int = 3
    semantic_enabled: bool = True
    hop_enabled: bool = True
    hop_lambda: float = 0.15
    contract_enabled: bool = True
    contract_exact_score: float = 1.0
    contract_unknown_score: float = 0.6
    entropy_enabled: bool = True
    novelty_enabled: bool = True
    pareto_enabled: bool = True
    pareto_epsilon: float = 1e-8
    crowding_enabled: bool = True
    hub_suppression_enabled: bool = True
    hub_degree_threshold: int = 10
    mcts_enabled: bool = True
    simulation_budget: int = 64
    ucb_c: float = 1.4
    objective_weights: tuple[float, ...] = (1.0, 1.0, 1.0, 1.0)
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_local_files_only: bool = False
    allowed_edges: tuple[RelationType, ...] = field(
        default_factory=lambda: (
            RelationType.CALLS,
            RelationType.CONTAINS,
            RelationType.DEFINES,
            RelationType.REFERENCES,
            RelationType.IMPORTS,
            RelationType.INHERITS,
            RelationType.IMPLEMENTS,
            RelationType.OVERRIDES,
            RelationType.EXTENDS,
            RelationType.POLYMORPHIC_CALL,
            RelationType.HTTP_CALLS,
            RelationType.CONSUMES,
            RelationType.DEFINES_RPC,
            RelationType.PASSES_ARG,
            RelationType.RETURNS,
            RelationType.FLOWS_TO,
            RelationType.MUTATES,
            RelationType.USES,
            RelationType.SEMANTIC_SIMILAR,
            RelationType.TOUCHES,
        )
    )

    def __post_init__(self) -> None:
        if self.node_budget is not None and self.node_budget < 1:
            raise ValueError("node_budget must be positive")
        if self.direction not in {"both", "outgoing", "incoming"}:
            raise ValueError("direction must be both, outgoing, or incoming")
        for name in ("beam_width", "token_budget", "seed_max_seeds", "simulation_budget",
                     "hub_degree_threshold"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if self.max_hops < 0:
            raise ValueError("max_hops must be nonnegative")
        for name in ("ucb_c", "hop_lambda", "pareto_epsilon"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if (len(self.objective_weights) != 4
                or any(not math.isfinite(w) or w < 0 for w in self.objective_weights)
                or not any(self.objective_weights)):
            raise ValueError("objective_weights requires four nonnegative finite weights, not all zero")
        if self.embedding_provider not in {"hashing", "sentence-transformers"}:
            raise ValueError("embedding_provider must be hashing or sentence-transformers")

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> EGPOTConfig:
        if not data:
            return cls()
        egpot = data.get("egpot", data)
        if not isinstance(egpot, dict):
            return cls()
        traversal = egpot.get("traversal", {})
        hop = egpot.get("hop", {})
        contract = egpot.get("contract", {})
        entropy = egpot.get("entropy", {})
        novelty = egpot.get("novelty", {})
        pareto = egpot.get("pareto", {})
        hub = egpot.get("hub_suppression", {})
        seed = egpot.get("seed", {})
        context = egpot.get("context", {})
        allowed_edges = cls().allowed_edges
        if isinstance(traversal, dict) and isinstance(traversal.get("allowed_edges"), list):
            allowed_edges = tuple(RelationType(item) for item in traversal["allowed_edges"])
        return cls(
            node_budget=int(egpot["node_budget"]) if egpot.get("node_budget") is not None else None,
            direction=str(traversal.get("direction", "both")) if isinstance(traversal, dict) else "both",
            mcts_enabled=bool(egpot.get("mcts_enabled", cls.mcts_enabled)),
            simulation_budget=int(egpot.get("simulation_budget", cls.simulation_budget)),
            ucb_c=float(egpot.get("ucb_c", cls.ucb_c)),
            objective_weights=tuple(float(w) for w in egpot.get("objective_weights", cls.objective_weights)),
            hub_degree_threshold=int(egpot.get("hub_degree_threshold",
                _nested(egpot, "hub_suppression", "degree_threshold", cls.hub_degree_threshold))),
            embedding_provider=str(egpot.get("embedding_provider", cls.embedding_provider)),
            embedding_model=str(egpot.get("embedding_model", cls.embedding_model)),
            embedding_local_files_only=bool(egpot.get("embedding_local_files_only", False)),
            beam_width=int(egpot.get("beam_width", cls.beam_width)),
            max_hops=int(egpot.get("max_hops", cls.max_hops)),
            token_budget=int(context.get("token_budget", cls.token_budget))
            if isinstance(context, dict)
            else cls.token_budget,
            seed_max_seeds=int(seed.get("max_seeds", cls.seed_max_seeds))
            if isinstance(seed, dict)
            else cls.seed_max_seeds,
            semantic_enabled=bool(_nested(egpot, "semantic", "enabled", cls.semantic_enabled)),
            hop_enabled=bool(hop.get("enabled", cls.hop_enabled))
            if isinstance(hop, dict)
            else cls.hop_enabled,
            hop_lambda=float(hop.get("lambda", cls.hop_lambda))
            if isinstance(hop, dict)
            else cls.hop_lambda,
            contract_enabled=bool(contract.get("enabled", cls.contract_enabled))
            if isinstance(contract, dict)
            else cls.contract_enabled,
            contract_exact_score=float(contract.get("exact_score", cls.contract_exact_score))
            if isinstance(contract, dict)
            else cls.contract_exact_score,
            contract_unknown_score=float(contract.get("unknown_score", cls.contract_unknown_score))
            if isinstance(contract, dict)
            else cls.contract_unknown_score,
            entropy_enabled=bool(entropy.get("enabled", cls.entropy_enabled))
            if isinstance(entropy, dict)
            else cls.entropy_enabled,
            novelty_enabled=bool(novelty.get("enabled", cls.novelty_enabled))
            if isinstance(novelty, dict)
            else cls.novelty_enabled,
            pareto_enabled=bool(pareto.get("enabled", cls.pareto_enabled))
            if isinstance(pareto, dict)
            else cls.pareto_enabled,
            pareto_epsilon=float(pareto.get("epsilon", cls.pareto_epsilon))
            if isinstance(pareto, dict)
            else cls.pareto_epsilon,
            crowding_enabled=bool(pareto.get("crowding", cls.crowding_enabled))
            if isinstance(pareto, dict)
            else cls.crowding_enabled,
            hub_suppression_enabled=bool(egpot.get("hub_suppression_enabled", hub.get("enabled", cls.hub_suppression_enabled)))
            if isinstance(hub, dict)
            else cls.hub_suppression_enabled,
            allowed_edges=allowed_edges,
        )


def _nested(data: dict[str, object], section: str, key: str, default: object) -> object:
    value = data.get(section, {})
    if isinstance(value, dict):
        return value.get(key, default)
    return default
