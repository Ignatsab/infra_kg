#!/usr/bin/env python3
"""Ingest the APM topology manifest with Graflo.

This follows Graflo's examples/4-ingest-neo4j pattern:
load GraphManifest from YAML, build runtime Bindings for CSV files, attach
bindings to the manifest, then call GraphEngine.define_and_ingest.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "graflo_experiment"))

from make_bindings import make_bindings


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest APM topology CSVs with Graflo.")
    parser.add_argument("--manifest", default="graflo_experiment/manifest.apm_topology.yaml")
    parser.add_argument("--data-dir", default="data/mock")
    parser.add_argument("--clear", action="store_true", help="Clear target graph data before ingest.")
    parser.add_argument("--recreate-schema", action="store_true", help="Recreate target schema before ingest.")
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    try:
        from suthing import FileHandle
        from graflo import GraphManifest
        from graflo.db import Neo4jConfig
        from graflo.hq import GraphEngine
        from graflo.hq.caster import IngestionParams
    except ImportError as exc:
        raise SystemExit(
            "GraFlo is not installed in this environment yet. Install it with:\n"
            "  python3 -m pip install graflo"
        ) from exc

    manifest = GraphManifest.from_config(FileHandle.load(args.manifest))
    manifest.finish_init()
    bindings = make_bindings(args.data_dir)
    manifest = manifest.model_copy(update={"bindings": bindings})
    manifest.finish_init()

    conn_conf = Neo4jConfig()
    engine = GraphEngine(target_db_flavor=conn_conf.connection_type)
    ingestion_params = IngestionParams(
        clear_data=args.clear,
        batch_size=args.batch_size,
    )
    engine.define_and_ingest(
        manifest=manifest,
        target_db_config=conn_conf,
        ingestion_params=ingestion_params,
        recreate_schema=args.recreate_schema,
    )


if __name__ == "__main__":
    main()
