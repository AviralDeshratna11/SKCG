from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Annotated

import typer

from sckg.graph.json_store import JsonGraphStore
from sckg.graph.store import GraphStore
from sckg.indexing.pipeline import IndexingPipeline
from sckg.ir.enums import RelationType
from sckg.retrieval.egpot import EGPOTTraverser
from sckg.retrieval.egpot.serializer import explain_traversal
from sckg.retrieval.pipeline import RetrievalPipeline
from sckg.visualization.export import write_graph_html
from sckg.utils.config import load_yaml

app = typer.Typer(help="Semantic Code Knowledge Graph CLI")


@app.command("import-graph")
def import_graph_export(path: Annotated[Path, typer.Argument(exists=True)]) -> None:
    """Load a downloaded /api/graph or GRAFT JSON export into the selected store."""
    from sckg.graph.import_graph import import_graph, audit_graph
    document = import_graph(path)
    store = make_store()
    if not isinstance(store, JsonGraphStore):
        raise typer.BadParameter("import-graph currently requires the JSON store")
    store.replace_document(document)
    typer.echo(json.dumps(audit_graph(document), indent=2))


def make_store() -> GraphStore:
    if os.getenv("SCKG_STORE", "json").lower() == "neo4j":
        from sckg.graph.neo4j_store import Neo4jGraphStore

        return Neo4jGraphStore(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            os.getenv("NEO4J_USER", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "sckg-password"),
        )
    return JsonGraphStore(Path(os.getenv("SCKG_JSON_STORE", ".sckg/graph.json")))


def _print_symbols(symbols) -> None:
    for symbol in symbols:
        typer.echo(f"{symbol.qualified_name}\t{symbol.kind.value}\t{symbol.file_path}:{symbol.start_line}")


@app.command()
def index(
    repo: Annotated[Path, typer.Argument(exists=True)] ,
    architecture: str = typer.Option("lnir", help="lnir or graft"),
    workspace: bool = typer.Option(False, help="Treat path as a GRAFT workspace YAML file"),
    lineage: bool = typer.Option(False, help="Add Git commit TOUCHES edges to a GRAFT graph"),
    max_commits: int = typer.Option(200, help="Maximum Git commits for lineage"),
) -> None:
    pipeline = IndexingPipeline(make_store(), {"architecture": architecture,
                                              "lineage": lineage, "max_commits": max_commits})
    report = pipeline.index_workspace(repo) if workspace else pipeline.index(repo)
    typer.echo(
        f"indexed files={report.build.files} symbols={report.build.symbols} "
        f"relations={report.build.relations}"
    )
    typer.echo(f"relation_counts={report.manifest.relation_counts}")


@app.command()
def stats(repo: Annotated[Path | None, typer.Argument()] = None) -> None:
    _ = repo
    typer.echo(make_store().stats())


@app.command("find-symbol")
def find_symbol(query: str) -> None:
    _print_symbols(make_store().find_symbol(query))


@app.command()
def definition(symbol: str) -> None:
    hit = make_store().get_definition(symbol)
    if hit:
        _print_symbols([hit])


@app.command()
def references(symbol: str) -> None:
    _print_symbols(make_store().get_references(symbol))


@app.command()
def callers(symbol: str) -> None:
    _print_symbols(make_store().get_callers(symbol))


@app.command()
def callees(symbol: str) -> None:
    _print_symbols(make_store().get_callees(symbol))


@app.command()
def neighbors(symbol: str, depth: int = 1) -> None:
    symbols, relations = make_store().get_neighbors(symbol, depth=depth)
    _print_symbols(symbols)
    typer.echo(f"relations={len(relations)}")


@app.command()
def subgraph(symbol: str, depth: int = 1) -> None:
    symbols, relations = make_store().get_subgraph([symbol], depth=depth)
    _print_symbols(symbols)
    typer.echo(f"relations={len(relations)}")


@app.command()
def path(source: str, target: str) -> None:
    for relation in make_store().explain_path(source, target):
        typer.echo(f"{relation.source_symbol_id} {relation.relation_type.value} {relation.target_symbol_id}")


@app.command()
def search(query: str) -> None:
    _print_symbols(make_store().find_symbol(query))


@app.command()
def retrieve(
    issue: str,
    repo: Path = Path("."),
    token_budget: int | None = None,
    strategy: str = "hybrid",
    max_hops: int | None = None,
    beam_width: int | None = None,
    node_budget: int | None = None,
    direction: str | None = None,
    explain: bool = False,
    trace: Path | None = None,
    config: Path | None = None,
    suppress_hubs: bool | None = typer.Option(None, "--suppress-hubs/--no-suppress-hubs"),
    hub_degree_threshold: int | None = None,
    use_hash_sim: bool = False,
    embedding_provider: str | None = None,
    mcts: bool | None = typer.Option(None, "--mcts/--no-mcts"),
    simulation_budget: int | None = None,
    ucb_c: float | None = None,
) -> None:
    store = make_store()
    settings = load_yaml(config) if config else {}
    egpot = settings.setdefault("egpot", {})
    if not isinstance(egpot, dict):
        raise typer.BadParameter("egpot config must be a mapping")
    for key, value in {
        "hub_suppression_enabled": suppress_hubs, "hub_degree_threshold": hub_degree_threshold,
        "embedding_provider": "hashing" if use_hash_sim else embedding_provider,
        "mcts_enabled": mcts, "simulation_budget": simulation_budget, "ucb_c": ucb_c,
        "node_budget": node_budget,
    }.items():
        if value is not None:
            egpot[key] = value
    if direction is not None:
        traversal = egpot.setdefault("traversal", {})
        if not isinstance(traversal, dict):
            raise typer.BadParameter("egpot.traversal config must be a mapping")
        traversal["direction"] = direction
    result = RetrievalPipeline(store, repo.resolve(), settings).retrieve(
        issue,
        token_budget,
        strategy=strategy,
        max_hops=max_hops,
        beam_width=beam_width,
    )
    if explain and result.egpot_result is not None:
        typer.echo(explain_traversal(result.egpot_result))
        typer.echo("")
    if trace and result.egpot_result is not None:
        EGPOTTraverser(store).write_trace(result.egpot_result, trace)
        typer.echo(f"wrote EG-POT trace {trace}")
    typer.echo(result.context)


@app.command("relation-types")
def relation_types() -> None:
    for relation_type in RelationType:
        typer.echo(relation_type.value)


@app.command()
def visualize(
    output: Path = Path(".sckg/graph.html"),
    symbol: str | None = None,
    depth: int = 1,
    limit: int = 800,
    egpot_trace: Path | None = None,
    compare_trace: list[Path] = typer.Option([], "--compare-trace"),
) -> None:
    store = make_store()
    if symbol:
        symbols, relations = store.get_subgraph([symbol], depth=depth)
        title = f"SCKG Subgraph: {symbol}"
    elif isinstance(store, JsonGraphStore):
        symbols = list(store.symbols.values())[:limit]
        selected = {item.id for item in symbols}
        relations = [
            relation
            for relation in store.relations.values()
            if relation.source_symbol_id in selected and relation.target_symbol_id in selected
        ]
        title = "SCKG Graph"
    else:
        raise typer.BadParameter("Full graph visualization currently requires the JSON backend or --symbol.")

    trace_data = None
    if egpot_trace:
        trace_data = json.loads(egpot_trace.read_text(encoding="utf-8"))
        title = f"{title} + EG-POT"
    if compare_trace and not trace_data:
        raise typer.BadParameter("--compare-trace requires --egpot-trace")
    comparisons = {f"{index + 1}. {path.stem}": json.loads(path.read_text(encoding="utf-8"))
                   for index, path in enumerate(compare_trace)}
    path = write_graph_html(output, symbols, relations, title, egpot_trace=trace_data,
                            comparison_traces=comparisons)
    typer.echo(f"wrote {path} with {len(symbols)} nodes and {len(relations)} relations")


if __name__ == "__main__":
    app()
