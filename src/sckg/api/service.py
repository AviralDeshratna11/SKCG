from __future__ import annotations

from pathlib import Path

from sckg.api.tools import SCKGTools
from sckg.graph.store import GraphStore


def create_tools(store: GraphStore, repo_path: Path) -> SCKGTools:
    return SCKGTools(store, repo_path)
