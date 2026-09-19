from pathlib import Path

from sckg.frontends.python import PythonFrontend
from sckg.graph.builder import GraphBuilder
from sckg.graph.json_store import JsonGraphStore
from sckg.retrieval.pipeline import RetrievalPipeline


def test_retrieval_returns_context_pack(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        """
class AuthenticationMiddleware:
    def validate(self, token):
        return validate_refresh_token(token)

def validate_refresh_token(token):
    return token.startswith("refresh")
""".strip(),
        encoding="utf-8",
    )
    store = JsonGraphStore(tmp_path / "graph.json")
    GraphBuilder(store).build(PythonFrontend().index_repository(repo, repository_identity="fixture"))
    result = RetrievalPipeline(store, repo, {"egpot": {"embedding_provider": "hashing"}}).retrieve("refresh token rejected by authentication middleware", 200)
    assert "AuthenticationMiddleware" in result.context
    assert "Relevant Symbols" in result.context
