# Infrastructure Topology Knowledge Graph

This repository is a small proof of concept for turning APM-style relational
tables into a property graph that can be loaded into Memgraph and inspected in
Memgraph Lab.

The graph builder keeps the table relationships deterministic:

- `apm_cluster.id -> apm_subclusters.apm_cluster`
- `apm_cluster.id -> apm_applications.apm_cluster`
- `apm_applications.id -> apm_application_daps.apm_application`
- `apm_applications.id -> apm_obso.application_id`
- `apm_obso.technology_id -> apm_technologies.id`
- `apm_obso.host` becomes a `Host` node

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

Export with local test embeddings:

```bash
python3 scripts/export_graph.py --embed hash --embedding-dimensions 64
```

Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

If Memgraph is already running locally on Bolt port `7687`, load the graph:

```bash
python3 -m pip install -r requirements.txt
python3 scripts/load_memgraph.py --clear
```

Then open Memgraph Lab and inspect paths with:

```cypher
MATCH p=(c:Cluster)-[:HAS_APPLICATION]->(a:Application)-[:DEPLOYED_ON]->(h:Host)
RETURN p
LIMIT 50;
```

If you want to start Memgraph with Docker:

```bash
docker compose up -d memgraph lab
python3 scripts/load_memgraph.py --clear
```

Memgraph Lab will be available at <http://localhost:3000>.

## Outputs

- Mock tables: `data/mock/*.csv`
- Graph JSON: `build/topology_graph.json`
- Graph Cypher: `build/topology_graph.cypher`
- Hash-embedding test JSON: `build/topology_graph_hash_embeddings.json`
- Hash-embedding test Cypher: `build/topology_graph_hash_embeddings.cypher`
- Useful inspection queries: `cypher/inspect_topology.cypher`
- Vector search examples: `cypher/vector_search.cypher`

## Graph Model

Primary nodes:

- `Cluster`
- `Subcluster`
- `Application`
- `Dap`
- `ObsolescenceRecord`
- `Technology`
- `Host`

Source-of-truth edges:

- `(:Cluster)-[:HAS_SUBCLUSTER]->(:Subcluster)`
- `(:Cluster)-[:HAS_APPLICATION]->(:Application)`
- `(:Application)-[:EXPOSES_DAP]->(:Dap)`
- `(:Application)-[:HAS_OBSOLESCENCE_RECORD]->(:ObsolescenceRecord)`
- `(:ObsolescenceRecord)-[:ON_HOST]->(:Host)`
- `(:ObsolescenceRecord)-[:REFERENCES_TECHNOLOGY]->(:Technology)`

Derived topology edges for easier agent traversal:

- `(:Application)-[:DEPLOYED_ON]->(:Host)`
- `(:Application)-[:USES_TECHNOLOGY]->(:Technology)`
- `(:Host)-[:HAS_TECHNOLOGY]->(:Technology)`
- `(:Application)-[:RELATED_TO]->(:Application)` when apps share hosts,
  clusters, DAPs, or technologies.

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
