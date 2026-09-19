from sckg.eval.graph_quality import precision_recall
from sckg.eval.retrieval import mean_reciprocal_rank, recall_at_k


def test_eval_metrics() -> None:
    assert precision_recall({"a", "b"}, {"b", "c"}) == {"precision": 0.5, "recall": 0.5}
    assert recall_at_k(["a", "b"], {"b"}, 2) == 1.0
    assert mean_reciprocal_rank(["a", "b"], {"b"}) == 0.5
