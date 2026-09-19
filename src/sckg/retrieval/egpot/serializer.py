from __future__ import annotations

from sckg.retrieval.egpot.models import TraversalResult


def explain_traversal(result: TraversalResult) -> str:
    lines = [
        "EG-POT Traversal",
        "",
        f"Search: {'Beam-MCTS' if result.debug.get('mcts_enabled') else 'Pareto beam'}",
        f"Simulations: {result.debug.get('simulations', 0)}",
        f"Embedding provider: {result.debug.get('embedding_provider', 'unknown')}",
        "",
        "Seed nodes:",
    ]
    for seed in result.seed_nodes:
        lines.append(
            f"- {seed.symbol.qualified_name} score={seed.score:.3f} "
            f"lexical={seed.lexical_score:.3f} semantic={seed.semantic_score:.3f}"
        )
    lines.extend(["", "Selected trajectories:"])
    for index, trajectory in enumerate(result.best_trajectories, start=1):
        lines.append(f"Path {index}:")
        lines.append(f"  [0] {trajectory.nodes[0].qualified_name} ({trajectory.nodes[0].file_path})")
        for hop in trajectory.hops:
            lines.append(
                f"  [{hop.hop_number}] {hop.relation.relation_type.value} -> "
                f"{hop.target.qualified_name} ({hop.target.file_path})"
            )
            lines.append(f"      {hop.reason}")
    lines.extend(
        [
            "",
            f"Stop reason: {result.stop_reason.value}",
            f"Visited nodes: {len(result.visited_nodes)}",
            f"Selected nodes: {len(result.selected_nodes)}",
            f"Selected edges: {len(result.selected_edges)}",
            f"Traversal time: {result.traversal_time:.4f}s",
        ]
    )
    return "\n".join(lines)
