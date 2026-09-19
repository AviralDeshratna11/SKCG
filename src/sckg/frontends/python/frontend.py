from __future__ import annotations

from pathlib import Path

from sckg import __version__
from sckg.frontends.python.mapper import PythonSymbolCollector, module_name_for_path
from sckg.frontends.python.parser import parse_python
from sckg.frontends.python.resolver import PythonSemanticResolver
from sckg.indexing.scanner import discover_files
from sckg.ir.enums import Language, Provenance, RelationType, SymbolKind
from sckg.ir.ids import file_id, relation_id, repository_id, symbol_id
from sckg.ir.models import FileNode, LNIRDocument, Relation, RepositoryNode, SourceLocation, Symbol
from sckg.utils.git import current_commit, remote_url
from sckg.utils.hash import file_sha256


class PythonFrontend:
    language = Language.PYTHON.value
    version = __version__

    def index_repository(self, repo_path: Path, repository_identity: str | None = None) -> LNIRDocument:
        repo_path = repo_path.resolve()
        commit_id = current_commit(repo_path)
        identity = repository_identity or str(repo_path)
        repo_id = repository_id(identity)
        repository = RepositoryNode(
            id=repo_id,
            path=str(repo_path),
            git_remote=remote_url(repo_path),
            commit_id=commit_id,
        )
        files: list[FileNode] = []
        symbols: list[Symbol] = []
        relations: list[Relation] = []
        collectors: dict[str, PythonSymbolCollector] = {}
        source_by_path: dict[str, list[str]] = {}
        module_file_symbols: dict[str, Symbol] = {}
        file_symbols_by_path: dict[str, Symbol] = {}

        for path in discover_files(repo_path, [".py"]):
            normalized = path.relative_to(repo_path).as_posix()
            source_lines = path.read_text(encoding="utf-8").splitlines()
            source_by_path[normalized] = source_lines
            module_name = module_name_for_path(path, repo_path)
            tree = parse_python(path)
            collector = PythonSymbolCollector(module_name)
            collector.visit(tree)
            collectors[normalized] = collector
            file_node = FileNode(
                id=file_id(repo_id, commit_id, normalized),
                repository_id=repo_id,
                commit_id=commit_id,
                normalized_path=normalized,
                language=Language.PYTHON,
                hash=file_sha256(path),
            )
            files.append(file_node)
            file_symbol = self._make_symbol(
                repo_id,
                commit_id,
                normalized,
                Language.PYTHON,
                SymbolKind.FILE,
                name=normalized,
                qualified_name=module_name,
                start_line=1,
                start_column=0,
                end_line=max(1, len(source_lines)),
                end_column=0,
                provenance=Provenance.AST,
                source_text="\n".join(source_lines[:80]),
            )
            symbols.append(file_symbol)
            file_symbols_by_path[normalized] = file_symbol
            module_file_symbols[module_name] = file_symbol

        local_to_symbol: dict[str, Symbol] = {}
        import_maps: dict[str, dict[str, str]] = {}
        for normalized, collector in collectors.items():
            import_maps[normalized] = collector.imports
            for local in collector.symbols:
                symbol = self._make_symbol(
                    repo_id,
                    commit_id,
                    normalized,
                    Language.PYTHON,
                    local.kind,
                    local.name,
                    local.qualified_name,
                    local.line,
                    local.column,
                    local.end_line,
                    local.end_column,
                    local.signature,
                    provenance=Provenance.AST,
                    metadata=local.metadata,
                    source_text=self._source_slice(source_by_path[normalized], local.line, local.end_line),
                )
                symbols.append(symbol)
                local_to_symbol[local.qualified_name] = symbol

        all_names = set(local_to_symbol)
        for normalized, collector in collectors.items():
            file_symbol = file_symbols_by_path[normalized]
            for local in collector.symbols:
                source = local_to_symbol[local.qualified_name]
                relations.append(
                    self._relation(
                        repo_id,
                        commit_id,
                        file_symbol,
                        source,
                        RelationType.CONTAINS,
                        source.location,
                        Provenance.AST,
                        1.0,
                    )
                )
                relations.append(
                    self._relation(
                        repo_id,
                        commit_id,
                        file_symbol,
                        source,
                        RelationType.DEFINES,
                        source.location,
                        Provenance.AST,
                        1.0,
                    )
                )
                if local.parent_qualified_name and local.parent_qualified_name in local_to_symbol:
                    parent = local_to_symbol[local.parent_qualified_name]
                    relations.append(
                        self._relation(
                            repo_id,
                            commit_id,
                            parent,
                            source,
                            RelationType.CONTAINS,
                            source.location,
                            Provenance.AST,
                            1.0,
                        )
                    )
            resolver = PythonSemanticResolver(all_names, import_maps[normalized])
            for local in collector.symbols:
                source = local_to_symbol[local.qualified_name]
                if local.kind == SymbolKind.IMPORT:
                    for imported in local.imports:
                        target = self._ensure_external_symbol(
                            imported,
                            repo_id,
                            commit_id,
                            normalized,
                            local_to_symbol,
                            symbols,
                        )
                        relations.append(
                            self._relation(
                                repo_id,
                                commit_id,
                                source,
                                target,
                                RelationType.IMPORTS,
                                source.location,
                                Provenance.IMPORT_RESOLVER,
                                0.85 if target.qualified_name not in all_names else 1.0,
                            )
                        )
                for base in local.bases:
                    resolved = resolver.resolve_reference(local.qualified_name, base)
                    if resolved and resolved.qualified_name in local_to_symbol:
                        relations.append(
                            self._relation(
                                repo_id,
                                commit_id,
                                source,
                                local_to_symbol[resolved.qualified_name],
                                RelationType.INHERITS,
                                source.location,
                                Provenance.STATIC_ANALYSIS,
                                1.0,
                            )
                        )
                for call in local.calls:
                    resolved = resolver.resolve_call(local.qualified_name, call)
                    if resolved and resolved.qualified_name in local_to_symbol:
                        relations.append(
                            self._relation(
                                repo_id,
                                commit_id,
                                source,
                                local_to_symbol[resolved.qualified_name],
                                RelationType.CALLS,
                                source.location,
                                Provenance.STATIC_ANALYSIS,
                                1.0,
                            )
                        )
                for ref in local.references:
                    resolved = resolver.resolve_reference(local.qualified_name, ref)
                    if resolved and resolved.qualified_name in local_to_symbol:
                        relations.append(
                            self._relation(
                                repo_id,
                                commit_id,
                                source,
                                local_to_symbol[resolved.qualified_name],
                                RelationType.REFERENCES,
                                source.location,
                                Provenance.STATIC_ANALYSIS,
                                0.95,
                            )
                        )

        unique_relations = {relation.id: relation for relation in relations}
        document = LNIRDocument(
            repository=repository,
            files=files,
            symbols=list({symbol.id: symbol for symbol in symbols}.values()),
            relations=list(unique_relations.values()),
        )
        return document

    def _make_symbol(
        self,
        repo_id: str,
        commit_id: str,
        normalized: str,
        language: Language,
        kind: SymbolKind,
        name: str,
        qualified_name: str,
        start_line: int,
        start_column: int,
        end_line: int,
        end_column: int,
        signature: str | None = None,
        provenance: Provenance = Provenance.AST,
        metadata: dict[str, str] | None = None,
        source_text: str | None = None,
    ) -> Symbol:
        return Symbol(
            id=symbol_id(repo_id, normalized, language, qualified_name, kind, signature),
            repository_id=repo_id,
            commit_id=commit_id,
            language=language,
            kind=kind,
            name=name,
            qualified_name=qualified_name,
            signature=signature,
            file_path=normalized,
            start_line=start_line,
            start_column=start_column,
            end_line=end_line,
            end_column=end_column,
            source_text=source_text,
            provenance=provenance,
            metadata=metadata or {},
        )

    def _ensure_external_symbol(
        self,
        qualified_name: str,
        repo_id: str,
        commit_id: str,
        normalized: str,
        local_to_symbol: dict[str, Symbol],
        symbols: list[Symbol],
    ) -> Symbol:
        if qualified_name in local_to_symbol:
            return local_to_symbol[qualified_name]
        symbol = self._make_symbol(
            repo_id,
            commit_id,
            normalized,
            Language.PYTHON,
            SymbolKind.IMPORT,
            qualified_name.split(".")[-1],
            qualified_name,
            1,
            0,
            1,
            0,
            provenance=Provenance.IMPORT_RESOLVER,
            metadata={"external": "true"},
            source_text=None,
        )
        local_to_symbol[qualified_name] = symbol
        symbols.append(symbol)
        return symbol

    def _relation(
        self,
        repo_id: str,
        commit_id: str,
        source: Symbol,
        target: Symbol,
        relation_type: RelationType,
        location: SourceLocation | None,
        provenance: Provenance,
        confidence: float,
    ) -> Relation:
        return Relation(
            id=relation_id(
                repo_id,
                commit_id,
                source.id,
                target.id,
                relation_type,
                location.key if location else "",
            ),
            repository_id=repo_id,
            commit_id=commit_id,
            source_symbol_id=source.id,
            target_symbol_id=target.id,
            relation_type=relation_type,
            source_location=location,
            provenance=provenance,
            confidence=confidence,
        )

    def _source_slice(self, source_lines: list[str], start_line: int, end_line: int) -> str:
        start = max(1, start_line)
        end = min(len(source_lines), end_line)
        if start > end:
            return ""
        return "\n".join(
            f"{line_number}: {source_lines[line_number - 1]}"
            for line_number in range(start, end + 1)
        )
