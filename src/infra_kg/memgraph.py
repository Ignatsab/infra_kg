"""Load the generated topology graph into Memgraph over the Bolt protocol."""

from __future__ import annotations

import os
from pathlib import Path

from infra_kg.env import load_dotenv
from infra_kg.graph_builder import KnowledgeGraph, split_key


def load_graph_to_memgraph(
    graph: KnowledgeGraph,
    *,
    uri: str | None = None,
    username: str | None = None,
    password: str | None = None,
    clear: bool = False,
    env_path: Path | str = ".env",
) -> dict[str, int]:
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: install the Neo4j Bolt driver with "
            "`python3 -m pip install -r requirements.txt`"
        ) from exc

    load_dotenv(env_path)
    uri = uri or os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687")
    username = username if username is not None else os.environ.get("MEMGRAPH_USERNAME")
    password = password if password is not None else os.environ.get("MEMGRAPH_PASSWORD")
    auth = (username, password) if username and password else None

    driver = GraphDatabase.driver(uri, auth=auth)
    with driver:
        driver.verify_connectivity()
        with driver.session() as session:
            if clear:
                session.run("MATCH (n) DETACH DELETE n").consume()
            create_indexes(session, graph)
            for node in graph.nodes.values():
                session.run(
                    f"MERGE (n:{node.label} {{id: $id}}) SET n += $properties",
                    id=node.identity,
                    properties=node.properties,
                ).consume()
            for edge in graph.edges:
                start_label, start_id = split_key(edge.start_key)
                end_label, end_id = split_key(edge.end_key)
                session.run(
                    f"""
                    MATCH (a:{start_label} {{id: $start_id}})
                    MATCH (b:{end_label} {{id: $end_id}})
                    MERGE (a)-[r:{edge.type}]->(b)
                    SET r += $properties
                    """,
                    start_id=start_id,
                    end_id=end_id,
                    properties=edge.properties,
                ).consume()
    return {"nodes": len(graph.nodes), "edges": len(graph.edges)}


def create_indexes(session, graph: KnowledgeGraph) -> None:
    for label in sorted({node.label for node in graph.nodes.values()}):
        try:
            session.run(f"CREATE INDEX ON :{label}(id)").consume()
        except Exception:
            # Memgraph reports an error if an index already exists in some versions.
            pass
