#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from infra_kg.embeddings import embedding_provider_from_choice
from infra_kg.graph_builder import build_graph, write_graph_cypher, write_graph_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Build topology graph exports from APM CSV tables.")
    parser.add_argument("--data-dir", default="data/mock", help="Directory containing apm_*.csv tables.")
    parser.add_argument("--out-json", default="build/topology_graph.json", help="Output graph JSON path.")
    parser.add_argument("--out-cypher", default="build/topology_graph.cypher", help="Output Cypher path.")
    parser.add_argument("--no-derived", action="store_true", help="Only emit source-of-truth FK edges.")
    parser.add_argument("--no-retrieval-text", action="store_true", help="Do not add retrieval_text to graph nodes.")
    parser.add_argument(
        "--embed",
        choices=["none", "hash", "openai"],
        default="none",
        help="Add node embeddings. Use openai for an OpenAI-compatible embedding endpoint.",
    )
    parser.add_argument("--embedding-dimensions", type=int, default=64, help="Hash embedding dimensions.")
    parser.add_argument("--enrich-with-llm", action="store_true", help="Add optional LLM summaries/tags.")
    args = parser.parse_args()

    embedding_provider = embedding_provider_from_choice(args.embed, dimensions=args.embedding_dimensions)
    graph = build_graph(
        Path(args.data_dir),
        include_derived=not args.no_derived,
        include_retrieval_text=not args.no_retrieval_text,
        embedding_provider=embedding_provider,
        enrich_with_llm=args.enrich_with_llm,
    )
    write_graph_json(graph, args.out_json)
    write_graph_cypher(graph, args.out_cypher)

    print(f"Wrote graph JSON to {args.out_json}")
    print(f"Wrote graph Cypher to {args.out_cypher}")
    print(f"Nodes by label: {graph.label_counts()}")
    print(f"Edges by type: {graph.edge_counts()}")
    if args.embed != "none":
        print(f"Added {args.embed} embeddings to {len(graph.nodes)} nodes")
    if graph.warnings:
        print("Warnings:")
        for warning in graph.warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
