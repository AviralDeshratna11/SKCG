from __future__ import annotations

from pathlib import Path

from sckg.ir.models import Relation, Symbol
from sckg.retrieval.ranking import RankedSymbol


class ContextPacker:
    def __init__(self, repo_path: Path, token_budget: int = 8000) -> None:
        self.repo_path = repo_path
        self.token_budget = token_budget

    def pack(self, ranked: list[RankedSymbol], relations: list[Relation]) -> str:
        lines = ["Repository Context", "", "Relevant Symbols:"]
        used = self._tokens("\n".join(lines))
        selected: list[RankedSymbol] = []
        for item in ranked:
            snippet = self._format_symbol(item)
            cost = self._tokens(snippet)
            if used + cost > self.token_budget:
                continue
            lines.append(snippet)
            used += cost
            selected.append(item)
        selected_ids = {item.symbol.id for item in selected}
        lines.extend(["", "Relations:"])
        for relation in relations:
            if relation.source_symbol_id in selected_ids and relation.target_symbol_id in selected_ids:
                line = (
                    f"- {relation.source_symbol_id} {relation.relation_type.value} -> "
                    f"{relation.target_symbol_id} [{relation.provenance.value}, {relation.confidence:.2f}]"
                )
                if used + self._tokens(line) <= self.token_budget:
                    lines.append(line)
                    used += self._tokens(line)
        lines.extend(["", "Relevant Code:"])
        for item in selected:
            code = self._snippet(item.symbol)
            if not code:
                continue
            block = f"\n# {item.symbol.file_path}::{item.symbol.qualified_name}\n{code}"
            if used + self._tokens(block) <= self.token_budget:
                lines.append(block)
                used += self._tokens(block)
        lines.append(f"\nEstimated tokens: {used}/{self.token_budget}")
        return "\n".join(lines)

    def _format_symbol(self, item: RankedSymbol) -> str:
        reasons = "; ".join(item.reasons[:3]) or "ranked by graph relevance"
        symbol = item.symbol
        return (
            f"- {symbol.file_path}::{symbol.qualified_name} "
            f"({symbol.kind.value}, score={item.score:.3f}) - {reasons}"
        )

    def _snippet(self, symbol: Symbol) -> str:
        path = self.repo_path / symbol.file_path
        if not path.exists():
            return ""
        lines = path.read_text(encoding="utf-8").splitlines()
        start = max(1, symbol.start_line - 2)
        end = min(len(lines), symbol.end_line + 2)
        return "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1))

    def _tokens(self, text: str) -> int:
        return max(1, len(text.split()))
