from __future__ import annotations

from collections.abc import Iterable

from neo4j import Driver, GraphDatabase

from sckg.graph.store import GraphStore
from sckg.ir.enums import RelationType
from sckg.ir.models import FileNode, Relation, RepositoryNode, Symbol


class Neo4jGraphStore(GraphStore):
    def __init__(self, uri: str, user: str, password: str) -> None:
        self.driver: Driver = GraphDatabase.driver(uri, auth=(user, password))
        self.ensure_schema()

    def close(self) -> None:
        self.driver.close()

    def ensure_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT repository_id IF NOT EXISTS FOR (r:Repository) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (f:File) REQUIRE f.id IS UNIQUE",
            "CREATE CONSTRAINT symbol_id IF NOT EXISTS FOR (s:Symbol) REQUIRE s.id IS UNIQUE",
            "CREATE INDEX symbol_qn IF NOT EXISTS FOR (s:Symbol) ON (s.qualified_name)",
            "CREATE INDEX symbol_commit IF NOT EXISTS FOR (s:Symbol) ON (s.commit_id)",
            "CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.normalized_path)",
            "CREATE INDEX repo_commit IF NOT EXISTS FOR (r:Repository) ON (r.commit_id)",
        ]
        with self.driver.session() as session:
            for statement in statements:
                session.run(statement)

    def upsert_repository(self, repository: RepositoryNode) -> None:
        self._batch_nodes("Repository", [repository.model_dump(mode="json")])

    def upsert_file(self, file: FileNode) -> None:
        self._batch_nodes("File", [file.model_dump(mode="json")])

    def upsert_symbol(self, symbol: Symbol) -> None:
        self._batch_nodes("Symbol", [symbol.model_dump(mode="json")])

    def upsert_symbols(self, symbols: list[Symbol]) -> None:
        self._batch_nodes("Symbol", [symbol.model_dump(mode="json") for symbol in symbols])

    def upsert_relation(self, relation: Relation) -> None:
        self.upsert_relations([relation])

    def upsert_relations(self, relations: list[Relation]) -> None:
        grouped: dict[str, list[dict[str, object]]] = {}
        for relation in relations:
            grouped.setdefault(relation.relation_type.value, []).append(relation.model_dump(mode="json"))
        with self.driver.session() as session:
            for rel_type, rows in grouped.items():
                session.run(
                    f"""
                    UNWIND $rows AS row
                    MATCH (source:Symbol {{id: row.source_symbol_id}})
                    MATCH (target:Symbol {{id: row.target_symbol_id}})
                    MERGE (source)-[r:{rel_type} {{id: row.id}}]->(target)
                    SET r += row
                    """,
                    rows=rows,
                )

    def _batch_nodes(self, label: str, rows: Iterable[dict[str, object]]) -> None:
        with self.driver.session() as session:
            session.run(
                f"""
                UNWIND $rows AS row
                MERGE (n:{label} {{id: row.id}})
                SET n += row
                """,
                rows=list(rows),
            )

    def find_symbol(self, query: str, limit: int = 20) -> list[Symbol]:
        with self.driver.session() as session:
            records = session.run(
                """
                MATCH (s:Symbol)
                WHERE toLower(s.qualified_name) CONTAINS toLower($query)
                   OR toLower(s.name) CONTAINS toLower($query)
                RETURN properties(s) AS s
                ORDER BY s.qualified_name
                LIMIT $limit
                """,
                query=query,
                limit=limit,
            )
            return [Symbol.model_validate(record["s"]) for record in records]

    def get_symbol(self, symbol: str) -> Symbol | None:
        with self.driver.session() as session:
            record = session.run(
                """
                MATCH (s:Symbol)
                WHERE s.id = $symbol OR s.qualified_name = $symbol
                RETURN properties(s) AS s
                LIMIT 1
                """,
                symbol=symbol,
            ).single()
            if record:
                return Symbol.model_validate(record["s"])
        matches = self.find_symbol(symbol, 1)
        return matches[0] if matches else None

    def get_neighbors(
        self, symbol: str, relation_types: list[RelationType] | None = None, depth: int = 1
    ) -> tuple[list[Symbol], list[Relation]]:
        start = self.get_symbol(symbol)
        if start is None:
            return [], []
        rel_filter = [rel.value for rel in relation_types] if relation_types else None
        with self.driver.session() as session:
            records = session.run(
                """
                MATCH path=(s:Symbol {id: $id})-[rels*1..$depth]-(n:Symbol)
                WHERE $rel_filter IS NULL OR all(r IN rels WHERE type(r) IN $rel_filter)
                UNWIND nodes(path) AS node
                WITH collect(DISTINCT properties(node)) AS nodes, collect(rels) AS rel_groups
                UNWIND rel_groups AS group
                UNWIND group AS rel
                RETURN nodes, collect(DISTINCT properties(rel)) AS rels
                """,
                id=start.id,
                depth=depth,
                rel_filter=rel_filter,
            ).single()
            if not records:
                return [start], []
            return (
                [Symbol.model_validate(row) for row in records["nodes"]],
                [Relation.model_validate(row) for row in records["rels"]],
            )

    def get_callers(self, symbol: str) -> list[Symbol]:
        return self._incoming(symbol, RelationType.CALLS)

    def get_callees(self, symbol: str) -> list[Symbol]:
        return self._outgoing(symbol, RelationType.CALLS)

    def get_references(self, symbol: str) -> list[Symbol]:
        return self._incoming(symbol, RelationType.REFERENCES)

    def get_definition(self, symbol: str) -> Symbol | None:
        return self.get_symbol(symbol)

    def get_file_symbols(self, path: str) -> list[Symbol]:
        with self.driver.session() as session:
            records = session.run(
                "MATCH (s:Symbol {file_path: $path}) RETURN properties(s) AS s ORDER BY s.start_line",
                path=path,
            )
            return [Symbol.model_validate(record["s"]) for record in records]

    def get_subgraph(
        self, seeds: list[str], relations: list[RelationType] | None = None, depth: int = 1
    ) -> tuple[list[Symbol], list[Relation]]:
        symbols: dict[str, Symbol] = {}
        rels: dict[str, Relation] = {}
        for seed in seeds:
            nodes, edges = self.get_neighbors(seed, relations, depth)
            symbols.update({node.id: node for node in nodes})
            rels.update({edge.id: edge for edge in edges})
        return list(symbols.values()), list(rels.values())

    def explain_path(self, source: str, target: str, max_depth: int = 4) -> list[Relation]:
        source_symbol = self.get_symbol(source)
        target_symbol = self.get_symbol(target)
        if source_symbol is None or target_symbol is None:
            return []
        with self.driver.session() as session:
            record = session.run(
                """
                MATCH path=shortestPath((s:Symbol {id: $source})-[*1..$depth]->(t:Symbol {id: $target}))
                RETURN [r IN relationships(path) | properties(r)] AS rels
                """,
                source=source_symbol.id,
                target=target_symbol.id,
                depth=max_depth,
            ).single()
            return [Relation.model_validate(row) for row in record["rels"]] if record else []

    def stats(self) -> dict[str, int]:
        with self.driver.session() as session:
            record = session.run(
                """
                MATCH (n)
                WITH count(n) AS nodes
                MATCH ()-[r]->()
                RETURN nodes, count(r) AS relations
                """
            ).single()
            return {"nodes": record["nodes"], "relations": record["relations"]} if record else {}

    def _incoming(self, symbol: str, relation_type: RelationType) -> list[Symbol]:
        target = self.get_symbol(symbol)
        if target is None:
            return []
        with self.driver.session() as session:
            records = session.run(
                f"MATCH (s:Symbol)-[:{relation_type.value}]->(:Symbol {{id: $id}}) RETURN properties(s) AS s",
                id=target.id,
            )
            return [Symbol.model_validate(record["s"]) for record in records]

    def _outgoing(self, symbol: str, relation_type: RelationType) -> list[Symbol]:
        source = self.get_symbol(symbol)
        if source is None:
            return []
        with self.driver.session() as session:
            records = session.run(
                f"MATCH (:Symbol {{id: $id}})-[:{relation_type.value}]->(s:Symbol) RETURN properties(s) AS s",
                id=source.id,
            )
            return [Symbol.model_validate(record["s"]) for record in records]
