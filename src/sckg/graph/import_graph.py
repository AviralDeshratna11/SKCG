"""Import the graph explorer API/export without rebuilding or inventing edges."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sckg.graft.adapter import _EXTENSIONS, _KINDS
from sckg.ir.enums import Language, Provenance, RelationType, SymbolKind
from sckg.ir.ids import stable_hash
from sckg.ir.models import LNIRDocument, Relation, RepositoryNode, Symbol


def import_graph(path: Path) -> LNIRDocument:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if "symbols" in data:
        repos = data.get("repositories", [])
        if len(repos) != 1:
            raise ValueError("LNIR import requires exactly one repository")
        return LNIRDocument(repository=repos[0], files=data.get("files", []),
                            symbols=data["symbols"], relations=data.get("relations", []))
    repository = RepositoryNode(id="export", path=str(path.resolve()), commit_id="snapshot",
                                metadata={"source": data.get("source", str(path))})
    symbols = []
    ids: set[str] = set()
    kinds = {**_KINDS, "service_contract": SymbolKind.INTERFACE,
             "rpc_contract": SymbolKind.METHOD, "external_func": SymbolKind.FUNCTION}
    for node in data["nodes"]:
        node_id = str(node["id"])
        if node_id in ids:
            raise ValueError(f"Duplicate node ID: {node_id}")
        ids.add(node_id)
        line = max(1, int(node.get("line", node.get("line_no", 1)) or 1))
        file = str(node.get("file") or "<external>")
        symbols.append(Symbol(
            id=node_id, repository_id=repository.id, commit_id=repository.commit_id,
            language=_EXTENSIONS.get(Path(file).suffix, Language.UNKNOWN),
            kind=kinds.get(node.get("type", ""), SymbolKind.CODE_CHUNK),
            name=node.get("name") or node.get("label") or node_id,
            qualified_name=node_id, file_path=file, start_line=line, start_column=0,
            end_line=max(line, int(node.get("end_line") or line)), end_column=0,
            source_text=node.get("code"), type=node.get("signature_type"),
            metadata={"graft_id": node_id, "layer": node.get("layer", ""),
                      "graft_type": node.get("type", ""), "graft_properties": node},
            provenance=Provenance.STATIC_ANALYSIS))
    relations = []
    for i, edge in enumerate(data.get("edges", data.get("links", []))):
        source, target = str(edge["source"]), str(edge["target"])
        if source not in ids or target not in ids:
            raise ValueError(f"Dangling edge {i}: {source} -> {target}")
        # Unknown relations fail explicitly instead of silently becoming REFERENCES.
        kind = RelationType(edge["relation"])
        confidence = edge.get("confidence", edge.get("c_type"))
        if confidence is not None:
            confidence = float(confidence)
            if not -1e-12 <= confidence <= 1 + 1e-12:
                raise ValueError(f"Invalid confidence at edge {i}: {confidence}")
            confidence = max(0.0, min(1.0, confidence))
        relations.append(Relation(
            id=stable_hash([source, target, kind.value, str(i)], "rel"),
            repository_id=repository.id, commit_id=repository.commit_id,
            source_symbol_id=source, target_symbol_id=target, relation_type=kind,
            confidence=0.6 if confidence is None else float(confidence),
            provenance=Provenance.HEURISTIC if confidence is None
            or kind == RelationType.SEMANTIC_SIMILAR else Provenance.STATIC_ANALYSIS,
            metadata={"layer": edge.get("layer", ""), "graft_properties": edge,
                      "confidence_available": confidence is not None}))
    return LNIRDocument(repository=repository, symbols=symbols, relations=relations)


def audit_graph(document: LNIRDocument) -> dict[str, Any]:
    edges = document.relations
    unique = {(e.source_symbol_id, e.target_symbol_id, e.relation_type) for e in edges}
    return {
        "nodes": len(document.symbols), "edges": len(edges),
        "parallel_edges": len(edges) - len(unique),
        "relations": dict(Counter(e.relation_type.value for e in edges)),
        "layers": dict(Counter(n.metadata.get("layer", "") for n in document.symbols)),
        "missing_source_text": sum(not n.source_text for n in document.symbols),
        "missing_confidence": sum(not e.metadata.get("confidence_available", True) for e in edges),
        "contract_edges": sum(e.relation_type in {RelationType.CONSUMES,
            RelationType.IMPLEMENTS, RelationType.DEFINES_RPC} for e in edges),
    }
