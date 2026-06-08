#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from infra_kg.graph_builder import build_graph
from infra_kg.memgraph import load_graph_to_memgraph


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the topology graph into local Memgraph.")
    parser.add_argument("--data-dir", default="data/mock", help="Directory containing apm_*.csv tables.")
    parser.add_argument("--uri", default=None, help="Memgraph Bolt URI. Defaults to MEMGRAPH_URI or bolt://localhost:7687.")
    parser.add_argument("--username", default=None, help="Memgraph username if auth is enabled.")
    parser.add_argument("--password", default=None, help="Memgraph password if auth is enabled.")
    parser.add_argument("--clear", action="store_true", help="Delete existing graph data before loading.")
    parser.add_argument("--no-derived", action="store_true", help="Only load source-of-truth FK edges.")
    parser.add_argument("--enrich-with-llm", action="store_true", help="Add optional LLM summaries/tags.")
    args = parser.parse_args()

    graph = build_graph(
        Path(args.data_dir),
        include_derived=not args.no_derived,
        enrich_with_llm=args.enrich_with_llm,
    )
    result = load_graph_to_memgraph(
        graph,
        uri=args.uri,
        username=args.username,
        password=args.password,
        clear=args.clear,
    )
    print(f"Loaded {result['nodes']} nodes and {result['edges']} edges into Memgraph")
    if graph.warnings:
        print("Warnings:")
        for warning in graph.warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
