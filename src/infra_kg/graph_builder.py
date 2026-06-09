"""Build a Memgraph-friendly topology graph from APM tables."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from infra_kg.embeddings import EmbeddingProvider
from infra_kg.env import load_dotenv
from infra_kg.llm import LLMSettings, OpenAICompatibleLLM

REQUIRED_TABLES = [
    "apm_cluster",
    "apm_subclusters",
    "apm_applications",
    "apm_application_daps",
    "apm_obso",
    "apm_technologies",
]

RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
STATUS_ORDER = {"supported": 1, "aging": 2, "obsolete": 3}
PROPERTY_KEY_PATTERN = re.compile(r"[^0-9A-Za-z_]+")


@dataclass
class GraphNode:
    label: str
    identity: str
    properties: dict[str, Any]

    @property
    def key(self) -> str:
        return make_key(self.label, self.identity)


@dataclass(frozen=True)
class GraphEdge:
    start_key: str
    type: str
    end_key: str
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.start_key, self.type, self.end_key)


@dataclass
class KnowledgeGraph:
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    _edge_keys: set[tuple[str, str, str]] = field(default_factory=set, init=False, repr=False)

    def add_node(self, label: str, identity: str, properties: dict[str, Any]) -> str:
        key = make_key(label, identity)
        clean = clean_properties({"id": identity, **properties})
        existing = self.nodes.get(key)
        if existing:
            existing.properties.update(clean)
        else:
            self.nodes[key] = GraphNode(label=label, identity=identity, properties=clean)
        return key

    def add_edge(
        self,
        start_key: str,
        edge_type: str,
        end_key: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        clean = clean_properties(properties or {})
        edge = GraphEdge(start_key=start_key, type=edge_type, end_key=end_key, properties=clean)
        if edge.key in self._edge_keys:
            return
        self.edges.append(edge)
        self._edge_keys.add(edge.key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "key": node.key,
                    "label": node.label,
                    "identity": node.identity,
                    "properties": node.properties,
                }
                for node in sorted(self.nodes.values(), key=lambda item: item.key)
            ],
            "edges": [
                {
                    "start_key": edge.start_key,
                    "type": edge.type,
                    "end_key": edge.end_key,
                    "properties": edge.properties,
                }
                for edge in sorted(self.edges, key=lambda item: item.key)
            ],
            "warnings": self.warnings,
        }

    def label_counts(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            counts[node.label] += 1
        return dict(sorted(counts.items()))

    def edge_counts(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for edge in self.edges:
            counts[edge.type] += 1
        return dict(sorted(counts.items()))


def build_graph(
    data_dir: Path | str,
    *,
    include_derived: bool = True,
    include_retrieval_text: bool = True,
    embedding_provider: EmbeddingProvider | None = None,
    enrich_with_llm: bool = False,
    env_path: Path | str = ".env",
    max_related_group_size: int = 200,
) -> KnowledgeGraph:
    tables = load_tables(data_dir)
    return build_graph_from_tables(
        tables,
        include_derived=include_derived,
        include_retrieval_text=include_retrieval_text,
        embedding_provider=embedding_provider,
        enrich_with_llm=enrich_with_llm,
        env_path=env_path,
        max_related_group_size=max_related_group_size,
    )


def build_graph_from_tables(
    tables: dict[str, list[dict[str, str]]],
    *,
    include_derived: bool = True,
    include_retrieval_text: bool = True,
    embedding_provider: EmbeddingProvider | None = None,
    enrich_with_llm: bool = False,
    env_path: Path | str = ".env",
    max_related_group_size: int = 200,
) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    validate_required_tables(tables, graph)

    clusters = by_id(tables.get("apm_cluster", []))
    subclusters = by_id(tables.get("apm_subclusters", []))
    applications = by_id(tables.get("apm_applications", []))
    technologies = by_id(tables.get("apm_technologies", []))
    obso_records = by_id(tables.get("apm_obso", []))

    for row in clusters.values():
        graph.add_node(
            "Cluster",
            row["id"],
            row_properties(row, "apm_cluster"),
        )

    for row in subclusters.values():
        subcluster_key = graph.add_node(
            "Subcluster",
            row["id"],
            row_properties(row, "apm_subclusters"),
        )
        cluster_id = row.get("apm_cluster", "")
        cluster_key = make_key("Cluster", cluster_id)
        if cluster_id in clusters:
            graph.add_edge(cluster_key, "HAS_SUBCLUSTER", subcluster_key, {"source_fk": "apm_cluster"})
        else:
            graph.warnings.append(f"Subcluster {row['id']} references missing cluster {cluster_id}")

    app_context: dict[str, dict[str, Any]] = {}
    for row in applications.values():
        cluster_id = row.get("apm_cluster", "")
        app_context[row["id"]] = {"cluster_id": cluster_id}
        app_key = graph.add_node(
            "Application",
            row["id"],
            row_properties(row, "apm_applications"),
        )
        cluster_key = make_key("Cluster", cluster_id)
        if cluster_id in clusters:
            graph.add_edge(cluster_key, "HAS_APPLICATION", app_key, {"source_fk": "apm_cluster"})
        else:
            graph.warnings.append(f"Application {row['id']} references missing cluster {cluster_id}")

    for row in tables.get("apm_application_daps", []):
        application_id = row.get("apm_application", "")
        dap_id = row.get("dap_id") or row.get("id", "")
        binding_key = graph.add_node(
            "ApplicationDap",
            row.get("id") or f"{application_id}:{dap_id}",
            row_properties(row, "apm_application_daps"),
        )
        dap_key = graph.add_node(
            "Dap",
            dap_id,
            {
                "name": row.get("dap_name"),
                "source_table": "apm_application_daps",
            },
        )
        if application_id in applications:
            app_key = make_key("Application", application_id)
            graph.add_edge(
                app_key,
                "HAS_DAP_BINDING",
                binding_key,
                {"source_fk": "apm_application"},
            )
            graph.add_edge(
                binding_key,
                "TARGETS_DAP",
                dap_key,
                {"source_field": "dap_id"},
            )
            graph.add_edge(
                app_key,
                "EXPOSES_DAP",
                dap_key,
                {
                    **row_properties(row, "apm_application_daps"),
                    "binding_id": row.get("id"),
                    "direction": row.get("direction"),
                    "protocol": row.get("protocol"),
                    "source_fk": "apm_application",
                },
            )
            app_context.setdefault(application_id, {}).setdefault("daps", []).append(
                {
                    "dap_id": dap_id,
                    "name": row.get("dap_name"),
                    "direction": row.get("direction"),
                    "protocol": row.get("protocol"),
                }
            )
        else:
            graph.warnings.append(f"DAP binding {row.get('id')} references missing application {application_id}")

    for row in technologies.values():
        graph.add_node(
            "Technology",
            row["id"],
            row_properties(row, "apm_technologies"),
        )

    for row in obso_records.values():
        obso_key = graph.add_node(
            "ObsolescenceRecord",
            row["id"],
            row_properties(row, "apm_obso"),
        )
        host = row.get("host", "")
        host_key = graph.add_node("Host", host, {"name": host, "source_table": "apm_obso"})
        graph.add_edge(obso_key, "ON_HOST", host_key, {"source_field": "host"})

        application_id = row.get("application_id", "")
        technology_id = row.get("technology_id", "")
        if application_id in applications:
            app_key = make_key("Application", application_id)
            graph.add_edge(app_key, "HAS_OBSOLESCENCE_RECORD", obso_key, {"source_fk": "application_id"})
            app_context.setdefault(application_id, {}).setdefault("hosts", []).append(host)
            app_context.setdefault(application_id, {}).setdefault("technologies", []).append(technology_id)
        else:
            graph.warnings.append(f"Obsolescence record {row['id']} references missing application {application_id}")

        if technology_id in technologies:
            technology_key = make_key("Technology", technology_id)
            graph.add_edge(
                obso_key,
                "REFERENCES_TECHNOLOGY",
                technology_key,
                {"source_fk": "technology_id"},
            )
        else:
            graph.warnings.append(f"Obsolescence record {row['id']} references missing technology {technology_id}")

    if include_derived:
        add_derived_topology_edges(
            graph,
            applications,
            technologies,
            obso_records,
            tables.get("apm_application_daps", []),
            max_related_group_size=max_related_group_size,
        )

    if enrich_with_llm:
        enrich_application_nodes(graph, applications, app_context, env_path)

    if include_retrieval_text:
        add_retrieval_text(graph)

    if embedding_provider is not None:
        add_embeddings(graph, embedding_provider)

    return graph


def add_derived_topology_edges(
    graph: KnowledgeGraph,
    applications: dict[str, dict[str, str]],
    technologies: dict[str, dict[str, str]],
    obso_records: dict[str, dict[str, str]],
    dap_rows: Iterable[dict[str, str]],
    max_related_group_size: int = 200,
) -> None:
    app_host_records: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    app_technology_records: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    host_technology_records: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    for row in obso_records.values():
        application_id = row.get("application_id", "")
        technology_id = row.get("technology_id", "")
        host = row.get("host", "")
        if application_id in applications and host:
            app_host_records[(application_id, host)].append(row)
        if application_id in applications and technology_id in technologies:
            app_technology_records[(application_id, technology_id)].append(row)
        if host and technology_id in technologies:
            host_technology_records[(host, technology_id)].append(row)

    for (application_id, host), records in app_host_records.items():
        graph.add_edge(
            make_key("Application", application_id),
            "DEPLOYED_ON",
            make_key("Host", host),
            aggregate_obso_properties(records),
        )

    for (application_id, technology_id), records in app_technology_records.items():
        props = aggregate_obso_properties(records)
        props["hosts"] = sorted({record.get("host", "") for record in records if record.get("host")})
        graph.add_edge(
            make_key("Application", application_id),
            "USES_TECHNOLOGY",
            make_key("Technology", technology_id),
            props,
        )

    for (host, technology_id), records in host_technology_records.items():
        props = aggregate_obso_properties(records)
        props["applications"] = sorted({record.get("application_id", "") for record in records if record.get("application_id")})
        graph.add_edge(
            make_key("Host", host),
            "HAS_TECHNOLOGY",
            make_key("Technology", technology_id),
            props,
        )

    app_reasons = application_relationship_reasons(
        applications,
        obso_records.values(),
        dap_rows,
        graph.warnings,
        max_group_size=max_related_group_size,
    )
    for (left_app, right_app), reasons in app_reasons.items():
        graph.add_edge(
            make_key("Application", left_app),
            "RELATED_TO",
            make_key("Application", right_app),
            {
                "reasons": sorted(reasons),
                "strength": len(reasons),
                "derived": True,
            },
        )


def application_relationship_reasons(
    applications: dict[str, dict[str, str]],
    obso_rows: Iterable[dict[str, str]],
    dap_rows: Iterable[dict[str, str]],
    warnings: list[str] | None = None,
    max_group_size: int = 200,
) -> dict[tuple[str, str], set[str]]:
    index: dict[str, dict[str, set[str]]] = {
        "cluster": defaultdict(set),
        "host": defaultdict(set),
        "technology": defaultdict(set),
        "dap": defaultdict(set),
    }
    for application_id, row in applications.items():
        index["cluster"][row.get("apm_cluster", "")].add(application_id)
    for row in obso_rows:
        index["host"][row.get("host", "")].add(row.get("application_id", ""))
        index["technology"][row.get("technology_id", "")].add(row.get("application_id", ""))
    for row in dap_rows:
        index["dap"][row.get("dap_id", "")].add(row.get("apm_application", ""))

    relationships: dict[tuple[str, str], set[str]] = defaultdict(set)
    for reason_type, values in index.items():
        for value, app_ids in values.items():
            clean_app_ids = sorted(app_id for app_id in app_ids if app_id in applications)
            if not value or len(clean_app_ids) < 2:
                continue
            if max_group_size > 0 and len(clean_app_ids) > max_group_size:
                if warnings is not None:
                    warnings.append(
                        f"Skipped RELATED_TO expansion for shared_{reason_type}:{value} "
                        f"because it contains {len(clean_app_ids)} applications "
                        f"(limit {max_group_size})"
                    )
                continue
            for idx, left_app in enumerate(clean_app_ids):
                for right_app in clean_app_ids[idx + 1 :]:
                    relationships[(left_app, right_app)].add(f"shared_{reason_type}:{value}")
    return relationships


def aggregate_obso_properties(records: list[dict[str, str]]) -> dict[str, Any]:
    risk_levels = sorted({record.get("risk_level", "") for record in records if record.get("risk_level")})
    statuses = sorted({record.get("obsolescence_status", "") for record in records if record.get("obsolescence_status")})
    return {
        "source_table": "apm_obso",
        "obso_record_count": len(records),
        "risk_levels": risk_levels,
        "statuses": statuses,
        "max_risk": max(risk_levels, key=lambda item: RISK_ORDER.get(item, 0), default=""),
        "worst_status": max(statuses, key=lambda item: STATUS_ORDER.get(item, 0), default=""),
    }


def enrich_application_nodes(
    graph: KnowledgeGraph,
    applications: dict[str, dict[str, str]],
    app_context: dict[str, dict[str, Any]],
    env_path: Path | str,
) -> None:
    load_dotenv(env_path)
    settings = LLMSettings.from_env()
    if settings is None:
        graph.warnings.append("LLM enrichment requested but no OpenAI-compatible LLM env vars were found")
        return

    llm = OpenAICompatibleLLM(settings)
    for application_id, row in applications.items():
        key = make_key("Application", application_id)
        enrichment = llm.enrich_application(row, app_context.get(application_id, {}))
        graph.nodes[key].properties.update(clean_properties(enrichment))


def add_retrieval_text(graph: KnowledgeGraph) -> None:
    neighbor_index: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        start_node = graph.nodes.get(edge.start_key)
        end_node = graph.nodes.get(edge.end_key)
        if not start_node or not end_node:
            continue
        neighbor_index[edge.start_key].append(f"{edge.type} {node_display(end_node)}")
        neighbor_index[edge.end_key].append(f"INCOMING_{edge.type} {node_display(start_node)}")

    for node in graph.nodes.values():
        fields = []
        for key, value in sorted(node.properties.items()):
            if key in {"embedding", "retrieval_text"}:
                continue
            if isinstance(value, list):
                value_text = ", ".join(str(item) for item in value)
            else:
                value_text = str(value)
            fields.append(f"{key}: {value_text}")
        relationships = "; ".join(sorted(neighbor_index.get(node.key, []))[:40])
        text = f"{node.label}. " + ". ".join(fields)
        if relationships:
            text += f". Relationships: {relationships}"
        node.properties["retrieval_text"] = text[:4000]


def add_embeddings(graph: KnowledgeGraph, provider: EmbeddingProvider) -> None:
    nodes = sorted(graph.nodes.values(), key=lambda item: item.key)
    texts = [str(node.properties.get("retrieval_text") or node_display(node)) for node in nodes]
    embeddings = provider.embed_texts(texts)
    if len(embeddings) != len(nodes):
        raise RuntimeError(f"Embedding provider returned {len(embeddings)} embeddings for {len(nodes)} nodes")

    for node, embedding in zip(nodes, embeddings):
        node.properties["embedding"] = [float(value) for value in embedding]
        node.properties["embedding_model"] = provider.__class__.__name__
        node.properties["embedding_dimensions"] = len(embedding)


def node_display(node: GraphNode) -> str:
    name = node.properties.get("name")
    if name and name != node.identity:
        return f"{node.label} {name} ({node.identity})"
    return f"{node.label} {node.identity}"


def load_tables(data_dir: Path | str) -> dict[str, list[dict[str, str]]]:
    base = Path(data_dir)
    return {table_name: read_csv(base / f"{table_name}.csv") for table_name in REQUIRED_TABLES}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required table file: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def validate_required_tables(tables: dict[str, list[dict[str, str]]], graph: KnowledgeGraph) -> None:
    for table_name in REQUIRED_TABLES:
        if table_name not in tables:
            graph.warnings.append(f"Missing table {table_name}")


def by_id(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        row_id = row.get("id", "")
        if row_id:
            result[row_id] = row
    return result


def row_properties(row: dict[str, str], table_name: str) -> dict[str, Any]:
    properties: dict[str, Any] = {"source_table": table_name}
    used_keys = set(properties)
    for column_name, value in row.items():
        property_key = unique_property_key(normalize_property_key(column_name), used_keys)
        properties[property_key] = value
    return properties


def normalize_property_key(column_name: str) -> str:
    key = PROPERTY_KEY_PATTERN.sub("_", column_name.strip())
    key = re.sub(r"_+", "_", key).strip("_")
    if not key:
        key = "field"
    if key[0].isdigit():
        key = f"field_{key}"
    return key


def unique_property_key(key: str, used_keys: set[str]) -> str:
    if key not in used_keys:
        used_keys.add(key)
        return key

    suffix = 2
    while f"{key}_{suffix}" in used_keys:
        suffix += 1
    unique_key = f"{key}_{suffix}"
    used_keys.add(unique_key)
    return unique_key


def make_key(label: str, identity: str) -> str:
    return f"{label}:{identity}"


def split_key(key: str) -> tuple[str, str]:
    label, identity = key.split(":", 1)
    return label, identity


def clean_properties(properties: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in properties.items():
        if value is None or value == "":
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
        elif isinstance(value, list):
            clean[key] = [item for item in value if isinstance(item, (str, int, float, bool)) and item != ""]
        else:
            clean[key] = str(value)
    return clean


def write_graph_json(graph: KnowledgeGraph, path: Path | str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


def write_graph_cypher(graph: KnowledgeGraph, path: Path | str, *, clear: bool = True) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if clear:
        lines.append("MATCH (n) DETACH DELETE n;")
        lines.append("")

    for label in sorted({node.label for node in graph.nodes.values()}):
        lines.append(f"CREATE INDEX ON :{label}(id);")
    for index_statement in vector_index_statements(graph):
        lines.append(index_statement)
    lines.append("")

    for node in sorted(graph.nodes.values(), key=lambda item: item.key):
        lines.append(
            f"MERGE (n:{node.label} {{id: {cypher_literal(node.identity)}}}) "
            f"SET n += {cypher_literal(node.properties)};"
        )
    lines.append("")

    for edge in sorted(graph.edges, key=lambda item: item.key):
        start_label, start_id = split_key(edge.start_key)
        end_label, end_id = split_key(edge.end_key)
        lines.append(
            f"MATCH (a:{start_label} {{id: {cypher_literal(start_id)}}}), "
            f"(b:{end_label} {{id: {cypher_literal(end_id)}}}) "
            f"MERGE (a)-[r:{edge.type}]->(b) "
            f"SET r += {cypher_literal(edge.properties)};"
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def vector_index_statements(graph: KnowledgeGraph) -> list[str]:
    statements: list[str] = []
    for label, dimension in vector_dimensions_by_label(graph).items():
        count = sum(1 for node in graph.nodes.values() if node.label == label and "embedding" in node.properties)
        capacity = max(100, count * 2)
        index_name = f"{label.lower()}_embedding_index"
        statements.append(
            f"CREATE VECTOR INDEX {index_name} ON :{label}(embedding) "
            f"WITH CONFIG {{'dimension': {dimension}, 'capacity': {capacity}, 'metric': 'cos'}};"
        )
    return statements


def vector_dimensions_by_label(graph: KnowledgeGraph) -> dict[str, int]:
    dimensions: dict[str, int] = {}
    for node in graph.nodes.values():
        embedding = node.properties.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            continue
        dimension = len(embedding)
        existing = dimensions.get(node.label)
        if existing is not None and existing != dimension:
            raise ValueError(f"Mixed embedding dimensions for label {node.label}: {existing} and {dimension}")
        dimensions[node.label] = dimension
    return dict(sorted(dimensions.items()))


def cypher_literal(value: Any) -> str:
    if isinstance(value, dict):
        items = ", ".join(f"{key}: {cypher_literal(item)}" for key, item in sorted(value.items()))
        return "{" + items + "}"
    if isinstance(value, list):
        return "[" + ", ".join(cypher_literal(item) for item in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value))
