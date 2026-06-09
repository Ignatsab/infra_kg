#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from infra_kg.embeddings import embedding_provider_from_choice
from infra_kg.env import load_dotenv


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic search over embedded Memgraph topology nodes.")
    parser.add_argument("query", help="Natural-language topology search query.")
    parser.add_argument(
        "--index",
        default="application_embedding_index",
        help="Memgraph vector index name, for example application_embedding_index.",
    )
    parser.add_argument("--limit", type=int, default=5, help="Number of nearest nodes to return.")
    parser.add_argument(
        "--embed",
        choices=["hash", "openai"],
        default="openai",
        help="Embedding provider used for the query. Must match the loaded node embeddings.",
    )
    parser.add_argument("--embedding-dimensions", type=int, default=64, help="Hash embedding dimensions.")
    parser.add_argument("--uri", default=None, help="Memgraph Bolt URI. Defaults to MEMGRAPH_URI or bolt://localhost:7687.")
    parser.add_argument("--username", default=None, help="Memgraph username if auth is enabled.")
    parser.add_argument("--password", default=None, help="Memgraph password if auth is enabled.")
    args = parser.parse_args()

    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: install the Neo4j Bolt driver with "
            "`python3 -m pip install -r requirements.txt`"
        ) from exc

    load_dotenv()
    provider = embedding_provider_from_choice(args.embed, dimensions=args.embedding_dimensions)
    if provider is None:
        raise RuntimeError("A query embedding provider is required")
    query_vector = provider.embed_texts([args.query])[0]

    uri = args.uri or os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687")
    username = args.username if args.username is not None else os.environ.get("MEMGRAPH_USERNAME")
    password = args.password if args.password is not None else os.environ.get("MEMGRAPH_PASSWORD")
    auth = (username, password) if username and password else None

    driver = GraphDatabase.driver(uri, auth=auth)
    with driver:
        driver.verify_connectivity()
        with driver.session() as session:
            records = session.run(
                """
                CALL vector_search.search($index_name, $limit, $query_vector)
                YIELD node, similarity
                RETURN labels(node) AS labels,
                       node.id AS id,
                       coalesce(node.name, node.id) AS name,
                       similarity AS similarity,
                       node.retrieval_text AS retrieval_text
                ORDER BY similarity DESC
                """,
                index_name=args.index,
                limit=args.limit,
                query_vector=query_vector,
            )
            for record in records:
                labels = ":".join(record["labels"])
                print(f"{record['similarity']:.4f} {labels} {record['id']} {record['name']}")
                retrieval_text = record.get("retrieval_text")
                if retrieval_text:
                    print(f"  {retrieval_text[:240]}")


if __name__ == "__main__":
    main()
