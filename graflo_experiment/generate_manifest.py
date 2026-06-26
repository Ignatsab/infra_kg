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
    print(f"Vertices: {len(manifest['schema']['graph']['vertex_config']['vertices'])}")
    print(f"Edges: {len(manifest['schema']['graph']['edge_config']['edges'])}")
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
    resources = resource_configs()
    return {
        "schema": {
            "metadata": {
                "name": "apm_topology",
                "version": "0.1.0",
                "description": "Experimental GraFlo manifest for APM infrastructure topology.",
            },
            "db_profile": {},
            "graph": {
                "vertex_config": {
                    "vertices": vertices,
                },
                "edge_config": {
                    "edges": edges,
                },
            },
        },
        "ingestion_model": {
            "resources": resources,
        },
    }


def vertex_schema(vertex: dict[str, Any], table_headers: dict[str, list[str]]) -> dict[str, Any]:
    fields = vertex_fields(vertex, table_headers)
    return {
        "name": vertex["name"],
        "properties": fields,
        "identity": list(vertex["identity"]),
    }


def vertex_fields(vertex: dict[str, Any], table_headers: dict[str, list[str]]) -> list[str]:
    fields: list[str] = []
    for field in vertex["identity"]:
        append_unique(fields, field)
    if vertex.get("source_columns") == "all":
        for field in table_headers.get(vertex["source_table"], []):
            append_unique(fields, field)
    for field in (vertex.get("properties") or {}):
        append_unique(fields, field)
    return fields


def edge_schema(edge: dict[str, Any]) -> dict[str, Any]:
    config = {
        "source": edge["source"],
        "target": edge["target"],
        "relation": edge["name"],
    }
    return config


def resource_configs() -> list[dict[str, Any]]:
    resources = []
    for vertex in VERTICES:
        resources.append(vertex_resource_config(vertex))
    for edge in EDGES:
        resources.append(edge_resource_config(edge))
    return resources


def vertex_resource_config(vertex: dict[str, Any]) -> dict[str, Any]:
    pipeline_step: dict[str, Any] = {"vertex": vertex["name"]}
    if vertex.get("source_columns") != "all":
        mapping = vertex_from_mapping(vertex)
        pipeline_step["from"] = mapping
    return {
        "name": vertex_resource_name(vertex),
        "drop_trivial_input_fields": True,
        "fail_fast": False,
        "pipeline": [pipeline_step],
    }


def edge_resource_config(edge: dict[str, Any]) -> dict[str, Any]:
    source_vertex = vertex_by_name(edge["source"])
    target_vertex = vertex_by_name(edge["target"])
    return {
        "name": edge_resource_name(edge),
        "drop_trivial_input_fields": True,
        "fail_fast": False,
        "pipeline": [
            {
                "vertex": edge["source"],
                "from": vertex_from_edge_key(source_vertex, edge["source_key"]),
            },
            {
                "vertex": edge["target"],
                "from": vertex_from_edge_key(target_vertex, edge["target_key"]),
            },
            {
                "source": edge["source"],
                "target": edge["target"],
                "relation": edge["name"],
            },
        ],
    }


def vertex_from_mapping(vertex: dict[str, Any]) -> dict[str, str]:
    mapping = {field: column for field, column in vertex["identity"].items()}
    mapping.update(vertex.get("properties") or {})
    return mapping


def vertex_from_edge_key(vertex: dict[str, Any], edge_key: dict[str, str]) -> dict[str, str]:
    mapping = {edge_key["vertex_field"]: edge_key["column"]}
    mapping.update(vertex.get("edge_properties") or {})
    return mapping


def vertex_by_name(name: str) -> dict[str, Any]:
    for vertex in VERTICES:
        if vertex["name"] == name:
            return vertex
    raise KeyError(f"Unknown vertex {name}")


def vertex_resource_name(vertex: dict[str, Any]) -> str:
    return f"{vertex['source_table']}__vertex__{vertex['name']}"


def edge_resource_name(edge: dict[str, Any]) -> str:
    return f"{edge['source_table']}__edge__{edge['name']}"


def source_tables() -> set[str]:
    return {item["source_table"] for item in VERTICES} | {item["source_table"] for item in EDGES}


def resource_bindings_by_table() -> dict[str, list[str]]:
    bindings: dict[str, list[str]] = {table_name: [] for table_name in sorted(source_tables())}
    for vertex in VERTICES:
        bindings[vertex["source_table"]].append(vertex_resource_name(vertex))
    for edge in EDGES:
        bindings[edge["source_table"]].append(edge_resource_name(edge))
    return bindings


def append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def dump_yaml(value: Any, indent: int = 0) -> str:
    lines = render_yaml(value, indent)
    return "\n".join(lines) + "\n"


def render_yaml(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        if not value:
            return [f"{prefix}{{}}"]
        lines: list[str] = []
        for key, item in value.items():
            key_text = yaml_key(key)
            if item == {}:
                lines.append(f"{prefix}{key_text}: {{}}")
                continue
            if item == []:
                lines.append(f"{prefix}{key_text}: []")
                continue
            if is_scalar(item):
                lines.append(f"{prefix}{key_text}: {scalar_yaml(item)}")
            else:
                lines.append(f"{prefix}{key_text}:")
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


def yaml_key(key: object) -> str:
    key_text = str(key)
    if key_text == "from":
        return '"from"'
    return key_text


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
