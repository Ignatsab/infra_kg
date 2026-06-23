# Infrastructure Topology Knowledge Graph

This repository is a small proof of concept for turning APM-style relational
tables into a property graph that can be loaded into Memgraph and inspected in
Memgraph Lab.

The graph builder keeps the table relationships deterministic:

- `apm_cluster.id -> apm_subclusters.apm_cluster`
- `apm_cluster.id -> apm_applications.apm_cluster`
- `apm_contacts.id -> apm_applications.production_domain_manager`
- `apm_contacts.id -> apm_applications.application_manager`
- `apm_contacts.id -> apm_applications.domain_manager`
- `apm_contacts.id -> apm_applications.production_manager`
- `apm_contacts.id -> apm_applications.apm_spoc`
- `apm_applications.id -> apm_application_daps.apm_application`
- `apm_applications.id -> apm_obso.application_id`
- `apm_obso.technology_id -> apm_technologies.id`
- `apm_obso.host` becomes a `Host` node
- `apm_obso.criticality`, `apm_obso.env`, and
  `apm_obso.location_country` become reusable dimension nodes

LLM usage is optional. The core topology edges are built from IDs and foreign
keys so repeated runs are stable. An OpenAI-compatible local LLM can be used to
add summaries and semantic tags to application nodes after the graph is built.

## Quick Start

Generate mock source tables:

```bash
python3 scripts/generate_mock_data.py
```

Export the graph to JSON and Cypher:

```bash
python3 scripts/export_graph.py
```

For a first pass on larger real CSV exports, start with only the trusted FK
graph:

```bash
python3 scripts/export_graph.py --no-derived
python3 scripts/render_graph_viewer.py
```

Then enable derived shortcut edges:

```bash
python3 scripts/export_graph.py --max-related-group-size 200
```

`RELATED_TO` edges can grow quickly because every app sharing a large cluster,
technology, host, or DAP can become related to every other app in that group.
The exporter skips `RELATED_TO` expansion for groups above
`--max-related-group-size` while preserving all source FK edges.

For large remote Memgraph loads, a practical first full-topology load is to keep
the concrete derived shortcuts but skip only app-to-app `RELATED_TO`:

```bash
python3 scripts/load_memgraph.py \
  --clear \
  --data-dir data/real/APM_DATA \
  --no-related-to \
  --batch-size 1000 \
  --uri "bolt://HOST:PORT" \
  --username "YOUR_USERNAME" \
  --password "YOUR_PASSWORD"
```

This still loads `DEPLOYED_ON`, `USES_TECHNOLOGY`, and `HAS_TECHNOLOGY`, while
avoiding the densest derived relationship type.

Export with local test embeddings:

```bash
python3 scripts/export_graph.py --embed hash --embedding-dimensions 64
```

Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Check whether Memgraph is already running:

```bash
python3 -m pip install -r requirements.txt
nc -zv 127.0.0.1 7687
docker ps | grep 7687
```

If `nc` says the port is open, or `docker ps` shows a Memgraph container mapped
to `7687`, reuse the running Memgraph and load the graph:

```bash
python3 scripts/load_memgraph.py --clear --uri bolt://127.0.0.1:7687
```

If nothing is running on `7687`, start Memgraph and Lab with Docker, then load
the graph:

```bash
docker compose up -d memgraph
docker compose ps
python3 scripts/load_memgraph.py --clear --uri bolt://127.0.0.1:7687
docker compose up -d lab
```

Memgraph Lab will be available at <http://localhost:3000>.

Then open Memgraph Lab and inspect paths with:

```cypher
MATCH p=(c:Cluster)-[:HAS_APPLICATION]->(a:Application)-[:DEPLOYED_ON]->(h:Host)
RETURN p
LIMIT 50;
```

If Docker has started the containers but the loader still says connection
refused or `ServiceUnavailable`, force IPv4 and let the loader wait:

```bash
python3 scripts/load_memgraph.py --clear --uri bolt://127.0.0.1:7687 --connect-retries 120 --connect-retry-delay 2
```

Useful checks:

```bash
docker compose ps
docker compose logs memgraph
nc -zv 127.0.0.1 7687
python3 scripts/check_memgraph.py
```

Troubleshooting notes:

- `dependency failed to start: container ... is unhealthy` means Docker started
  the Memgraph container, but Docker's health check did not pass yet. Start only
  `memgraph`, wait until `docker compose ps` says `healthy`, then load the graph
  and start `lab`.
- `Connection refused` means nothing is accepting Bolt connections on port
  `7687` yet.
- `incomplete handshake response` means the port opened, but the Bolt driver
  could not complete the Memgraph protocol handshake. Reinstall dependencies
  with `python3 -m pip install -r requirements.txt` so the Neo4j driver is
  pinned to the compatible major version.
- `vm.max_map_count ... is too low` is a host/VM setting warning from Memgraph.
  If Memgraph keeps restarting or staying unhealthy and you have sudo access,
  run `sudo sysctl -w vm.max_map_count=524288`, then restart Memgraph.
- LiteLLM and `pkg_resources` warnings in Memgraph logs are not blockers for
  loading this graph.

If Memgraph Lab is hard to open through a Cloud IDE port proxy, render the
generated graph directly:

```bash
python3 scripts/render_graph_viewer.py
python3 -m http.server 8080 --directory build
```

Then open forwarded port `8080` and go to `/topology_viewer.html`.

For large real graphs, the HTML viewer renders a representative sample by
default so it opens quickly and remains readable. The sample tries to include
all node labels and relationship types:

```bash
python3 scripts/render_graph_viewer.py --max-nodes 120 --max-edges 180
```

To render only the neighborhood around one application, search by application
name or id. Matching is case-insensitive and partial for names:

```bash
python3 scripts/render_graph_viewer.py \
  --application-name "SERVICE NOW" \
  --focus-depth 2 \
  --max-nodes 120 \
  --max-edges 180 \
  --output build/service_now_viewer.html
```

Depth `1` shows direct neighbors. Depth `2` also includes the next hop, such as
obsolescence dimensions, DAP targets, hosts, and technologies. If app-to-app
relationships are too dense, skip them for the focused viewer:

```bash
python3 scripts/render_graph_viewer.py \
  --application-name "SERVICE NOW" \
  --exclude-edge-type RELATED_TO \
  --output build/service_now_viewer.html
```

If you intentionally want the full graph:

```bash
python3 scripts/render_graph_viewer.py --full
```

Evaluate the full exported graph automatically:

```bash
python3 scripts/evaluate_graph.py --graph-json build/topology_graph.json --out-json build/graph_quality_report.json
```

The evaluator checks structural quality: broken edges, schema mismatches,
isolated nodes, connected components, reachability from clusters, required
relationship coverage, duplicate edges, and high-degree hubs.

## Outputs

- Mock tables: `data/mock/*.csv`
- Graph JSON: `build/topology_graph.json`
- Graph Cypher: `build/topology_graph.cypher`
- Hash-embedding test JSON: `build/topology_graph_hash_embeddings.json`
- Hash-embedding test Cypher: `build/topology_graph_hash_embeddings.cypher`
- Useful inspection queries: `cypher/inspect_topology.cypher`
- Vector search examples: `cypher/vector_search.cypher`
- Graph quality report: `build/graph_quality_report.json`

## Graph Model

Primary nodes:

- `Cluster`
- `Subcluster`
- `Application`
- `ApplicationDap`
- `Contact`
- `Criticality`
- `Dap`
- `Environment`
- `ObsolescenceRecord`
- `LocationCountry`
- `Technology`
- `Host`

Source-of-truth edges:

- `(:Cluster)-[:HAS_SUBCLUSTER]->(:Subcluster)`
- `(:Cluster)-[:HAS_APPLICATION]->(:Application)`
- `(:Application)-[:HAS_PRODUCTION_DOMAIN_MANAGER]->(:Contact)`
- `(:Application)-[:HAS_APPLICATION_MANAGER]->(:Contact)`
- `(:Application)-[:HAS_DOMAIN_MANAGER]->(:Contact)`
- `(:Application)-[:HAS_PRODUCTION_MANAGER]->(:Contact)`
- `(:Application)-[:HAS_APM_SPOC]->(:Contact)`
- `(:Application)-[:EXPOSES_DAP]->(:Dap)`
- `(:Application)-[:HAS_DAP_BINDING]->(:ApplicationDap)`
- `(:ApplicationDap)-[:TARGETS_DAP]->(:Dap)`
- `(:Application)-[:HAS_OBSOLESCENCE_RECORD]->(:ObsolescenceRecord)`
- `(:ObsolescenceRecord)-[:ON_HOST]->(:Host)`
- `(:ObsolescenceRecord)-[:REFERENCES_TECHNOLOGY]->(:Technology)`
- `(:ObsolescenceRecord)-[:HAS_CRITICALITY]->(:Criticality)`
- `(:ObsolescenceRecord)-[:IN_ENVIRONMENT]->(:Environment)`
- `(:ObsolescenceRecord)-[:LOCATED_IN_COUNTRY]->(:LocationCountry)`

Derived topology edges for easier agent traversal:

- `(:Application)-[:DEPLOYED_ON]->(:Host)`
- `(:Application)-[:USES_TECHNOLOGY]->(:Technology)`
- `(:Host)-[:HAS_TECHNOLOGY]->(:Technology)`
- `(:Application)-[:RELATED_TO]->(:Application)` when apps share hosts,
  clusters, DAPs, or technologies.

## Source Columns

The graph preserves all source columns by default:

- Entity tables such as `apm_cluster`, `apm_subclusters`,
  `apm_applications`, `apm_contacts`, `apm_obso`, and `apm_technologies`
  become graph nodes with every CSV/DB column copied as a node property.
- `apm_obso.criticality`, `apm_obso.env`, and
  `apm_obso.location_country` are also promoted into reusable dimension nodes
  so agents can traverse/filter by those values without losing the raw
  properties on each `ObsolescenceRecord`.
- The join-like `apm_application_daps` table is represented as row-level
  `ApplicationDap` nodes so every binding row keeps all of its columns.
- The direct `(:Application)-[:EXPOSES_DAP]->(:Dap)` edge is still kept as a
  traversal shortcut, and it also receives the source binding row properties.

CSV table aliases are supported for export convenience. In particular,
`apm_clusters.csv` is accepted as an alias for the canonical internal table
name `apm_cluster`.

Column names are normalized into Memgraph-safe property keys. For example,
`Owner Email` becomes `Owner_Email`.

The intended layering is:

1. Source properties preserve raw table data.
2. Deterministic FK edges preserve trusted topology.
3. Derived shortcut edges make the topology agent easier to query.
4. LLM summaries and embeddings use the full row context without changing the
   trusted topology edges.

## Optional LLM Enrichment

Create a `.env` file with OpenAI-compatible settings:

```dotenv
LLM_BASE_URL=https://your-proxy.example.com/v1
LLM_API_KEY=...
LLM_MODEL=your-local-model
```

Alternative variable names are also accepted:

- `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`
- `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_API_KEY`, `LOCAL_LLM_MODEL`

Then export with:

```bash
python3 scripts/export_graph.py --enrich-with-llm
```

The LLM only adds application summaries/tags. It does not create or remove
topology edges.

If the exporter says no LLM env vars were found, run the safe checker. It never
prints the API key:

```bash
python3 scripts/check_llm_env.py --env-path .env
```

If your `.env` lives somewhere else:

```bash
python3 scripts/export_graph.py --enrich-with-llm --env-path /path/to/.env
```

## Optional Vector Retrieval

You do not need embeddings to create or inspect the graph. For the first visual
check, exact Cypher traversal and property search are enough:

```cypher
MATCH p=(a:Application)-[:USES_TECHNOLOGY]->(t:Technology)
WHERE toLower(t.name) CONTAINS "java"
RETURN p;
```

Embeddings become useful once your topology agent needs semantic retrieval, for
example queries like "apps with old payment database risk" where the user does
not know exact application, host, or technology names.

This project supports two embedding modes:

- `--embed hash` creates deterministic local vectors only for plumbing tests.
  These are not real semantic embeddings.
- `--embed openai` calls an OpenAI-compatible `/embeddings` endpoint, which can
  be your work proxy/local model.

For real semantic retrieval, set:

```dotenv
EMBEDDING_BASE_URL=https://your-proxy.example.com/v1
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_DIMENSIONS=1536
```

Aliases such as `EMBEDDING_LINK`, `EMBEDDING_KEY`, `LLM_LINK`, `LLM_KEY`, and
`LLM_MODEL` are also accepted. If your URL already ends with `/embeddings`, the
exporter normalizes it to the OpenAI-compatible base URL automatically.

Check the embedding environment safely:

```bash
python3 scripts/check_embedding_env.py --env-path .env
```

Export files with real semantic embeddings:

```bash
python3 scripts/export_graph.py \
  --embed openai \
  --out-json build/topology_graph_real_embeddings.json \
  --out-cypher build/topology_graph_real_embeddings.cypher
```

Then load embedded nodes into Memgraph:

```bash
python3 scripts/load_memgraph.py --clear --embed openai
```

Search embedded nodes:

```bash
python3 scripts/search_memgraph.py "obsolete payment database risk" \
  --embed openai \
  --index application_embedding_index
```

Memgraph can run vector search and graph traversal in the same Cypher query, so
the intended retrieval flow is:

1. Embed the user question.
2. Retrieve the closest graph nodes with `vector_search.search`.
3. Traverse from those nodes through deterministic KG edges.
4. Give the topology agent the retrieved paths as grounded context.

## Why Not GraFlo In This First Pass?

GraFlo is a good candidate once the model stabilizes: it provides a manifest
layer for converting CSV/SQL/JSON/XML into labeled property graphs and lists
Memgraph among its supported graph targets. For this proof of concept, direct
Cypher keeps the pipeline small and easy to inspect while we validate the
topology shape.
