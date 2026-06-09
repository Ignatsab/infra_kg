#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from infra_kg.env import load_dotenv


def main() -> None:
    parser = argparse.ArgumentParser(description="Check loaded Memgraph topology counts.")
    parser.add_argument("--uri", default=None, help="Memgraph Bolt URI. Defaults to MEMGRAPH_URI or bolt://127.0.0.1:7687.")
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
    uri = args.uri or os.environ.get("MEMGRAPH_URI", "bolt://127.0.0.1:7687")
    username = args.username if args.username is not None else os.environ.get("MEMGRAPH_USERNAME")
    password = args.password if args.password is not None else os.environ.get("MEMGRAPH_PASSWORD")
    auth = (username, password) if username and password else None

    driver = GraphDatabase.driver(uri, auth=auth)
    with driver:
        driver.verify_connectivity()
        with driver.session() as session:
            print("Nodes by label")
            for record in session.run(
                """
                MATCH (n)
                RETURN labels(n) AS labels, count(*) AS count
                ORDER BY labels
                """
            ):
                print(f"- {record['labels']}: {record['count']}")

            print("\nEdges by type")
            for record in session.run(
                """
                MATCH ()-[r]->()
                RETURN type(r) AS relationship, count(*) AS count
                ORDER BY relationship
                """
            ):
                print(f"- {record['relationship']}: {record['count']}")

            total = session.run(
                """
                MATCH (n)
                WITH count(n) AS nodes
                MATCH ()-[r]->()
                RETURN nodes, count(r) AS edges
                """
            ).single()
            print(f"\nTotal: {total['nodes']} nodes / {total['edges']} edges")


if __name__ == "__main__":
    main()
