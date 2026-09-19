from __future__ import annotations

from collections import Counter
from pathlib import Path

from sckg import __version__
from sckg.graph.schema import SCHEMA_VERSION
from sckg.ir.models import IndexManifest, LNIRDocument
from sckg.utils.hash import configuration_hash


def create_manifest(document: LNIRDocument, config: dict[str, object]) -> IndexManifest:
    return IndexManifest(
        repository=document.repository.path,
        commit_sha=document.repository.commit_id,
        indexer_version=__version__,
        schema_version=SCHEMA_VERSION,
        language_frontends={document.files[0].language.value: __version__} if document.files else {},
        configuration_hash=configuration_hash(config),
        files_scanned=len(document.files),
        files_parsed=len(document.files),
        files_failed=0,
        symbols_extracted=len(document.symbols),
        relations_extracted=len(document.relations),
        relation_counts=dict(Counter(rel.relation_type.value for rel in document.relations)),
    )


def write_manifest(document: LNIRDocument, config: dict[str, object], output_dir: Path) -> IndexManifest:
    manifest = create_manifest(document, config)
    manifest.write(output_dir / "manifest.json")
    return manifest
