from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sckg.graph.json_store import JsonGraphStore
from sckg.graph.store import GraphStore
from sckg.retrieval.egpot import EGPOTConfig, EGPOTTraverser, TraversalResult
from sckg.ir.models import Symbol
from sckg.retrieval.lexical import LexicalRetriever
from sckg.retrieval.packing import ContextPacker
from sckg.retrieval.ranking import RankedSymbol, rank_symbols
from sckg.retrieval.seeds import Seed, combine_candidates
from sckg.retrieval.semantic import SemanticRetriever, make_embedding_provider
from sckg.retrieval.traversal import expand_seeds
from sckg.retrieval.egpot.hub_suppression import HubSuppressor


@dataclass(frozen=True)
class RetrievalResult:
    seeds: list[Seed]
    ranked_symbols: list[RankedSymbol]
    context: str
    egpot_result: TraversalResult | None = None


class RetrievalPipeline:
    def __init__(self, store: GraphStore, repo_path: Path, config: dict[str, Any] | None = None) -> None:
        self.store = store
        self.repo_path = repo_path
        self.config = config or {}
        self.lexical = LexicalRetriever()
        self.egpot_config = EGPOTConfig.from_dict(self.config)
        self.semantic = SemanticRetriever(make_embedding_provider(
            self.egpot_config.embedding_provider, self.egpot_config.embedding_model,
            self.egpot_config.embedding_local_files_only))

    def retrieve(
        self,
        issue: str,
        token_budget: int | None = None,
        strategy: str = "hybrid",
        max_hops: int | None = None,
        beam_width: int | None = None,
    ) -> RetrievalResult:
        if token_budget is not None and token_budget < 1:
            raise ValueError("token_budget must be positive")
        if strategy not in {"hybrid", "egpot"}:
            raise ValueError(f"Unknown retrieval strategy: {strategy}")
        hubs = HubSuppressor(self.store, self.egpot_config.hub_suppression_enabled,
                             self.egpot_config.hub_degree_threshold)
        symbols = [symbol for symbol in self._all_symbols() if not hubs.is_hub(symbol.id)]
        retrieval_config = self.config.get("retrieval", self.config)
        max_seed_symbols = int(retrieval_config.get("max_seed_symbols", 20))
        lexical_weight = float(retrieval_config.get("lexical_weight", 0.55))
        semantic_weight = float(retrieval_config.get("semantic_weight", 0.45))
        lexical = self.lexical.score(issue, symbols, max_seed_symbols)
        semantic = self.semantic.score(issue, symbols, max_seed_symbols)
        seeds = combine_candidates(lexical, semantic, lexical_weight, semantic_weight, max_seed_symbols)
        if strategy == "egpot":
            egpot_config = EGPOTConfig.from_dict(self.config)
            traverser = EGPOTTraverser(self.store, egpot_config, self.semantic.provider)
            egpot = traverser.traverse(
                issue,
                seeds,
                max_hops=max_hops,
                beam_width=beam_width,
                token_budget=token_budget,
            )
            ranked = rank_symbols(list(egpot.selected_nodes), list(egpot.selected_edges), seeds)
            budget = token_budget or egpot_config.token_budget
            context = ContextPacker(self.repo_path, budget).pack(ranked, list(egpot.selected_edges))
            return RetrievalResult(
                seeds=seeds,
                ranked_symbols=ranked,
                context=context,
                egpot_result=egpot,
            )
        traversal_cfg = retrieval_config.get("traversal", {})
        depth = int(traversal_cfg.get("max_depth", 1)) if isinstance(traversal_cfg, dict) else 1
        expanded, relations = expand_seeds(self.store, seeds, depth=depth, hubs=hubs)
        ranked = rank_symbols(expanded, relations, seeds)
        budget = token_budget or int(retrieval_config.get("token_budget", 8000))
        context = ContextPacker(self.repo_path, budget).pack(ranked, relations)
        return RetrievalResult(seeds=seeds, ranked_symbols=ranked, context=context)

    def _all_symbols(self) -> list[Symbol]:
        if isinstance(self.store, JsonGraphStore):
            return list(self.store.symbols.values())
        results: list[Symbol] = []
        for query in [""]:
            results.extend(self.store.find_symbol(query, limit=10000))
        return list({symbol.id: symbol for symbol in results}.values())
