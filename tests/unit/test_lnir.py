import pytest

from sckg.ir.enums import Language, Provenance, RelationType, SymbolKind
from sckg.ir.ids import file_id, relation_id, repository_id, symbol_id
from sckg.ir.models import FileNode, LNIRDocument, Relation, RepositoryNode, SourceLocation, Symbol


def test_lnir_validates_relation_targets() -> None:
    repo_id = repository_id("repo")
    repo = RepositoryNode(id=repo_id, path="repo", commit_id="HEAD")
    file = FileNode(
        id=file_id(repo_id, "HEAD", "a.py"),
        repository_id=repo_id,
        commit_id="HEAD",
        normalized_path="a.py",
        language=Language.PYTHON,
        hash="abc",
    )
    symbol = Symbol(
        id=symbol_id(repo_id, "a.py", Language.PYTHON, "a.f", SymbolKind.FUNCTION),
        repository_id=repo_id,
        commit_id="HEAD",
        language=Language.PYTHON,
        kind=SymbolKind.FUNCTION,
        name="f",
        qualified_name="a.f",
        file_path="a.py",
        start_line=1,
        start_column=0,
        end_line=1,
        end_column=3,
        provenance=Provenance.AST,
    )
    relation = Relation(
        id=relation_id(repo_id, "HEAD", symbol.id, "missing", RelationType.CALLS),
        repository_id=repo_id,
        commit_id="HEAD",
        source_symbol_id=symbol.id,
        target_symbol_id="missing",
        relation_type=RelationType.CALLS,
        source_location=SourceLocation(file_path="a.py", start_line=1, start_column=0, end_line=1, end_column=3),
        provenance=Provenance.STATIC_ANALYSIS,
    )
    with pytest.raises(ValueError):
        LNIRDocument(repository=repo, files=[file], symbols=[symbol], relations=[relation])
