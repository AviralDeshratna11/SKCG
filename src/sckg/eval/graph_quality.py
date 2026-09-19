from __future__ import annotations


def precision_recall(predicted: set[str], gold: set[str]) -> dict[str, float]:
    true_positive = len(predicted & gold)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    return {"precision": precision, "recall": recall}
