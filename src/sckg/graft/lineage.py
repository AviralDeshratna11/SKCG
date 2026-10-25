"""
lineage.py  —  GRAFT-CKG Layer 3: Git Lineage Layer (L_lineage)
================================================================
Paper Section IV-B / Equation (5): Extends the four-layer CKG with
developer/commit provenance by parsing git log --numstat output and
attaching TOUCHES hyper-edges from commit::<sha> nodes to the
file/function nodes already present in the graph.

This enables:
  - SCKGTraversal.who_changed(symbol) — "which commit last touched this function?"
  - Blame-aware blast-radius (surfaces commits that changed a callee,
    helping root-cause regressions).
  - Temporal coupling detection: two symbols that change together in the same
    commit share a co-change weight on their TOUCHES edges.

Graph additions
---------------
Node types added:
  commit::<sha>  (type="commit", layer="Llineage")
    attrs: sha, message (first 72 chars), author, date, files_changed

Edge types added:
  TOUCHES  commit::<sha>  →  file::<rel_path>   (layer="Llineage")
    attrs: lines_added, lines_removed, net_delta

Usage
-----
  from lineage import LineageLayer
  from sckg.graft.graft_ckg import CKGBuilder

  builder = CKGBuilder("path/to/repo")
  builder.build()

  lineage = LineageLayer(builder)
  lineage.ingest(max_commits=200)     # parse git history

  # Who last touched place_order?
  info = lineage.who_changed("place_order")
  print(info)

  # Get full commit provenance for a file
  commits = lineage.file_history("services/order_service.py")
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import networkx as nx




# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CommitRecord:
    sha: str
    message: str
    author: str
    date: str
    files: List[Tuple[int, int, str]] = field(default_factory=list)
    """files: list of (lines_added, lines_removed, rel_path)"""


# ---------------------------------------------------------------------------
# Lineage Layer
# ---------------------------------------------------------------------------

class LineageLayer:
    """
    Parses git history for a repository and enriches the CKG with
    commit provenance nodes and TOUCHES edges (L_lineage).

    Parameters
    ----------
    builder : CKGBuilder
        An already-built CKGBuilder instance.
    """

    LAYER = "Llineage"

    def __init__(self, builder):
        self.builder = builder
        self.repo_path: str = builder.repo_path
        self.graph: nx.MultiDiGraph = builder.graph
        self.commits: Dict[str, CommitRecord] = {}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def ingest(self, max_commits: int = 500, branch: str = "HEAD") -> int:
        """
        Parse up to max_commits commits from git log and attach TOUCHES edges.
        Returns the number of commit nodes added to the graph.
        """
        raw = self._run_git_log(max_commits, branch)
        if raw is None:
            print(f"[!] lineage: no git repository found at {self.repo_path}")
            return 0

        self.commits = self._parse_git_log(raw)
        added = 0
        for sha, rec in self.commits.items():
            self._add_commit_node(rec)
            added += 1
            for lines_add, lines_del, rel_path in rec.files:
                self._add_touches_edge(sha, rel_path, lines_add, lines_del)

        print(f"[*] Lineage Layer (Llineage): {added} commits, "
              f"{self._count_lineage_edges()} TOUCHES edges added.")
        return added

    def who_changed(self, symbol_or_file: str, top_n: int = 5) -> List[Dict]:
        """
        Return the 	op_n most recent commits that touched a symbol or file.

        symbol_or_file can be:
          - A simple function/class name (e.g. "place_order")
          - A relative file path (e.g. "services/order_service.py")
          - A CKG node ID fragment

        Returns a list of dicts with keys: sha, message, author, date, lines_added, lines_removed.
        """
        results = []
        query = symbol_or_file.lower()

        # First: find matching file paths touched by commits
        matching_files = set()
        for sha, rec in self.commits.items():
            for _, _, rel_path in rec.files:
                if query in rel_path.lower():
                    matching_files.add(rel_path)

        # Second: find CKG nodes that match the query and get their file
        for nid, data in self.graph.nodes(data=True):
            name = data.get("name", "")
            file_ = data.get("file", "")
            if query in nid.lower() or query in name.lower():
                if file_:
                    matching_files.add(file_)

        # Collect commits that touch any matching file
        for sha, rec in self.commits.items():
            for lines_add, lines_del, rel_path in rec.files:
                if rel_path in matching_files:
                    results.append({
                        "sha": sha[:12],
                        "message": rec.message,
                        "author": rec.author,
                        "date": rec.date,
                        "file": rel_path,
                        "lines_added": lines_add,
                        "lines_removed": lines_del,
                    })
                    break

        # Sort by date descending (git log is already newest-first)
        return results[:top_n]

    def file_history(self, rel_path: str) -> List[Dict]:
        """
        Return all commits that modified `rel_path`, newest first.
        """
        norm = rel_path.replace("\\\\", "/")
        history = []
        for sha, rec in self.commits.items():
            for la, lr, fp in rec.files:
                if fp == norm or fp.endswith(norm):
                    history.append({
                        "sha": sha[:12],
                        "message": rec.message,
                        "author": rec.author,
                        "date": rec.date,
                        "file": fp,
                        "lines_added": la,
                        "lines_removed": lr,
                    })
                    break
        return history

    def co_change_weight(self, path_a: str, path_b: str) -> float:
        """
        Temporal coupling weight: fraction of commits that touch both path_a
        and path_b simultaneously (Jaccard co-change coefficient).
        """
        set_a = set()
        set_b = set()
        for sha, rec in self.commits.items():
            files = {fp for _, _, fp in rec.files}
            if path_a in files:
                set_a.add(sha)
            if path_b in files:
                set_b.add(sha)
        union = set_a | set_b
        if not union:
            return 0.0
        return len(set_a & set_b) / len(union)

    def export_lineage_subgraph(self) -> nx.DiGraph:
        """
        Return a simple DiGraph containing only commit nodes and TOUCHES edges.
        Useful for standalone lineage analysis or Neo4j export.
        """
        sg = nx.DiGraph()
        for nid, data in self.graph.nodes(data=True):
            if data.get("layer") == self.LAYER:
                sg.add_node(nid, **data)
        for u, v, data in self.graph.edges(data=True):
            if data.get("relation") == "TOUCHES":
                sg.add_edge(u, v, **data)
        return sg

    # -----------------------------------------------------------------------
    # Internal: git log parsing
    # -----------------------------------------------------------------------

    def _run_git_log(self, max_commits: int, branch: str) -> Optional[str]:
        """Run git log --numstat and return raw output, or None if git unavailable."""
        try:
            result = subprocess.run(
                [
                    "git", "log",
                    f"-{max_commits}",
                    "--numstat",
                    "--format=COMMIT:%H%nAUTHOR:%an%nDATE:%ad%nMSG:%s",
                    "--date=short",
                    branch,
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return None
            return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def _parse_git_log(self, raw: str) -> Dict[str, CommitRecord]:
        """Parse --numstat output into CommitRecord objects."""
        commits: Dict[str, CommitRecord] = {}
        current: Optional[CommitRecord] = None

        for line in raw.splitlines():
            line = line.rstrip()
            if line.startswith("COMMIT:"):
                current = CommitRecord(
                    sha=line[7:].strip(),
                    message="",
                    author="",
                    date="",
                )
                commits[current.sha] = current
            elif line.startswith("AUTHOR:") and current:
                current.author = line[7:].strip()
            elif line.startswith("DATE:") and current:
                current.date = line[5:].strip()
            elif line.startswith("MSG:") and current:
                current.message = line[4:].strip()[:72]
            elif current and re.match(r"^\d+\s+\d+\s+", line):
                parts = line.split(None, 2)
                if len(parts) == 3:
                    try:
                        la = int(parts[0])
                        lr = int(parts[1])
                    except ValueError:
                        la = lr = 0
                    fp = parts[2].replace("\\\\", "/")
                    current.files.append((la, lr, fp))

        return commits

    # -----------------------------------------------------------------------
    # Internal: graph mutation
    # -----------------------------------------------------------------------

    def _add_commit_node(self, rec: CommitRecord) -> str:
        node_id = f"commit::{self.builder.repo_prefix}{rec.sha[:12]}"
        self.graph.add_node(
            node_id,
            type="commit",
            layer=self.LAYER,
            sha=rec.sha,
            message=rec.message,
            author=rec.author,
            date=rec.date,
            files_changed=len(rec.files),
        )
        return node_id

    def _add_touches_edge(self, sha: str, rel_path: str, lines_add: int, lines_del: int):
        commit_node = f"commit::{self.builder.repo_prefix}{sha[:12]}"
        # Try to find an exact file node in the CKG
        file_node = f"file::{self.builder.repo_prefix}{rel_path}"
        if not self.graph.has_node(file_node):
            # Fallback: add a lightweight file node
            self.graph.add_node(
                file_node,
                type="file",
                layer=self.LAYER,
                file=rel_path,
                name=os.path.basename(rel_path),
            )
        if self.graph.has_node(commit_node):
            self.graph.add_edge(
                commit_node,
                file_node,
                relation="TOUCHES",
                layer=self.LAYER,
                lines_added=lines_add,
                lines_removed=lines_del,
                net_delta=lines_add - lines_del,
            )

    def _count_lineage_edges(self) -> int:
        return sum(
            1 for _, _, d in self.graph.edges(data=True)
            if d.get("relation") == "TOUCHES"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    import argparse
    parser = argparse.ArgumentParser(
        description="GRAFT-CKG Git Lineage Layer — attach commit provenance to CKG"
    )
    parser.add_argument("repo", help="Path to a git repository")
    parser.add_argument("--max-commits", type=int, default=200,
                        help="Maximum commits to parse (default 200)")
    parser.add_argument("--who-changed", metavar="SYMBOL",
                        help="Print which commits last touched SYMBOL")
    parser.add_argument("--file-history", metavar="REL_PATH",
                        help="Print commit history for a file")
    parser.add_argument("--co-change", nargs=2, metavar=("PATH_A", "PATH_B"),
                        help="Print temporal coupling weight between two files")
    args = parser.parse_args()

    from sckg.graft.graft_ckg import CKGBuilder
    builder = CKGBuilder(args.repo)
    builder.build()
    layer = LineageLayer(builder)
    layer.ingest(max_commits=args.max_commits)

    if args.who_changed:
        import json
        results = layer.who_changed(args.who_changed)
        print(json.dumps(results, indent=2))

    if args.file_history:
        import json
        results = layer.file_history(args.file_history)
        print(json.dumps(results, indent=2))

    if args.co_change:
        w = layer.co_change_weight(args.co_change[0], args.co_change[1])
        print(f"Co-change weight ({args.co_change[0]} <-> {args.co_change[1]}): {w:.4f}")


if __name__ == "__main__":
    _cli()

