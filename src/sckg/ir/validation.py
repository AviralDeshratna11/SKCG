from __future__ import annotations

from collections import Counter

from sckg.ir.models import LNIRDocument


def validate_unique_ids(document: LNIRDocument) -> None:
    ids = [document.repository.id]
    ids.extend(file.id for file in document.files)
    ids.extend(symbol.id for symbol in document.symbols)
    ids.extend(relation.id for relation in document.relations)
    duplicates = [item for item, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise ValueError(f"duplicate LNIR ids: {duplicates}")
