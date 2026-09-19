from __future__ import annotations

import ast
from pathlib import Path

from sckg.frontends.python.symbols import LocalSymbol
from sckg.ir.enums import SymbolKind


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = [arg.arg for arg in node.args.posonlyargs + node.args.args]
    if node.args.vararg:
        args.append(f"*{node.args.vararg.arg}")
    args.extend(arg.arg for arg in node.args.kwonlyargs)
    if node.args.kwarg:
        args.append(f"**{node.args.kwarg.arg}")
    return f"{node.name}({', '.join(args)})"


def _name_from_expr(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name_from_expr(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _name_from_expr(node.func)
    return None


class PythonSymbolCollector(ast.NodeVisitor):
    def __init__(self, module_name: str) -> None:
        self.module_name = module_name
        self.scope: list[str] = [module_name]
        self.symbols: list[LocalSymbol] = []
        self.imports: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        imports: list[str] = []
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self.imports[local] = alias.name
            imports.append(alias.name)
        self._add_symbol(node, imports[0], imports[0], SymbolKind.IMPORT, imports=tuple(imports))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        prefix = "." * node.level + (node.module or "")
        imports: list[str] = []
        for alias in node.names:
            target = f"{prefix}.{alias.name}" if prefix else alias.name
            target = target.strip(".")
            local = alias.asname or alias.name
            self.imports[local] = target
            imports.append(target)
        name = prefix or "."
        self._add_symbol(node, name, name, SymbolKind.IMPORT, imports=tuple(imports))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = ".".join([*self.scope, node.name])
        bases = tuple(filter(None, (_name_from_expr(base) for base in node.bases)))
        self.symbols.append(
            LocalSymbol(
                name=node.name,
                qualified_name=qualified,
                kind=SymbolKind.CLASS,
                line=node.lineno,
                column=node.col_offset,
                end_line=getattr(node, "end_lineno", node.lineno),
                end_column=getattr(node, "end_col_offset", node.col_offset),
                parent_qualified_name=".".join(self.scope),
                bases=bases,
            )
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified = ".".join([*self.scope, node.name])
        kind = SymbolKind.METHOD if len(self.scope) > 1 and self.scope[-1] != self.module_name else SymbolKind.FUNCTION
        calls: list[str] = []
        references: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call = _name_from_expr(child.func)
                if call:
                    calls.append(call)
            elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                references.append(child.id)
        self.symbols.append(
            LocalSymbol(
                name=node.name,
                qualified_name=qualified,
                kind=kind,
                line=node.lineno,
                column=node.col_offset,
                end_line=getattr(node, "end_lineno", node.lineno),
                end_column=getattr(node, "end_col_offset", node.col_offset),
                signature=_signature(node),
                parent_qualified_name=".".join(self.scope),
                calls=tuple(dict.fromkeys(calls)),
                references=tuple(dict.fromkeys(references)),
            )
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _add_symbol(
        self,
        node: ast.AST,
        name: str,
        qualified_name: str,
        kind: SymbolKind,
        imports: tuple[str, ...] = (),
    ) -> None:
        self.symbols.append(
            LocalSymbol(
                name=name,
                qualified_name=f"{self.module_name}.{qualified_name}",
                kind=kind,
                line=getattr(node, "lineno", 1),
                column=getattr(node, "col_offset", 0),
                end_line=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                end_column=getattr(node, "end_col_offset", getattr(node, "col_offset", 0)),
                parent_qualified_name=self.module_name,
                imports=imports,
            )
        )


def module_name_for_path(path: Path, repo_path: Path) -> str:
    relative = path.relative_to(repo_path).with_suffix("")
    parts = [part for part in relative.parts if part != "__init__"]
    return ".".join(parts) or path.parent.name
