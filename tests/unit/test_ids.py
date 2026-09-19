from sckg.ir.enums import Language, SymbolKind
from sckg.ir.ids import repository_id, symbol_id


def test_symbol_id_is_deterministic_without_commit() -> None:
    repo = repository_id("example")
    first = symbol_id(repo, "pkg/service.py", Language.PYTHON, "pkg.service.charge", SymbolKind.FUNCTION, "charge(x)")
    second = symbol_id(repo, "pkg/service.py", Language.PYTHON, "pkg.service.charge", SymbolKind.FUNCTION, "charge(x)")
    changed_commit_does_not_matter = symbol_id(
        repo, "pkg/service.py", Language.PYTHON, "pkg.service.charge", SymbolKind.FUNCTION, "charge(x)"
    )
    assert first == second == changed_commit_does_not_matter


def test_symbol_id_changes_for_signature() -> None:
    repo = repository_id("example")
    assert symbol_id(repo, "a.py", Language.PYTHON, "a.f", SymbolKind.FUNCTION, "f(x)") != symbol_id(
        repo, "a.py", Language.PYTHON, "a.f", SymbolKind.FUNCTION, "f(y)"
    )
