from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sckg.ir.models import Symbol

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class Candidate:
    symbol: Symbol
    score: float
    reason: str


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


class LexicalRetriever:
    def score(self, query: str, symbols: list[Symbol], limit: int = 20) -> list[Candidate]:
        query_terms = tokenize(query)
        if not query_terms:
            return []
        docs = [
            tokenize(
                " ".join(
                    filter(
                        None,
                        [symbol.name, symbol.qualified_name, symbol.file_path, symbol.signature or ""],
                    )
                )
            )
            for symbol in symbols
        ]
        document_count = len(docs)
        scored: list[Candidate] = []
        for symbol, terms in zip(symbols, docs, strict=True):
            if not terms:
                continue
            term_counts = {term: terms.count(term) for term in set(terms)}
            score = 0.0
            for query_term in query_terms:
                containing = sum(1 for doc in docs if query_term in doc)
                if containing == 0:
                    continue
                tf = term_counts.get(query_term, 0) / len(terms)
                idf = math.log((document_count + 1) / (containing + 0.5))
                score += tf * idf
            if score > 0:
                scored.append(Candidate(symbol, score, "lexical token match"))
        return sorted(scored, key=lambda candidate: candidate.score, reverse=True)[:limit]
