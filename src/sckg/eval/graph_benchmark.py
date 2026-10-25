"""Seed-controlled retrieval benchmarks. Gold labels are used only by the scorer.

Budgets count unique admitted nodes (including seeds), not embedding evaluations.
All methods use the same immutable, bidirectional graph and supplied start function.
Vector retrieval and community retrieval are global methods and do not claim paths.
"""
from __future__ import annotations

import math
import random
import time
from collections import defaultdict, deque
from dataclasses import replace
from functools import lru_cache
from typing import Any

import networkx as nx
import numpy as np

from sckg.graph.json_store import JsonGraphStore
from sckg.retrieval.egpot import EGPOTConfig, EGPOTTraverser
from sckg.retrieval.seeds import Seed
from sckg.retrieval.semantic import EmbeddingProvider


METHODS = ("vector", "vector_bfs_2", "vector_bfs_3", "vector_bfs_4", "vector_bfs_5",
           "ppr", "beam", "greedy", "community", "standard_mcts", "egpot",
           "weighted_sum", "no_entropy", "no_contracts", "no_mcts", "expanded_budget")


class Benchmark:
    def __init__(self, store: JsonGraphStore, provider: EmbeddingProvider) -> None:
        self.store, self.provider = store, provider
        self.ids = sorted(store.symbols)
        self.index = {node: i for i, node in enumerate(self.ids)}
        self.graph = nx.Graph()
        self.graph.add_nodes_from(self.ids)
        self.graph.add_edges_from((e.source_symbol_id, e.target_symbol_id)
                                  for e in store.relations.values()
                                  if e.source_symbol_id != e.target_symbol_id)
        # Required dependency/algorithm: no connected-component substitute for Louvain.
        self.communities = nx.community.louvain_communities(self.graph, seed=0)
        self.matrix = np.asarray([provider.embed(self.text(n)) for n in self.ids])
        norms = np.linalg.norm(self.matrix, axis=1, keepdims=True)
        self.matrix /= np.maximum(norms, 1e-12)
        self.adj = {n: sorted(self.graph[n]) for n in self.ids}

    def text(self, node: str) -> str:
        s = self.store.symbols[node]
        return " ".join(filter(None, [s.name, s.qualified_name, s.signature, s.type,
                                       s.file_path, s.source_text]))

    @lru_cache(maxsize=256)
    def scores(self, query: str) -> dict[str, float]:
        v = np.asarray(self.provider.embed(query))
        v /= max(float(np.linalg.norm(v)), 1e-12)
        return dict(zip(self.ids, (self.matrix @ v).tolist(), strict=True))

    def run(self, method: str, query: str, start: str, budget: int, seed: int,
            *, provider_name: str = "hashing") -> dict[str, Any]:
        if method not in METHODS or start not in self.index or budget < 1:
            raise ValueError("Invalid method, exact start ID, or budget")
        begin = time.perf_counter()
        scores = self.scores(query)
        rng = random.Random(seed)
        # Seed affects ties/exploration only, never targets or query wording.
        tie = {n: rng.random() for n in self.ids}
        ranked = sorted(self.ids, key=lambda n: (-scores[n], tie[n], n))
        paths: list[tuple[str, ...]] = []
        selected: list[str] = []
        visited = {start}
        effective_budget = budget * 2 if method == "expanded_budget" else budget

        def admit(path: tuple[str, ...]) -> bool:
            if len(visited | set(path)) > effective_budget:
                return False
            visited.update(path)
            paths.append(path)
            return True

        if method in {"egpot", "weighted_sum", "no_entropy", "no_contracts",
                      "no_mcts", "expanded_budget"}:
            cfg = EGPOTConfig(embedding_provider=provider_name, node_budget=effective_budget,
                              embedding_local_files_only=True)
            changes = {"weighted_sum": {"pareto_enabled": False},
                       "no_entropy": {"entropy_enabled": False},
                       "no_contracts": {"contract_enabled": False},
                       "no_mcts": {"mcts_enabled": False}}
            cfg = replace(cfg, **changes.get(method, {}))
            result = EGPOTTraverser(self.store, cfg, self.provider).traverse(
                query, [Seed(self.store.symbols[start], scores[start], 0, scores[start], ())])
            selected = [n.id for n in result.selected_nodes]
            visited = {n.id for n in result.visited_nodes}
            paths = [p.node_ids for p in result.best_trajectories]
        elif method == "vector":
            selected = [start] + [n for n in ranked if n != start][:effective_budget - 1]
            visited.update(selected)
        elif method.startswith("vector_bfs_"):
            # Vector-ranked neighbor order, common start, depth-limited BFS.
            depth = int(method[-1])
            queue = deque([(start,)])
            while queue and len(visited) < effective_budget:
                path = queue.popleft()
                if len(path) - 1 >= depth:
                    continue
                for n in sorted(self.adj[path[-1]], key=lambda n: (-scores[n], tie[n])):
                    if n not in visited and admit((*path, n)):
                        queue.append((*path, n))
            selected = list(visited)
        elif method == "ppr":
            values = nx.pagerank(self.graph, alpha=0.85,
                                 personalization={n: float(n == start) for n in self.ids})
            selected = [start] + sorted((n for n in self.ids if n != start),
                                        key=lambda n: (-values[n], tie[n]))[:effective_budget - 1]
            visited.update(selected)
        elif method == "community":
            ordered = sorted(self.communities,
                             key=lambda c: -sum(max(0, scores[n]) for n in c) / math.sqrt(len(c)))
            selected = [start]
            for community in ordered:
                for n in sorted(community, key=lambda n: (-scores[n], tie[n])):
                    if n not in visited and len(visited) < effective_budget:
                        selected.append(n)
                        visited.add(n)
        elif method in {"beam", "greedy"}:
            beam = [(start,)]
            width = 1 if method == "greedy" else 5
            for _ in range(5):
                candidates = [(*p, n) for p in beam for n in self.adj[p[-1]] if n not in p]
                candidates.sort(key=lambda p: (-scores[p[-1]], tie[p[-1]], p))
                beam = []
                for p in candidates:
                    if admit(p):
                        beam.append(p)
                    if len(beam) >= width:
                        break
                if not beam:
                    break
            selected = list(visited)
        else:
            # Standard UCT Monte Carlo tree search: random rollouts, no Pareto filter.
            counts: dict[tuple[str, ...], int] = defaultdict(int)
            rewards: dict[tuple[str, ...], float] = defaultdict(float)
            children: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
            for _ in range(64):
                path = (start,)
                ancestors = [path]
                while len(path) <= 5:
                    if path not in children:
                        children[path] = [(*path, n) for n in self.adj[path[-1]] if n not in path
                                          and (n in visited or len(visited) < effective_budget)]
                        rng.shuffle(children[path])
                    available = [p for p in children[path]
                                 if len(visited | set(p)) <= effective_budget]
                    if not available:
                        break
                    path = max(available, key=lambda p: float("inf") if not counts[p] else
                               rewards[p] / counts[p] + 1.4 * math.sqrt(
                                   math.log(max(1, counts[ancestors[-1]])) / counts[p]))
                    admit(path)
                    ancestors.append(path)
                for p in ancestors:
                    counts[p] += 1
                    rewards[p] += scores[path[-1]]
            selected = list(visited)
        assert len(visited) <= effective_budget
        # Ranking is identical for every method; traversal determines candidate membership.
        selected.sort(key=lambda n: (-scores[n], n))
        return {"selected": selected, "visited": len(visited), "paths": paths,
                "latency_ms": (time.perf_counter() - begin) * 1000,
                "effective_budget": effective_budget}


def score_result(result: dict[str, Any], gold: dict[str, Any]) -> dict[str, float]:
    target = gold["target"]
    ranked = result["selected"]
    rank = ranked.index(target) + 1 if target in ranked else 0
    expected = gold["path"]
    covered = set(ranked)
    ordered = any(all(n in path for n in expected)
                  and [path.index(n) for n in expected] == sorted(path.index(n) for n in expected)
                  for path in result["paths"])
    return {"hit": float(bool(rank)), "hits_at_1": float(rank == 1),
            "hits_at_5": float(0 < rank <= 5), "mrr_at_5": 1 / rank if 0 < rank <= 5 else 0,
            "path_coverage": sum(n in covered for n in expected) / len(expected),
            "ordered_path": float(ordered),
            "redundancy": 1 - len(covered & set(expected)) / max(1, len(covered)),
            "latency_ms": result["latency_ms"], "visited": result["visited"]}
