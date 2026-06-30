#!/usr/bin/env python3
"""Export a renderable graph from the Graflo APM manifest experiment.

This is a local preview path for the manifest generated in this folder. It
executes the simple vertex/edge resource pipelines we generate and writes the
same JSON shape used by the existing HTML topology viewer. It does not require
Docker, Memgraph, or the Graflo package.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "graflo_experiment"))

from infra_kg.graph_builder import (  # noqa: E402
    KnowledgeGraph,
    add_retrieval_text,
    clean_properties,
    row_properties,
    write_graph_cypher,
    write_graph_json,
)
from infra_kg.memgraph import load_graph_to_memgraph  # noqa: E402
from render_graph_viewer import (  # noqa: E402
    focus_application_graph,
    render_html,
    sample_graph,
    with_metadata,
)

from apm_mapping import TABLE_ALIASES  # noqa: E402
from generate_manifest import build_manifest, read_table_headers, source_tables  # noqa: E402

VALUE_NODE_LABELS = {"Host", "Criticality", "Environment", "LocationCountry"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a local viewer graph from the Graflo APM manifest experiment."
    )
    parser.add_argument("--data-dir", default="data/mock", help="Directory containing apm_*.csv files.")
    parser.add_argument(
        "--manifest",
        default="graflo_experiment/manifest.apm_topology.yaml",
        help="Graflo manifest path. Used directly if PyYAML is installed; otherwise rebuilt from apm_mapping.py.",
    )
    parser.add_argument("--output", default="build/graflo_topology_graph.json", help="Output graph JSON path.")
    parser.add_argument("--out-cypher", default="build/graflo_topology_graph.cypher", help="Output Cypher path.")
    parser.add_argument(
        "--viewer-output",
        default="build/graflo_topology_viewer.html",
        help="Output HTML viewer path.",
    )
    parser.add_argument("--no-viewer", action="store_true", help="Only write JSON; skip HTML viewer rendering.")
    parser.add_argument("--no-retrieval-text", action="store_true", help="Do not add retrieval_text to graph nodes.")
    parser.add_argument("--max-nodes", type=int, default=120, help="Maximum nodes in sampled viewer mode.")
    parser.add_argument("--max-edges", type=int, default=180, help="Maximum edges in sampled viewer mode.")
    parser.add_argument("--full", action="store_true", help="Render the full graph in the viewer.")
    parser.add_argument("--application-name", "--app-name", default=None, help="Focus viewer on an application name.")
    parser.add_argument("--application-id", "--app-id", default=None, help="Focus viewer on an application id.")
    parser.add_argument("--focus-depth", type=int, default=2, help="Relationship hops around the focused application.")
    parser.add_argument(
        "--load-memgraph",
        action="store_true",
        help="Load the manifest-built graph into Memgraph over Bolt after exporting files.",
    )
    parser.add_argument("--uri", default=None, help="Memgraph Bolt URI, for example bolt://127.0.0.1:7687.")
    parser.add_argument("--username", default=None, help="Memgraph username if auth is enabled.")
    parser.add_argument("--password", default=None, help="Memgraph password if auth is enabled.")
    parser.add_argument("--clear", action="store_true", help="Delete existing Memgraph graph data before loading.")
    parser.add_argument("--env-path", default=".env", help="Path to .env file for Memgraph environment settings.")
    parser.add_argument("--connect-retries", type=int, default=120, help="Memgraph connection attempts before failing.")
    parser.add_argument(
        "--connect-retry-delay",
        type=float,
        default=2.0,
        help="Seconds between Memgraph connection attempts.",
    )
    parser.add_argument("--batch-size", type=int, default=1000, help="Rows per Memgraph write query.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    manifest, manifest_source = load_manifest_or_rebuild(Path(args.manifest), data_dir)
    graph = build_graph_from_manifest(manifest, data_dir)
    if not args.no_retrieval_text:
        add_retrieval_text(graph)

    write_graph_json(graph, args.output)
    write_graph_cypher(graph, args.out_cypher)
    print(f"Wrote Graflo manifest graph JSON to {args.output}")
    print(f"Wrote Graflo manifest Cypher to {args.out_cypher}")
    print(f"Manifest source: {manifest_source}")
    print(f"Nodes by label: {graph.label_counts()}")
    print(f"Edges by type: {graph.edge_counts()}")

    if not args.no_viewer:
        graph_dict = graph.to_dict()
        viewer_graph = viewer_subset(
            graph_dict,
            full=args.full,
            max_nodes=args.max_nodes,
            max_edges=args.max_edges,
            application_name=args.application_name,
            application_id=args.application_id,
            focus_depth=args.focus_depth,
        )
        viewer_output = Path(args.viewer_output)
        viewer_output.parent.mkdir(parents=True, exist_ok=True)
        viewer_output.write_text(render_html(viewer_graph), encoding="utf-8")
        print(f"Wrote Graflo manifest viewer to {viewer_output}")

    if args.load_memgraph:
        result = load_graph_to_memgraph(
            graph,
            uri=args.uri,
            username=args.username,
            password=args.password,
            clear=args.clear,
            env_path=args.env_path,
            connect_retries=args.connect_retries,
            connect_retry_delay=args.connect_retry_delay,
            batch_size=args.batch_size,
        )
        print(f"Loaded {result['nodes']} nodes and {result['edges']} edges into Memgraph")

    if graph.warnings:
        print("Warnings:")
        for warning in graph.warnings:
            print(f"- {warning}")


def load_manifest_or_rebuild(manifest_path: Path, data_dir: Path) -> tuple[dict[str, Any], str]:
    if manifest_path.exists():
        text = manifest_path.read_text(encoding="utf-8")
        try:
            import yaml  # type: ignore[import-not-found]

            loaded = yaml.safe_load(text)
            if not isinstance(loaded, dict):
                raise ValueError(f"{manifest_path} did not contain a YAML object")
            return loaded, str(manifest_path)
        except ModuleNotFoundError:
            try:
                return parse_generated_yaml(text), f"{manifest_path} parsed with local YAML subset"
            except ValueError:
                manifest = build_manifest(read_table_headers(data_dir))
                return manifest, "rebuilt from apm_mapping.py because PyYAML is not installed"

    manifest = build_manifest(read_table_headers(data_dir))
    return manifest, "rebuilt from apm_mapping.py because the manifest file was not found"


def parse_generated_yaml(text: str) -> dict[str, Any]:
    tokens = normalize_yaml_tokens(text)
    if not tokens:
        return {}
    value, index = parse_yaml_block(tokens, 0, tokens[0][0])
    if index != len(tokens):
        raise ValueError("Unexpected trailing YAML content")
    if not isinstance(value, dict):
        raise ValueError("Generated manifest YAML must parse to an object")
    return value


def normalize_yaml_tokens(text: str) -> list[tuple[int, str]]:
    tokens: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        content = raw_line.strip()
        if content.startswith("- "):
            item = content[2:].strip()
            if split_yaml_key_value(item) is not None:
                tokens.append((indent, "-"))
                tokens.append((indent + 2, item))
            else:
                tokens.append((indent, content))
        else:
            tokens.append((indent, content))
    return tokens


def parse_yaml_block(tokens: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(tokens):
        return {}, index
    content = tokens[index][1]
    if content == "-" or content.startswith("- "):
        return parse_yaml_list(tokens, index, indent)
    return parse_yaml_dict(tokens, index, indent)


def parse_yaml_dict(
    tokens: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(tokens):
        line_indent, content = tokens[index]
        if line_indent < indent:
            break
        if line_indent != indent or content == "-" or content.startswith("- "):
            break

        split = split_yaml_key_value(content)
        if split is None:
            raise ValueError(f"Expected YAML key/value at line content {content!r}")
        key, raw_value = split
        index += 1
        if raw_value:
            result[key] = parse_yaml_scalar(raw_value)
        elif index < len(tokens) and tokens[index][0] > indent:
            result[key], index = parse_yaml_block(tokens, index, tokens[index][0])
        else:
            result[key] = {}
    return result, index


def parse_yaml_list(tokens: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(tokens):
        line_indent, content = tokens[index]
        if line_indent < indent:
            break
        if line_indent != indent or not (content == "-" or content.startswith("- ")):
            break

        if content == "-":
            index += 1
            if index < len(tokens) and tokens[index][0] > indent:
                item, index = parse_yaml_block(tokens, index, tokens[index][0])
            else:
                item = None
            result.append(item)
        else:
            result.append(parse_yaml_scalar(content[2:].strip()))
            index += 1
    return result, index


def split_yaml_key_value(content: str) -> tuple[str, str] | None:
    key, separator, value = content.partition(":")
    if not separator:
        return None
    key = key.strip()
    if not key:
        return None
    if key.startswith('"') and key.endswith('"'):
        key = json.loads(key)
    return key, value.strip()


def parse_yaml_scalar(value: str) -> Any:
    if value == "{}":
        return {}
    if value == "[]":
        return []
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith('"') and value.endswith('"'):
        return json.loads(value)
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def build_graph_from_manifest(manifest: dict[str, Any], data_dir: Path | str) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    vertex_schemas = vertex_schemas_by_name(manifest)
    row_cache: dict[str, list[dict[str, str]]] = {}
    skipped = Counter()

    resources = manifest.get("ingestion_model", {}).get("resources", [])
    if not isinstance(resources, list):
        graph.warnings.append("Manifest ingestion_model.resources is missing or is not a list")
        return graph

    for resource in resources:
        if not isinstance(resource, dict):
            skipped["non-object resources"] += 1
            continue

        resource_name = str(resource.get("name", ""))
        source_table = source_table_from_resource_name(resource_name)
        if not source_table:
            skipped[f"{resource_name or '<unnamed resource>'}: missing source table in resource name"] += 1
            continue

        rows = row_cache.setdefault(source_table, read_table_rows(data_dir, source_table, graph))
        pipeline = resource.get("pipeline", [])
        if not isinstance(pipeline, list):
            skipped[f"{resource_name}: pipeline is not a list"] += 1
            continue

        for row_number, row in enumerate(rows, start=2):
            context: dict[str, str] = {}
            for step in pipeline:
                if not isinstance(step, dict):
                    skipped[f"{resource_name}: non-object pipeline step"] += 1
                    continue

                if "vertex" in step:
                    label = str(step["vertex"])
                    node_key = add_manifest_vertex(
                        graph,
                        vertex_schemas,
                        label,
                        step.get("from"),
                        step.get("properties"),
                        row,
                        source_table,
                    )
                    if node_key:
                        context[label] = node_key
                    else:
                        skipped[f"{resource_name}: blank {label} identity"] += 1
                    continue

                if "source" in step and "target" in step:
                    edge_type = str(step.get("relation") or f"{step['source']}_TO_{step['target']}")
                    start_key = context.get(str(step["source"]))
                    end_key = context.get(str(step["target"]))
                    if not start_key or not end_key:
                        skipped[f"{resource_name}: skipped {edge_type} edge with blank endpoint"] += 1
                        continue
                    graph.add_edge(
                        start_key,
                        edge_type,
                        end_key,
                        edge_properties(resource_name, source_table, edge_type, row),
                    )
                    continue

                skipped[f"{resource_name}: unsupported pipeline step near CSV row {row_number}"] += 1

    add_skip_warnings(graph, skipped)
    return graph


def vertex_schemas_by_name(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    vertices = (
        manifest.get("schema", {})
        .get("graph", {})
        .get("vertex_config", {})
        .get("vertices", [])
    )
    result = {}
    if isinstance(vertices, list):
        for vertex in vertices:
            if isinstance(vertex, dict) and vertex.get("name"):
                result[str(vertex["name"])] = vertex
    return result


def add_manifest_vertex(
    graph: KnowledgeGraph,
    vertex_schemas: dict[str, dict[str, Any]],
    label: str,
    field_mapping: object,
    property_mapping: object,
    row: dict[str, str],
    source_table: str,
) -> str | None:
    schema = vertex_schemas.get(label, {})
    identity_fields = schema.get("identity") or ["id"]
    if not isinstance(identity_fields, list):
        identity_fields = [identity_fields]

    mapping = field_mapping if isinstance(field_mapping, dict) else None
    from_column = field_mapping if isinstance(field_mapping, str) else None
    identity_values = [mapped_row_value(row, mapping, str(field)) for field in identity_fields]
    if from_column:
        identity_values = [(row.get(from_column) or "").strip()]
    if any(value == "" for value in identity_values):
        return None

    identity = "|".join(identity_values)
    if from_column:
        properties = {"source_table": source_table}
        if label in VALUE_NODE_LABELS:
            properties["name"] = identity
    elif mapping is None:
        properties = row_properties(row, source_table)
    else:
        properties = {"source_table": source_table}
        for property_name, column_name in mapping.items():
            properties[str(property_name)] = row.get(str(column_name), "")

    if isinstance(property_mapping, dict):
        for property_name, column_name in property_mapping.items():
            properties[str(property_name)] = row.get(str(column_name), "")

    return graph.add_node(label, identity, properties)


def mapped_row_value(row: dict[str, str], mapping: dict[Any, Any] | None, field: str) -> str:
    column = str(mapping.get(field, field)) if mapping else field
    return (row.get(column) or "").strip()


def edge_properties(resource_name: str, source_table: str, edge_type: str, row: dict[str, str]) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "source_table": source_table,
        "graflo_resource": resource_name,
    }
    if edge_type == "EXPOSES_DAP":
        properties.update(row_properties(row, source_table))
        properties["binding_id"] = row.get("id", "")
    return clean_properties(properties)


def source_table_from_resource_name(resource_name: str) -> str:
    canonical_name = canonical_table_name(resource_name)
    if canonical_name in source_tables():
        return canonical_name
    if "__" not in resource_name:
        return ""
    return canonical_table_name(resource_name.split("__", 1)[0])


def canonical_table_name(table_name: str) -> str:
    for canonical_name, aliases in TABLE_ALIASES.items():
        if table_name in aliases:
            return canonical_name
    return table_name


def read_table_rows(data_dir: Path | str, table_name: str, graph: KnowledgeGraph) -> list[dict[str, str]]:
    base = Path(data_dir)
    aliases = unique_items([table_name, *TABLE_ALIASES.get(table_name, [])])
    for alias in aliases:
        path = base / f"{alias}.csv"
        if path.exists():
            with path.open(newline="", encoding="utf-8") as handle:
                return [dict(row) for row in csv.DictReader(handle)]

    graph.warnings.append(
        f"Missing CSV for source table {table_name}. Tried: {', '.join(f'{alias}.csv' for alias in aliases)}"
    )
    return []


def unique_items(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


def add_skip_warnings(graph: KnowledgeGraph, skipped: Counter[str]) -> None:
    for message, count in sorted(skipped.items()):
        graph.warnings.append(f"{message}: {count} row(s)")


def viewer_subset(
    graph: dict[str, Any],
    *,
    full: bool,
    max_nodes: int,
    max_edges: int,
    application_name: str | None,
    application_id: str | None,
    focus_depth: int,
) -> dict[str, Any]:
    if application_name or application_id:
        return focus_application_graph(
            graph,
            application_name=application_name,
            application_id=application_id,
            depth=focus_depth,
            max_nodes=max_nodes,
            max_edges=max_edges,
            exclude_edge_types=set(),
        )
    if full:
        return with_metadata(graph, sampled=False)
    return sample_graph(graph, max_nodes=max_nodes, max_edges=max_edges)


if __name__ == "__main__":
    main()
