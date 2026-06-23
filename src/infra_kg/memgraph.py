"""Load the generated topology graph into Memgraph over the Bolt protocol."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Iterable, TypeVar

from infra_kg.env import load_dotenv
from infra_kg.graph_builder import GraphEdge, GraphNode, KnowledgeGraph, split_key, vector_dimensions_by_label

T = TypeVar("T")


def load_graph_to_memgraph(
    graph: KnowledgeGraph,
    *,
    uri: str | None = None,
    username: str | None = None,
    password: str | None = None,
    clear: bool = False,
    env_path: Path | str = ".env",
    connect_retries: int | None = None,
    connect_retry_delay: float | None = None,
    batch_size: int = 1000,
) -> dict[str, int]:
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: install the Neo4j Bolt driver with "
            "`python3 -m pip install -r requirements.txt`"
        ) from exc

    load_dotenv(env_path)
    uri = uri or os.environ.get("MEMGRAPH_URI", "bolt://127.0.0.1:7687")
    username = username if username is not None else os.environ.get("MEMGRAPH_USERNAME")
    password = password if password is not None else os.environ.get("MEMGRAPH_PASSWORD")
    connect_retries = connect_retries if connect_retries is not None else int(os.environ.get("MEMGRAPH_CONNECT_RETRIES", "120"))
    connect_retry_delay = (
        connect_retry_delay
        if connect_retry_delay is not None
        else float(os.environ.get("MEMGRAPH_CONNECT_RETRY_DELAY", "2"))
    )
    batch_size = max(1, int(os.environ.get("MEMGRAPH_BATCH_SIZE", str(batch_size))))
    auth = (username, password) if username and password else None

    driver = GraphDatabase.driver(uri, auth=auth)
    with driver:
        verify_connectivity_with_retry(driver, uri, connect_retries, connect_retry_delay)
        with driver.session() as session:
            if clear:
                print("Clearing existing Memgraph graph...")
                session.run("MATCH (n) DETACH DELETE n").consume()
            create_indexes(session, graph)
            load_nodes(session, graph.nodes.values(), batch_size)
            vector_indexes = create_vector_indexes(session, graph)
            load_edges(session, graph.edges, batch_size)
    return {"nodes": len(graph.nodes), "edges": len(graph.edges), "vector_indexes": vector_indexes}


def load_nodes(session, nodes: Iterable[GraphNode], batch_size: int) -> None:
    nodes_by_label: dict[str, list[GraphNode]] = {}
    total = 0
    for node in nodes:
        nodes_by_label.setdefault(node.label, []).append(node)
        total += 1

    loaded = 0
    print(f"Loading {total} nodes in batches of {batch_size}...")
    for label, label_nodes in sorted(nodes_by_label.items()):
        for batch in chunks(label_nodes, batch_size):
            rows = [{"id": node.identity, "properties": node.properties} for node in batch]
            session.run(
                f"""
                UNWIND $rows AS row
                MERGE (n:{label} {{id: row.id}})
                SET n += row.properties
                """,
                rows=rows,
            ).consume()
            loaded += len(batch)
            print_progress("nodes", loaded, total)


def load_edges(session, edges: Iterable[GraphEdge], batch_size: int) -> None:
    edges_by_shape: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    total = 0
    for edge in edges:
        start_label, start_id = split_key(edge.start_key)
        end_label, end_id = split_key(edge.end_key)
        shape = (start_label, edge.type, end_label)
        edges_by_shape.setdefault(shape, []).append(
            {
                "start_id": start_id,
                "end_id": end_id,
                "properties": edge.properties,
            }
        )
        total += 1

    loaded = 0
    print(f"Loading {total} edges in batches of {batch_size}...")
    for (start_label, edge_type, end_label), shape_edges in sorted(edges_by_shape.items()):
        for batch in chunks(shape_edges, batch_size):
            session.run(
                f"""
                UNWIND $rows AS row
                MATCH (a:{start_label} {{id: row.start_id}})
                MATCH (b:{end_label} {{id: row.end_id}})
                MERGE (a)-[r:{edge_type}]->(b)
                SET r += row.properties
                """,
                rows=batch,
            ).consume()
            loaded += len(batch)
            print_progress("edges", loaded, total)


def chunks(items: list[T], size: int) -> Iterable[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def print_progress(label: str, loaded: int, total: int) -> None:
    if not total:
        return
    if loaded == total or loaded % 10000 == 0:
        percent = (loaded / total) * 100
        print(f"Loaded {loaded}/{total} {label} ({percent:.1f}%)")


def verify_connectivity_with_retry(driver, uri: str, retries: int, retry_delay: float) -> None:
    attempts = max(1, retries)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            driver.verify_connectivity()
            if attempt > 1:
                print(f"Connected to Memgraph at {uri} after {attempt} attempts")
            return
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            print(
                f"Waiting for Memgraph at {uri} "
                f"({attempt}/{attempts}): {exc.__class__.__name__}"
            )
            time.sleep(retry_delay)

    raise RuntimeError(
        f"Could not connect to Memgraph at {uri} after {attempts} attempts. "
        "If you started Docker Compose moments ago, check `docker compose ps` "
        "and `docker compose logs memgraph`. If your machine resolves localhost "
        "to IPv6 first, use `--uri bolt://127.0.0.1:7687`. If the error says "
        "`incomplete handshake response`, reinstall dependencies with "
        "`python3 -m pip install -r requirements.txt` so the Neo4j driver is "
        "pinned to the compatible major version."
    ) from last_error


def create_indexes(session, graph: KnowledgeGraph) -> None:
    for label in sorted({node.label for node in graph.nodes.values()}):
        try:
            session.run(f"CREATE INDEX ON :{label}(id)").consume()
        except Exception:
            # Memgraph reports an error if an index already exists in some versions.
            pass


def create_vector_indexes(session, graph: KnowledgeGraph) -> int:
    created = 0
    for label, dimension in vector_dimensions_by_label(graph).items():
        count = sum(1 for node in graph.nodes.values() if node.label == label and "embedding" in node.properties)
        capacity = max(100, count * 2)
        index_name = f"{label.lower()}_embedding_index"
        try:
            session.run(
                f"""
                CREATE VECTOR INDEX {index_name} ON :{label}(embedding)
                WITH CONFIG {{'dimension': {dimension}, 'capacity': {capacity}, 'metric': 'cos'}}
                """
            ).consume()
            created += 1
        except Exception:
            # Older Memgraph versions may not support vector indexes, and existing
            # indexes can also raise. The embeddings are still stored on nodes.
            pass
    return created
