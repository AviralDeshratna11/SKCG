from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from sckg.ir.enums import Language, RelationType, SymbolKind


def normalize_repo_path(path: str) -> str:
    return path.replace("\\", "/").rstrip("/")


def normalize_file_path(path: str) -> str:
    return str(PurePosixPath(path.replace("\\", "/")))


def stable_hash(parts: list[str], prefix: str) -> str:
    canonical = "\x1f".join(part.strip() for part in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def repository_id(repository_identity: str) -> str:
    return stable_hash([normalize_repo_path(repository_identity)], "repo")


def file_id(repository_id_value: str, commit_id: str, normalized_path: str) -> str:
    return stable_hash([repository_id_value, commit_id, normalize_file_path(normalized_path)], "file")


def symbol_id(
    repository_id_value: str,
    normalized_path: str,
    language: Language,
    qualified_name: str,
    kind: SymbolKind,
    signature: str | None = None,
) -> str:
    return stable_hash(
        [
            repository_id_value,
            normalize_file_path(normalized_path),
            language.value,
            qualified_name,
            kind.value,
            signature or "",
        ],
        "sym",
    )


def relation_id(
    repository_id_value: str,
    commit_id: str,
    source_symbol_id: str,
    target_symbol_id: str,
    relation_type: RelationType,
    source_location_key: str = "",
) -> str:
    return stable_hash(
        [
            repository_id_value,
            commit_id,
            source_symbol_id,
            relation_type.value,
            target_symbol_id,
            source_location_key,
        ],
        "rel",
    )
