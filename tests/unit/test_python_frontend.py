from pathlib import Path

from sckg.frontends.python import PythonFrontend
from sckg.ir.enums import RelationType, SymbolKind


def test_python_frontend_extracts_symbols_and_calls(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(
        """
def validate_user(user):
    return user is not None

class PaymentService:
    def charge(self, user, amount):
        validate_user(user)
        return amount
""".strip(),
        encoding="utf-8",
    )
    document = PythonFrontend().index_repository(tmp_path, repository_identity="fixture")
    names = {symbol.qualified_name: symbol for symbol in document.symbols}
    assert "service.PaymentService" in names
    assert "service.PaymentService.charge" in names
    assert names["service.PaymentService.charge"].kind == SymbolKind.METHOD
    assert "validate_user(user)" in (names["service.PaymentService.charge"].source_text or "")
    call_edges = [rel for rel in document.relations if rel.relation_type == RelationType.CALLS]
    targets = {next(symbol for symbol in document.symbols if symbol.id == rel.target_symbol_id).qualified_name for rel in call_edges}
    assert "service.validate_user" in targets


def test_python_frontend_resolves_cross_file_imported_method_call(tmp_path: Path) -> None:
    (tmp_path / "checkout.py").write_text(
        """
from payment import PaymentService

def place_order(user, amount):
    return PaymentService().charge(user, amount)
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "payment.py").write_text(
        """
class PaymentService:
    def charge(self, user, amount):
        return amount
""".strip(),
        encoding="utf-8",
    )
    document = PythonFrontend().index_repository(tmp_path, repository_identity="fixture")
    symbols = {symbol.id: symbol for symbol in document.symbols}
    call_edges = [rel for rel in document.relations if rel.relation_type == RelationType.CALLS]
    pairs = {
        (symbols[rel.source_symbol_id].qualified_name, symbols[rel.target_symbol_id].qualified_name)
        for rel in call_edges
    }
    assert ("checkout.place_order", "payment.PaymentService.charge") in pairs


def test_python_frontend_resolves_inheritance_without_guessing_dynamic_calls(tmp_path: Path) -> None:
    (tmp_path / "models.py").write_text(
        """
class Base:
    pass

class Child(Base):
    def run(self, gateway):
        return gateway.process()
""".strip(),
        encoding="utf-8",
    )
    document = PythonFrontend().index_repository(tmp_path, repository_identity="fixture")
    symbols = {symbol.id: symbol for symbol in document.symbols}
    inherits = [rel for rel in document.relations if rel.relation_type == RelationType.INHERITS]
    inherit_pairs = {
        (symbols[rel.source_symbol_id].qualified_name, symbols[rel.target_symbol_id].qualified_name)
        for rel in inherits
    }
    assert ("models.Child", "models.Base") in inherit_pairs
    call_edges = [rel for rel in document.relations if rel.relation_type == RelationType.CALLS]
    call_targets = {symbols[rel.target_symbol_id].qualified_name for rel in call_edges}
    assert "gateway.process" not in call_targets
