from __future__ import annotations

import math
from collections import Counter

from sckg.graph.store import GraphStore
from sckg.ir.models import Relation, Symbol
from sckg.ir.enums import Provenance, RelationType
from sckg.retrieval.egpot.config import EGPOTConfig
from sckg.retrieval.egpot.models import ContractScore, ContractStatus, ObjectiveVector, Trajectory
from sckg.retrieval.semantic import EmbeddingProvider, make_embedding_provider, cosine
from sckg.retrieval.egpot.hub_suppression import HubSuppressor
from sckg.retrieval.egpot.adjacency import Adjacency


class StructuralEntropyEstimator:
    def __init__(self, store: GraphStore, hubs: HubSuppressor | None = None) -> None:
        self.store = store
        self.hubs = hubs
        self._cache: dict[str, float] = {}
        self.adjacency = Adjacency(store)

    def entropy(self, symbol: Symbol) -> float:
        if symbol.id in self._cache:
            return self._cache[symbol.id]
        relations = list({(r.target_symbol_id, r.relation_type): r
                          for r in self._outgoing_relations(symbol)}.values())
        total = len(relations)
        if total == 0:
            self._cache[symbol.id] = 0.0
            return 0.0
        counts = Counter(relation.relation_type for relation in relations)
        value = -sum((count / total) * math.log2(count / total) for count in counts.values())
        if math.isclose(value, 0.0, abs_tol=1e-12):
            value = 0.0
        if self.hubs is not None:
            value *= self.hubs.discount(symbol.id)
        self._cache[symbol.id] = value
        return value

    def _outgoing_relations(self, symbol: Symbol) -> list[Relation]:
        return [r for r in self.adjacency.edges(symbol.id)
                if r.source_symbol_id == symbol.id and r.target_symbol_id != symbol.id]


class NoveltyEstimator:
    def novelty(self, symbol: Symbol, relation: Relation, trajectory: Trajectory) -> float:
        if trajectory.creates_cycle(symbol):
            return 0.0
        score = 1.0
        if any(node.file_path == symbol.file_path for node in trajectory.nodes):
            score *= 0.75
        if any(node.source_text and node.source_text == symbol.source_text for node in trajectory.nodes):
            score *= 0.25
        if any(hop.relation.relation_type == relation.relation_type for hop in trajectory.hops):
            score *= 0.85
        return max(0.0, min(1.0, score))


class ContractEvaluator:
    def __init__(self, config: EGPOTConfig) -> None:
        self.config = config

    def score(self, previous: Symbol, candidate: Symbol, relation: Relation) -> ContractScore:
        if previous.type and candidate.type and previous.type == candidate.type:
            return ContractScore(
                self.config.contract_exact_score,
                ContractStatus.EXACT,
                ("matching symbol types",),
                (relation.provenance.value,),
            )
        if relation.confidence >= 0.95 and relation.provenance != Provenance.HEURISTIC:
            return ContractScore(
                self.config.contract_exact_score,
                ContractStatus.COMPATIBLE,
                ("high-confidence static relation",),
                (relation.provenance.value,),
            )
        if previous.type is None or candidate.type is None:
            return ContractScore(
                self.config.contract_unknown_score,
                ContractStatus.UNKNOWN,
                ("type metadata unavailable",),
                (relation.provenance.value,),
            )
        return ContractScore(
            self.config.contract_unknown_score,
            ContractStatus.INCONSISTENT,
            ("available type metadata differs",),
            (relation.provenance.value,),
        )


class ObjectiveEvaluator:
    def __init__(self, store: GraphStore, config: EGPOTConfig,
                 provider: EmbeddingProvider | None = None) -> None:
        self.config = config
        self.embeddings = provider or make_embedding_provider(
            config.embedding_provider, config.embedding_model, config.embedding_local_files_only)
        self.hubs = HubSuppressor(store, config.hub_suppression_enabled, config.hub_degree_threshold)
        self.entropy = StructuralEntropyEstimator(store, self.hubs)
        self.novelty = NoveltyEstimator()
        self.contracts = ContractEvaluator(config)
        self._query_cache: dict[str, list[float]] = {}
        self._symbol_cache: dict[str, list[float]] = {}

    def evaluate(
        self, query: str, trajectory: Trajectory, relation: Relation, candidate: Symbol
    ) -> tuple[ObjectiveVector, float, float, ContractScore]:
        semantic = self._semantic(query, candidate) if self.config.semantic_enabled else 0.0
        hop = -self.config.hop_lambda * (trajectory.depth + 1) if self.config.hop_enabled else 0.0
        contract = (
            self.contracts.score(trajectory.current_node, candidate, relation)
            if self.config.contract_enabled
            else ContractScore(0.0, ContractStatus.UNKNOWN)
        )
        entropy = self.entropy.entropy(candidate) if self.config.entropy_enabled else 0.0
        novelty = self.novelty.novelty(candidate, relation, trajectory) if self.config.novelty_enabled else 1.0
        # Keep information gain on the same [0, 1] scale as semantic/contract
        # objectives; report the original entropy separately for diagnostics.
        information_gain = entropy / math.log2(len(RelationType)) * novelty
        return (
            ObjectiveVector(semantic, hop, contract.score, information_gain),
            entropy,
            novelty,
            contract,
        )

    def _semantic(self, query: str, symbol: Symbol) -> float:
        if query not in self._query_cache:
            self._query_cache[query] = self.embeddings.embed(query)
        if symbol.id not in self._symbol_cache:
            text = " ".join(
                filter(
                    None,
                    [
                        symbol.name,
                        symbol.qualified_name,
                        symbol.signature or "",
                        symbol.type or "",
                        symbol.file_path,
                        symbol.source_text or "",
                    ],
                )
            )
            self._symbol_cache[symbol.id] = self.embeddings.embed(text)
        return cosine(self._query_cache[query], self._symbol_cache[symbol.id])
