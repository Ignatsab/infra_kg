#!/usr/bin/env python3
"""Generate a GraFlo-style manifest draft for the APM topology CSVs."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any

from apm_mapping import EDGES, TABLE_ALIASES, VERTICES

TABLE_ORDER = [
    "apm_cluster",
    "apm_subclusters",
    "apm_applications",
    "apm_contacts",
    "apm_application_daps",
    "apm_obso",
    "apm_technologies",
]


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
    for table_name in ordered_source_tables():
        pipeline = table_resource_pipeline(table_name)
        if not pipeline:
            continue
        resources.append(
            {
                "name": table_name,
                "drop_trivial_input_fields": True,
                "fail_fast": False,
                "pipeline": pipeline,
            }
        )
    return resources


def table_resource_pipeline(table_name: str) -> list[dict[str, Any]]:
    pipeline: list[dict[str, Any]] = []
    seen_endpoint_steps: set[tuple[str, str, tuple[tuple[str, str], ...]]] = set()
    local_record_labels = set()

    for vertex in VERTICES:
        if vertex["source_table"] == table_name and vertex.get("source_columns") == "all":
            pipeline.append({"vertex": vertex["name"]})
            local_record_labels.add(vertex["name"])
            seen_endpoint_steps.add((vertex["name"], "", ()))

    for edge in [item for item in EDGES if item["source_table"] == table_name]:
        source_vertex = vertex_by_name(edge["source"])
        target_vertex = vertex_by_name(edge["target"])
        append_endpoint_step(
            pipeline,
            seen_endpoint_steps,
            table_name,
            source_vertex,
            edge["source_key"],
            local_record_labels,
        )
        append_endpoint_step(
            pipeline,
            seen_endpoint_steps,
            table_name,
            target_vertex,
            edge["target_key"],
            local_record_labels,
        )
        pipeline.append(
            {
                "source": edge["source"],
                "target": edge["target"],
                "relation": edge["name"],
            }
        )

    return pipeline


def append_endpoint_step(
    pipeline: list[dict[str, Any]],
    seen_endpoint_steps: set[tuple[str, str, tuple[tuple[str, str], ...]]],
    table_name: str,
    vertex: dict[str, Any],
    edge_key: dict[str, str],
    local_record_labels: set[str],
) -> None:
    column = edge_key["column"]
    if column == "id" and vertex["name"] in local_record_labels:
        return

    step = vertex_reference_step(vertex, column)
    signature = step_signature(step)
    if signature in seen_endpoint_steps:
        return

    pipeline.append(step)
    seen_endpoint_steps.add(signature)


def vertex_reference_step(vertex: dict[str, Any], column: str) -> dict[str, Any]:
    mapping = {"id": column}
    mapping.update(
        {
            field: source_column
            for field, source_column in (vertex.get("properties") or {}).items()
            if source_column != column
        }
    )
    step: dict[str, Any] = {
        "vertex": vertex["name"],
        "from": mapping,
    }
    return step


def step_signature(step: dict[str, Any]) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    properties = step.get("properties") or {}
    return (
        str(step["vertex"]),
        str(step.get("from") or ""),
        tuple(sorted((str(key), str(value)) for key, value in properties.items())),
    )


def vertex_by_name(name: str) -> dict[str, Any]:
    for vertex in VERTICES:
        if vertex["name"] == name:
            return vertex
    raise KeyError(f"Unknown vertex {name}")


def vertex_resource_name(vertex: dict[str, Any]) -> str:
    return vertex["source_table"]


def edge_resource_name(edge: dict[str, Any]) -> str:
    return edge["source_table"]


def source_tables() -> set[str]:
    return {item["source_table"] for item in VERTICES} | {item["source_table"] for item in EDGES}


def ordered_source_tables() -> list[str]:
    tables = source_tables()
    ordered = [table_name for table_name in TABLE_ORDER if table_name in tables]
    ordered.extend(sorted(tables - set(ordered)))
    return ordered


def resource_bindings_by_table() -> dict[str, list[str]]:
    bindings: dict[str, list[str]] = {}
    for table_name in ordered_source_tables():
        bindings[table_name] = [table_name]
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
    return str(key)


def is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def scalar_yaml(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if is_plain_yaml_scalar(text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def is_plain_yaml_scalar(value: str) -> bool:
    if not value:
        return False
    if value.strip() != value:
        return False
    if value in {"null", "true", "false", "{}", "[]"}:
        return False
    if value[0] in "-?:,[]{}#&*!|>'\"%@`":
        return False
    if "\n" in value or "\r" in value:
        return False
    if re.search(r"(^|[\s])#", value):
        return False
    return True


if __name__ == "__main__":
    main()
