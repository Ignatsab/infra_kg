#!/usr/bin/env python3
"""Generate a GraFlo-style manifest draft for the APM topology CSVs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from apm_mapping import EDGES, TABLE_ALIASES, VERTICES


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an experimental GraFlo manifest for APM topology data.")
    parser.add_argument("--data-dir", default="data/mock", help="Directory containing apm_*.csv files.")
    parser.add_argument("--output", default="graflo_experiment/manifest.apm_topology.yaml", help="Output manifest path.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    table_headers = read_table_headers(data_dir)
    manifest = build_manifest(table_headers)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(dump_yaml(manifest), encoding="utf-8")

    print(f"Wrote GraFlo manifest draft to {output}")
    print(f"Vertices: {len(manifest['schema']['core_schema']['vertices'])}")
    print(f"Edges: {len(manifest['schema']['core_schema']['edges'])}")
    print(f"Resources: {len(manifest['ingestion_model']['resources'])}")


def read_table_headers(data_dir: Path) -> dict[str, list[str]]:
    headers: dict[str, list[str]] = {}
    for path in sorted(data_dir.glob("*.csv")):
        table_name = path.stem
        canonical_name = canonical_table_name(table_name)
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            headers[canonical_name] = next(reader, [])
    return headers


def canonical_table_name(table_name: str) -> str:
    for canonical_name, aliases in TABLE_ALIASES.items():
        if table_name in aliases:
            return canonical_name
    return table_name


def build_manifest(table_headers: dict[str, list[str]]) -> dict[str, Any]:
    vertices = [vertex_schema(vertex, table_headers) for vertex in VERTICES]
    edges = [edge_schema(edge) for edge in EDGES]
    resources = [resource_config(table_name) for table_name in sorted(resources_by_table())]
    return {
        "schema": {
            "metadata": {
                "name": "apm_topology",
                "description": "Experimental GraFlo manifest for APM infrastructure topology.",
            },
            "db_profile": {
                "type": "MEMGRAPH",
            },
            "core_schema": {
                "vertices": vertices,
                "edges": edges,
            },
        },
        "ingestion_model": {
            "resources": resources,
        },
    }


def vertex_schema(vertex: dict[str, Any], table_headers: dict[str, list[str]]) -> dict[str, Any]:
    fields = vertex_fields(vertex, table_headers)
    config = {
        "name": vertex["name"],
        "fields": fields,
        "indexes": [
            {
                "fields": list(vertex["identity"]),
            }
        ],
    }
    config["identity"] = vertex["identity"]
    config["source_table"] = vertex["source_table"]
    return config


def vertex_fields(vertex: dict[str, Any], table_headers: dict[str, list[str]]) -> list[str]:
    fields: list[str] = []
    for field in vertex["identity"]:
        append_unique(fields, field)
    if vertex.get("source_columns") == "all":
        for field in table_headers.get(vertex["source_table"], []):
            append_unique(fields, field)
    for field in (vertex.get("properties") or {}):
        append_unique(fields, field)
    append_unique(fields, "source_table")
    return fields


def edge_schema(edge: dict[str, Any]) -> dict[str, Any]:
    config = {
        "name": edge["name"],
        "source": edge["source"],
        "target": edge["target"],
        "source_table": edge["source_table"],
        "source_key": edge["source_key"],
        "target_key": edge["target_key"],
    }
    if edge.get("source_columns") == "all":
        config["properties"] = {"source_columns": "all"}
    return config


def resource_config(table_name: str) -> dict[str, Any]:
    applies = []
    for vertex in VERTICES:
        if vertex["source_table"] == table_name:
            applies.append(
                {
                    "vertex": vertex["name"],
                    "from": vertex_from_mapping(vertex),
                }
            )
    for edge in EDGES:
        if edge["source_table"] == table_name:
            applies.append(
                {
                    "edge": edge["name"],
                    "source": edge["source"],
                    "target": edge["target"],
                    "source_key": edge["source_key"],
                    "target_key": edge["target_key"],
                }
            )
    return {
        "name": table_name,
        "apply": applies,
    }


def vertex_from_mapping(vertex: dict[str, Any]) -> dict[str, str]:
    mapping = {field: column for field, column in vertex["identity"].items()}
    mapping.update(vertex.get("properties") or {})
    return mapping


def resources_by_table() -> set[str]:
    return {item["source_table"] for item in VERTICES} | {item["source_table"] for item in EDGES}


def append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def dump_yaml(value: Any, indent: int = 0) -> str:
    lines = render_yaml(value, indent)
    return "\n".join(lines) + "\n"


def render_yaml(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if is_scalar(item):
                lines.append(f"{prefix}{key}: {scalar_yaml(item)}")
            else:
                lines.append(f"{prefix}{key}:")
                lines.extend(render_yaml(item, indent + 2))
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{prefix}[]"]
        lines = []
        for item in value:
            if is_scalar(item):
                lines.append(f"{prefix}- {scalar_yaml(item)}")
            else:
                rendered = render_yaml(item, indent + 2)
                lines.append(f"{prefix}- {rendered[0].lstrip()}")
                lines.extend(rendered[1:])
        return lines
    return [f"{prefix}{scalar_yaml(value)}"]


def is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def scalar_yaml(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value))


if __name__ == "__main__":
    main()
