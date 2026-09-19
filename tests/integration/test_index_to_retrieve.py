from pathlib import Path

from sckg.graph.json_store import JsonGraphStore
from sckg.indexing.pipeline import IndexingPipeline
from sckg.retrieval.pipeline import RetrievalPipeline


def test_repository_to_graph_to_context(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "checkout.py").write_text(
        """
from payment import PaymentService

def place_order(user, amount):
    return PaymentService().charge(user, amount)
""".strip(),
        encoding="utf-8",
    )
    (repo / "payment.py").write_text(
        """
class PaymentService:
    def charge(self, user, amount):
        return amount
""".strip(),
        encoding="utf-8",
    )
    store = JsonGraphStore(tmp_path / "graph.json")
    report = IndexingPipeline(store).index(repo)
    assert report.build.files == 2
    context = RetrievalPipeline(store, repo, {"egpot": {"embedding_provider": "hashing"}}).retrieve("payment charge order amount", 300).context
    assert "PaymentService" in context
