#!/usr/bin/env python3
"""Validate the experimental GraFlo manifest if Graflo is installed."""

from __future__ import annotations

import argparse
from pathlib import Path

from make_bindings import make_bindings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the experimental GraFlo manifest.")
    parser.add_argument("--manifest", default="graflo_experiment/manifest.apm_topology.yaml")
    parser.add_argument("--data-dir", default=None, help="Optionally also instantiate runtime FileConnector bindings.")
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
    assert_no_runtime_bindings_in_manifest(manifest_path)
    manifest = GraphManifest.from_config(FileHandle.load(manifest_path))
    manifest.finish_init()
    schema = manifest.require_schema()
    ingestion_model = manifest.require_ingestion_model()

    core_schema = getattr(schema, "core_schema", None) or getattr(schema, "graph", None)
    vertex_config = getattr(core_schema, "vertex_config", None)
    edge_config = getattr(core_schema, "edge_config", None)
    vertices = getattr(vertex_config, "vertices", getattr(core_schema, "vertices", []))
    edges = getattr(edge_config, "edges", getattr(core_schema, "edges", []))
    resources = getattr(ingestion_model, "resources", [])
    print(f"Manifest is valid: {manifest_path}")
    print(f"Vertices: {len(vertices)}")
    print(f"Edges: {len(edges)}")
    print(f"Resources: {len(resources)}")
    if args.data_dir:
        bindings = make_bindings(args.data_dir)
        print(f"Bindings are valid for data dir: {args.data_dir}")
        print(f"Connectors: {len(bindings.connectors)}")


def assert_no_runtime_bindings_in_manifest(manifest_path: Path) -> None:
    text = manifest_path.read_text(encoding="utf-8")
    forbidden_markers = [
        "\nbindings:",
        "\n  sub_path:",
        "\n    sub_path:",
        "\n    core_schema:",
        "\n      apply:",
        "\n        source_key:",
        "\n        target_key:",
    ]
    if any(marker in text for marker in forbidden_markers):
        raise SystemExit(
            f"{manifest_path} still contains runtime connector bindings such as "
            "`bindings` or `sub_path`. Regenerate it with:\n"
            "  python3 graflo_experiment/generate_manifest.py "
            "--data-dir data/real/APM_DATA "
            "--output graflo_experiment/manifest.apm_topology.yaml\n"
            "Then verify with:\n"
            "  grep -n \"sub_path\\|bindings:\" graflo_experiment/manifest.apm_topology.yaml"
        )


if __name__ == "__main__":
    main()
