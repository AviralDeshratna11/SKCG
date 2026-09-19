from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sckg.ir.enums import Language, Provenance, RelationType, SymbolKind


class SourceLocation(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_path: str
    start_line: int = Field(ge=1)
    start_column: int = Field(ge=0)
    end_line: int = Field(ge=1)
    end_column: int = Field(ge=0)

    @property
    def key(self) -> str:
        return (
            f"{self.file_path}:{self.start_line}:{self.start_column}:"
            f"{self.end_line}:{self.end_column}"
        )


class RepositoryNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    path: str
    git_remote: str | None = None
    commit_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class FileNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    repository_id: str
    commit_id: str
    normalized_path: str
    language: Language
    hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Symbol(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    repository_id: str
    commit_id: str
    language: Language
    kind: SymbolKind
    name: str
    qualified_name: str
    signature: str | None = None
    type: str | None = None
    file_path: str
    start_line: int = Field(ge=1)
    start_column: int = Field(ge=0)
    end_line: int = Field(ge=1)
    end_column: int = Field(ge=0)
    source_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Provenance = Provenance.AST

    @property
    def location(self) -> SourceLocation:
        return SourceLocation(
            file_path=self.file_path,
            start_line=self.start_line,
            start_column=self.start_column,
            end_line=self.end_line,
            end_column=self.end_column,
        )


class Relation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    repository_id: str
    commit_id: str
    source_symbol_id: str
    target_symbol_id: str
    relation_type: RelationType
    source_location: SourceLocation | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Provenance
    metadata: dict[str, Any] = Field(default_factory=dict)


class LNIRDocument(BaseModel):
    repository: RepositoryNode
    files: list[FileNode] = Field(default_factory=list)
    symbols: list[Symbol] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)

    @field_validator("relations")
    @classmethod
    def relation_symbols_must_exist(cls, relations: list[Relation], info: Any) -> list[Relation]:
        data = info.data
        symbols = data.get("symbols", [])
        symbol_ids = {symbol.id for symbol in symbols}
        missing = [
            relation.id
            for relation in relations
            if relation.source_symbol_id not in symbol_ids or relation.target_symbol_id not in symbol_ids
        ]
        if missing:
            raise ValueError(f"relations reference missing symbols: {missing}")
        return relations


class IndexManifest(BaseModel):
    repository: str
    commit_sha: str
    indexer_version: str
    schema_version: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    language_frontends: dict[str, str]
    configuration_hash: str
    files_scanned: int = 0
    files_parsed: int = 0
    files_failed: int = 0
    symbols_extracted: int = 0
    relations_extracted: int = 0
    relation_counts: dict[str, int] = Field(default_factory=dict)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
