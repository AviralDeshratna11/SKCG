from __future__ import annotations

from dataclasses import dataclass

from sckg.ir.models import Symbol
from sckg.retrieval.lexical import Candidate


@dataclass(frozen=True)
class Seed:
    symbol: Symbol
    lexical_score: float
    semantic_score: float
    score: float
    reasons: tuple[str, ...]


def combine_candidates(
    lexical: list[Candidate],
    semantic: list[Candidate],
    lexical_weight: float,
    semantic_weight: float,
    limit: int,
) -> list[Seed]:
    by_id: dict[str, dict[str, object]] = {}
    for candidate in lexical:
        by_id.setdefault(candidate.symbol.id, {"symbol": candidate.symbol, "lexical": 0.0, "semantic": 0.0, "reasons": []})
        by_id[candidate.symbol.id]["lexical"] = candidate.score
        by_id[candidate.symbol.id]["reasons"].append(candidate.reason)  # type: ignore[union-attr]
    for candidate in semantic:
        by_id.setdefault(candidate.symbol.id, {"symbol": candidate.symbol, "lexical": 0.0, "semantic": 0.0, "reasons": []})
        by_id[candidate.symbol.id]["semantic"] = candidate.score
        by_id[candidate.symbol.id]["reasons"].append(candidate.reason)  # type: ignore[union-attr]
    seeds = [
        Seed(
            symbol=item["symbol"],  # type: ignore[arg-type]
            lexical_score=float(item["lexical"]),
            semantic_score=float(item["semantic"]),
            score=lexical_weight * float(item["lexical"]) + semantic_weight * float(item["semantic"]),
            reasons=tuple(item["reasons"]),  # type: ignore[arg-type]
        )
        for item in by_id.values()
    ]
    return sorted(seeds, key=lambda seed: seed.score, reverse=True)[:limit]
