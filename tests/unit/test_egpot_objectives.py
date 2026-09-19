from pathlib import Path

from sckg.frontends.python import PythonFrontend
from sckg.graph.builder import GraphBuilder
from sckg.graph.json_store import JsonGraphStore
from sckg.ir.enums import Language, Provenance, RelationType, SymbolKind
from sckg.ir.models import Relation, Symbol
from sckg.retrieval.egpot.config import EGPOTConfig
from sckg.retrieval.egpot.models import ContractStatus, ObjectiveVector, Trajectory
from sckg.retrieval.egpot.objectives import ContractEvaluator, StructuralEntropyEstimator


def _symbol(name: str, type_: str | None = None) -> Symbol:
    return Symbol(
        id=name,
        repository_id="repo",
        commit_id="commit",
        language=Language.PYTHON,
        kind=SymbolKind.FUNCTION,
        name=name,
        qualified_name=name,
        type=type_,
        file_path=f"{name}.py",
        start_line=1,
        start_column=0,
        end_line=1,
        end_column=1,
        provenance=Provenance.AST,
    )


def _relation(source: Symbol, target: Symbol, kind: RelationType, confidence: float = 1.0) -> Relation:
    return Relation(
        id=f"{source.id}-{kind.value}-{target.id}",
        repository_id="repo",
        commit_id="commit",
        source_symbol_id=source.id,
        target_symbol_id=target.id,
        relation_type=kind,
        confidence=confidence,
        provenance=Provenance.STATIC_ANALYSIS,
    )


def test_entropy_known_values(tmp_path: Path) -> None:
    store = JsonGraphStore(tmp_path / "graph.json")
    a = _symbol("a")
    b = _symbol("b")
    c = _symbol("c")
    d = _symbol("d")
    for symbol in [a, b, c, d]:
        store.upsert_symbol(symbol)
    for relation in [
        _relation(a, b, RelationType.CALLS),
        _relation(a, c, RelationType.CALLS),
        _relation(a, d, RelationType.REFERENCES),
        _relation(b, c, RelationType.CALLS),
    ]:
        store.upsert_relation(relation)

    entropy = StructuralEntropyEstimator(store)

    assert entropy.entropy(d) == 0.0
    assert entropy.entropy(b) == 0.0
    assert round(entropy.entropy(a), 3) == 0.918


def test_contract_statuses() -> None:
    evaluator = ContractEvaluator(EGPOTConfig())
    a = _symbol("a", "Token")
    b = _symbol("b", "Token")
    c = _symbol("c")
    d = _symbol("d", "User")
    relation = _relation(a, b, RelationType.CALLS, confidence=0.8)

    assert evaluator.score(a, b, relation).status == ContractStatus.EXACT
    assert evaluator.score(a, c, relation).status == ContractStatus.UNKNOWN
    assert evaluator.score(a, d, relation).status == ContractStatus.INCONSISTENT


def test_trajectory_extension_preserves_edge_and_cycle() -> None:
    a = _symbol("a")
    b = _symbol("b")
    relation = _relation(a, b, RelationType.CALLS)
    trajectory = Trajectory((a,))

    assert not trajectory.creates_cycle(b)
    extended = trajectory.extend(
        relation,
        b,
        objectives=ObjectiveVector(1, -0.1, 1, 0),
        entropy=0,
        novelty=1,
        contract=ContractEvaluator(EGPOTConfig()).score(a, b, relation),
        reason="test",
    )

    assert extended.creates_cycle(a)
    assert extended.hops[0].relation == relation
    assert extended.hops[0].target == b


def test_egpot_retrieval_pipeline_integrates_with_existing_index(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        """
def validate(token):
    return refresh(token)

def refresh(token):
    return token.startswith("refresh")
""".strip(),
        encoding="utf-8",
    )
    store = JsonGraphStore(tmp_path / "graph.json")
    GraphBuilder(store).build(PythonFrontend().index_repository(repo, repository_identity="fixture"))

    from sckg.retrieval.pipeline import RetrievalPipeline

    result = RetrievalPipeline(store, repo, {"egpot": {"embedding_provider": "hashing"}}).retrieve(
        "why is refresh token rejected",
        300,
        strategy="egpot",
        max_hops=2,
        beam_width=2,
    )

    assert result.egpot_result is not None
    assert result.egpot_result.best_trajectories
    assert result.egpot_result.objective_scores
    assert len(result.egpot_result.selected_nodes) <= len(result.egpot_result.visited_nodes)
    assert "Relevant Symbols" in result.context
