from __future__ import annotations

from pathlib import Path
from typing import Protocol

from sckg.ir.models import LNIRDocument


class LanguageFrontend(Protocol):
    language: str
    version: str

    def index_repository(self, repo_path: Path, repository_identity: str | None = None) -> LNIRDocument:
        """Produce language-neutral IR for a repository."""
