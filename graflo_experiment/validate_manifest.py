#!/usr/bin/env python3
"""Validate the experimental GraFlo manifest if Graflo is installed."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the experimental GraFlo manifest.")
    parser.add_argument("--manifest", default="graflo_experiment/manifest.apm_topology.yaml")
    args = parser.parse_args()

    try:
        from suthing import FileHandle
        from graflo import GraphManifest
    except ImportError as exc:
        raise SystemExit(
            "GraFlo is not installed in this environment yet. Install it with:\n"
            "  python3 -m pip install graflo\n"
            "Then rerun this command."
        ) from exc

    manifest_path = Path(args.manifest)
    manifest = GraphManifest.from_config(FileHandle.load(manifest_path))
    manifest.finish_init()
    schema = manifest.require_schema()
    ingestion_model = manifest.require_ingestion_model()

    core_schema = getattr(schema, "core_schema", None)
    vertices = getattr(core_schema, "vertices", [])
    edges = getattr(core_schema, "edges", [])
    resources = getattr(ingestion_model, "resources", [])
    print(f"Manifest is valid: {manifest_path}")
    print(f"Vertices: {len(vertices)}")
    print(f"Edges: {len(edges)}")
    print(f"Resources: {len(resources)}")


if __name__ == "__main__":
    main()
