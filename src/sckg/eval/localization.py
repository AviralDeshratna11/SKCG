from __future__ import annotations

from sckg.eval.retrieval import recall_at_k


def file_level_recall(ranked_files: list[str], gold_files: set[str], k: int = 5) -> float:
    return recall_at_k(ranked_files, gold_files, k)
