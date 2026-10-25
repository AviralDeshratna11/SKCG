"""Translate GRAFT's layered graph into the stable SCKG intermediate representation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sckg.ir.enums import Language, Provenance, RelationType, SymbolKind
from sckg.ir.ids import file_id, relation_id, repository_id, stable_hash
from sckg.ir.models import FileNode, LNIRDocument, Relation, RepositoryNode, Symbol
from sckg.utils.git import current_commit, remote_url
from sckg.utils.hash import file_sha256


_EXTENSIONS = {
    ".py": Language.PYTHON, ".js": Language.JAVASCRIPT, ".jsx": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT, ".tsx": Language.TYPESCRIPT, ".go": Language.GO,
    ".java": Language.JAVA, ".cs": Language.CSHARP, ".proto": Language.PROTOBUF,
}
_KINDS = {
    "file": SymbolKind.FILE, "module": SymbolKind.MODULE, "class": SymbolKind.CLASS,
    "interface": SymbolKind.INTERFACE, "function": SymbolKind.FUNCTION,
    "method": SymbolKind.METHOD, "variable": SymbolKind.VARIABLE,
    "parameter": SymbolKind.PARAMETER, "import": SymbolKind.IMPORT,
    "service": SymbolKind.INTERFACE, "rpc": SymbolKind.METHOD,
    "commit": SymbolKind.COMMIT,
}


def _plain(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return str(value)


def graph_to_document(graph: Any, root: Path, *, identity: str | None = None,
                      source_roots: dict[str, Path] | None = None) -> LNIRDocument:
    """Preserve GRAFT node IDs, layers, parallel edges, and hyper-edge metadata."""
    root = root.resolve()
    repo_id = repository_id(identity or str(root))
    commit = current_commit(root)
    repository = RepositoryNode(
        id=repo_id, path=str(root), git_remote=remote_url(root), commit_id=commit,
        metadata={"architecture": "graft"},
    )
    files: dict[str, FileNode] = {}
    symbols: dict[str, Symbol] = {}
    node_ids: dict[str, str] = {}
    for raw_id, data in graph.nodes(data=True):
        raw = str(raw_id)
        path = str(data.get("file") or "").replace("\\", "/")
        if not path and raw.startswith("file::"):
            path = raw.removeprefix("file::")
        if not path:
            path = "<workspace>"
        suffix = Path(path).suffix.lower()
        language = _EXTENSIONS.get(suffix, Language.UNKNOWN)
        kind = _KINDS.get(str(data.get("type", "")).lower(), SymbolKind.CODE_CHUNK)
        name = str(data.get("name") or raw.split(":")[-1])
        sid = stable_hash([repo_id, raw], "sym")
        node_ids[raw] = sid
        line = max(1, int(data.get("line_no") or 1))
        code = str(data.get("code") or "")
        doc = str(data.get("docstring") or "")
        symbols[sid] = Symbol(
            id=sid, repository_id=repo_id, commit_id=commit, language=language,
            kind=kind, name=name, qualified_name=raw, file_path=path,
            start_line=line, start_column=0, end_line=line, end_column=0,
            source_text=code or doc or None,
            metadata={"graft_id": raw, "layer": str(data.get("layer") or "Lsyn"),
                      "graft_type": str(data.get("type") or ""),
                      "repo": str(data.get("repo") or ""), "docstring": doc,
                      "graft_properties": _plain(dict(data))},
            provenance=Provenance.STATIC_ANALYSIS,
        )
        repo_name, _, repo_path = path.partition("/")
        local = ((source_roots or {}).get(repo_name, root / repo_name) / repo_path
                 if source_roots and repo_name in source_roots else root / path)
        if path != "<workspace>" and suffix in _EXTENSIONS and local.is_file():
            files[path] = FileNode(
                id=file_id(repo_id, commit, path), repository_id=repo_id,
                commit_id=commit, normalized_path=path, language=language,
                hash=file_sha256(local),
            )

    relations: dict[str, Relation] = {}
    for source, target, key, data in graph.edges(keys=True, data=True):
        relation_name = str(data.get("relation") or "REFERENCES")
        try:
            relation_type = RelationType(relation_name)
        except ValueError:
            relation_type = RelationType.REFERENCES
        source_id = node_ids[str(source)]
        target_id = node_ids[str(target)]
        rid = relation_id(repo_id, commit, source_id, target_id, relation_type, str(key))
        confidence = float(data.get("c_type", 1.0) or 0.0)
        relations[rid] = Relation(
            id=rid, repository_id=repo_id, commit_id=commit,
            source_symbol_id=source_id, target_symbol_id=target_id,
            relation_type=relation_type, confidence=max(0.0, min(1.0, confidence)),
            provenance=Provenance.STATIC_ANALYSIS if relation_type != RelationType.SEMANTIC_SIMILAR
            else Provenance.HEURISTIC,
            metadata={"layer": str(data.get("layer") or ""), "graft_relation": relation_name,
                      "graft_edge_key": str(key), "hyperedge": _plain(data.get("metadata") or {}),
                      "f_call": _plain(data.get("f_call")),
                      "id_ctx": _plain(data.get("id_ctx")),
                      "graft_properties": _plain(dict(data))},
        )
    return LNIRDocument(repository=repository, files=list(files.values()),
                        symbols=list(symbols.values()), relations=list(relations.values()))
