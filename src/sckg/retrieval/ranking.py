from __future__ import annotations

from dataclasses import dataclass

from sckg.ir.enums import RelationType, SymbolKind
from sckg.ir.models import Relation, Symbol
from sckg.retrieval.seeds import Seed


@dataclass(frozen=True)
class RankedSymbol:
    symbol: Symbol
    score: float
    reasons: tuple[str, ...]


DEFAULT_RELATION_WEIGHTS = {
    RelationType.CALLS: 1.0,
    RelationType.REFERENCES: 0.8,
    RelationType.IMPORTS: 0.5,
    RelationType.INHERITS: 0.7,
    RelationType.IMPLEMENTS: 0.7,
    RelationType.OVERRIDES: 0.8,
    RelationType.CONTAINS: 0.3,
}


def rank_symbols(
    symbols: list[Symbol],
    relations: list[Relation],
    seeds: list[Seed],
    relation_weights: dict[RelationType, float] | None = None,
) -> list[RankedSymbol]:
    weights = relation_weights or DEFAULT_RELATION_WEIGHTS
    seed_scores = {seed.symbol.id: seed.score for seed in seeds}
    adjacency_bonus = {symbol.id: 0.0 for symbol in symbols}
    reasons: dict[str, list[str]] = {symbol.id: [] for symbol in symbols}
    for relation in relations:
        weight = weights.get(relation.relation_type, 0.1) * relation.confidence
        adjacency_bonus[relation.source_symbol_id] = adjacency_bonus.get(relation.source_symbol_id, 0) + weight * 0.2
        adjacency_bonus[relation.target_symbol_id] = adjacency_bonus.get(relation.target_symbol_id, 0) + weight * 0.4
        reasons.setdefault(relation.target_symbol_id, []).append(
            f"connected by {relation.relation_type.value} ({relation.provenance.value}, {relation.confidence:.2f})"
        )
    ranked = []
    for symbol in symbols:
        importance = 0.2 if symbol.kind in {SymbolKind.CLASS, SymbolKind.FUNCTION, SymbolKind.METHOD} else 0.05
        score = seed_scores.get(symbol.id, 0.0) + adjacency_bonus.get(symbol.id, 0.0) + importance
        if symbol.id in seed_scores:
            reasons.setdefault(symbol.id, []).append("direct seed match")
        ranked.append(RankedSymbol(symbol=symbol, score=score, reasons=tuple(reasons.get(symbol.id, []))))
    return sorted(ranked, key=lambda item: item.score, reverse=True)
