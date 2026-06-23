#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from infra_kg.embeddings import embedding_provider_from_choice
from infra_kg.graph_builder import build_graph
from infra_kg.memgraph import load_graph_to_memgraph


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the topology graph into local Memgraph.")
    parser.add_argument("--data-dir", default="data/mock", help="Directory containing apm_*.csv tables.")
    parser.add_argument("--uri", default=None, help="Memgraph Bolt URI. Defaults to MEMGRAPH_URI or bolt://127.0.0.1:7687.")
    parser.add_argument("--username", default=None, help="Memgraph username if auth is enabled.")
    parser.add_argument("--password", default=None, help="Memgraph password if auth is enabled.")
    parser.add_argument("--clear", action="store_true", help="Delete existing graph data before loading.")
    parser.add_argument("--no-derived", action="store_true", help="Only load source-of-truth FK edges.")
    parser.add_argument(
        "--max-related-group-size",
        type=int,
        default=200,
        help="Skip derived RELATED_TO all-to-all expansion for groups larger than this. Use 0 for no cap.",
    )
    parser.add_argument(
        "--no-related-to",
        action="store_true",
        help="Keep derived shortcuts but skip Application RELATED_TO edges.",
    )
    parser.add_argument("--no-retrieval-text", action="store_true", help="Do not add retrieval_text to graph nodes.")
    parser.add_argument(
        "--embed",
        choices=["none", "hash", "openai"],
        default="none",
        help="Add node embeddings. Use openai for an OpenAI-compatible embedding endpoint.",
    )
    parser.add_argument("--embedding-dimensions", type=int, default=64, help="Hash embedding dimensions.")
    parser.add_argument("--enrich-with-llm", action="store_true", help="Add optional LLM summaries/tags.")
    parser.add_argument("--env-path", default=".env", help="Path to .env file for LLM/embedding settings.")
    parser.add_argument("--connect-retries", type=int, default=120, help="Memgraph connection attempts before failing.")
    parser.add_argument("--connect-retry-delay", type=float, default=2.0, help="Seconds between Memgraph connection attempts.")
    parser.add_argument("--batch-size", type=int, default=1000, help="Rows per Memgraph write query.")
    args = parser.parse_args()

    embedding_provider = embedding_provider_from_choice(
        args.embed,
        dimensions=args.embedding_dimensions,
        env_path=args.env_path,
    )
    graph = build_graph(
        Path(args.data_dir),
        include_derived=not args.no_derived,
        include_related=not args.no_related_to,
        include_retrieval_text=not args.no_retrieval_text,
        embedding_provider=embedding_provider,
        enrich_with_llm=args.enrich_with_llm,
        env_path=args.env_path,
        max_related_group_size=args.max_related_group_size,
    )
    result = load_graph_to_memgraph(
        graph,
        uri=args.uri,
        username=args.username,
        password=args.password,
        clear=args.clear,
        connect_retries=args.connect_retries,
        connect_retry_delay=args.connect_retry_delay,
        batch_size=args.batch_size,
    )
    print(f"Loaded {result['nodes']} nodes and {result['edges']} edges into Memgraph")
    if result.get("vector_indexes"):
        print(f"Created {result['vector_indexes']} vector indexes")
    if graph.warnings:
        print("Warnings:")
        for warning in graph.warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
