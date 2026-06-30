# GraFlo APM Topology Experiment

This folder is a separate experiment for trying the same APM topology graph with
GraFlo, without changing the current `src/infra_kg` builder or Memgraph loader.

GraFlo is manifest-driven: the manifest describes vertices, edges, identities,
properties, and ingestion resources. Runtime bindings connect those resources to
physical CSV files. In our case the important part is the table relationship
contract: which table column creates a node id, and which table column points to
another node id.

The generated manifest is table-centric. Each CSV table becomes one resource,
and central tables such as `apm_applications`, `apm_application_daps`, and
`apm_obso` create their surrounding topology in the same pipeline. Foreign-key
endpoints use scalar `from` values, for example `from: apm_cluster`, because the
target vertex identity is `id` by convention.

This experiment follows the Graflo documentation and the official
`examples/4-ingest-neo4j` pattern:

- `schema.graph.vertex_config.vertices` defines logical node types.
- `schema.graph.edge_config.edges` defines logical edge types with `relation`.
- `ingestion_model.resources[*].pipeline` maps each source table record into
  vertices and edges.
- `Bindings` and `FileConnector` objects are created in Python at runtime.

## Files

- `apm_mapping.py` - compact source of truth for APM vertices and edges.
- `generate_manifest.py` - generates a GraFlo YAML manifest from the
  mapping and current CSV headers.
- `manifest.apm_topology.yaml` - generated manifest draft.
- `make_bindings.py` - creates runtime Graflo `FileConnector` bindings for a
  CSV folder.
- `validate_manifest.py` - optional validation using Graflo, if installed.
- `ingest.py` - optional Graflo ingestion entrypoint following the
  `4-ingest-neo4j` runtime pattern.

## Generate Manifest

From the repository root:

```bash
python3 graflo_experiment/generate_manifest.py \
  --data-dir data/mock \
  --output graflo_experiment/manifest.apm_topology.yaml
```

For real CSV exports:

```bash
python3 graflo_experiment/generate_manifest.py \
  --data-dir data/real/APM_DATA \
  --output graflo_experiment/manifest.apm_topology.yaml
```

The generator writes plain YAML scalars where possible, so the manifest stays
easy to read and does not wrap every value in quotes.

## Validate With Graflo

Install Graflo in the environment where you want to test it:

```bash
python3 -m pip install graflo
```

Then validate the generated manifest:

```bash
python3 graflo_experiment/validate_manifest.py \
  --manifest graflo_experiment/manifest.apm_topology.yaml
```

The manifest should not contain runtime connector fields:

```bash
grep -n "sub_path\|bindings:\|core_schema\|apply:\|source_key\|target_key" graflo_experiment/manifest.apm_topology.yaml
```

This command should print nothing.

To also validate that the runtime file bindings can be constructed:

```bash
python3 graflo_experiment/validate_manifest.py \
  --manifest graflo_experiment/manifest.apm_topology.yaml \
  --data-dir data/real/APM_DATA
```

The manifest YAML intentionally does not include `FileConnector.sub_path`.
Graflo's `4-ingest-neo4j` example creates `Bindings` and
`FileConnector(..., sub_path=Path(...))` in Python at runtime, then attaches
bindings with `manifest.model_copy(update={"bindings": bindings})`.

## Visualize The Graflo Manifest Locally

If Docker or local Memgraph is unhealthy, you can still preview the graph
described by the Graflo manifest. This command executes the simple
vertex/edge pipelines generated in this folder and writes the same JSON format
used by the custom HTML viewer:

```bash
python3 graflo_experiment/export_manifest_graph.py \
  --data-dir data/mock \
  --manifest graflo_experiment/manifest.apm_topology.yaml \
  --output build/graflo_topology_graph.json \
  --out-cypher build/graflo_topology_graph.cypher \
  --viewer-output build/graflo_topology_viewer.html
```

For real CSV exports:

```bash
python3 graflo_experiment/export_manifest_graph.py \
  --data-dir data/real/APM_DATA \
  --manifest graflo_experiment/manifest.apm_topology.yaml \
  --output build/graflo_topology_graph.json \
  --out-cypher build/graflo_topology_graph.cypher \
  --viewer-output build/graflo_topology_viewer.html
```

Then open `build/graflo_topology_viewer.html`.

For a focused view around one application:

```bash
python3 graflo_experiment/export_manifest_graph.py \
  --data-dir data/real/APM_DATA \
  --application-name "SERVICE NOW" \
  --focus-depth 2 \
  --max-nodes 120 \
  --max-edges 180
```

This preview path does not call Graflo's database ingestion runtime. It is a
local renderer for the manifest shape we generate here, useful for checking the
nodes and relationships before loading anything into Memgraph.

## Load The Manifest-Built Graph By Bolt

After the local HTML preview looks correct, load the same manifest-built graph
into a dedicated Memgraph test instance. Use `--clear` only when that instance
is safe to wipe:

```bash
python3 graflo_experiment/export_manifest_graph.py \
  --data-dir data/real/APM_DATA \
  --manifest graflo_experiment/manifest.apm_topology.yaml \
  --no-viewer \
  --load-memgraph \
  --clear \
  --uri "bolt://HOST:PORT" \
  --username "YOUR_USERNAME" \
  --password "YOUR_PASSWORD" \
  --batch-size 1000
```

This is not Graflo's own ingestion engine; it uses the Graflo manifest preview
graph and the repository's existing Bolt loader. To test Graflo's official
ingestion runtime, use `ingest.py` after installing Graflo.

## Mapped Vertices

- `Cluster` from `apm_cluster`
- `Subcluster` from `apm_subclusters`
- `Application` from `apm_applications`
- `Contact` from `apm_contacts`
- `ApplicationDap` from `apm_application_daps`
- `Dap` from `apm_application_daps.dap_id`
- `Technology` from `apm_technologies`
- `ObsolescenceRecord` from `apm_obso`
- `Host` from `apm_obso.host`
- `Criticality` from `apm_obso.criticality`
- `Environment` from `apm_obso.env`
- `LocationCountry` from `apm_obso.location_country`

## Mapped Edges

- `Cluster -HAS_SUBCLUSTER-> Subcluster`
- `Cluster -HAS_APPLICATION-> Application`
- `Application -HAS_PRODUCTION_DOMAIN_MANAGER-> Contact`
- `Application -HAS_APPLICATION_MANAGER-> Contact`
- `Application -HAS_DOMAIN_MANAGER-> Contact`
- `Application -HAS_PRODUCTION_MANAGER-> Contact`
- `Application -HAS_APM_SPOC-> Contact`
- `Application -HAS_DAP_BINDING-> ApplicationDap`
- `ApplicationDap -TARGETS_DAP-> Dap`
- `Application -EXPOSES_DAP-> Dap`
- `Application -HAS_OBSOLESCENCE_RECORD-> ObsolescenceRecord`
- `ObsolescenceRecord -ON_HOST-> Host`
- `ObsolescenceRecord -REFERENCES_TECHNOLOGY-> Technology`
- `ObsolescenceRecord -HAS_CRITICALITY-> Criticality`
- `ObsolescenceRecord -IN_ENVIRONMENT-> Environment`
- `ObsolescenceRecord -LOCATED_IN-> LocationCountry`

This first manifest focuses on direct, source-table edges. The current custom
builder still owns derived shortcuts such as `DEPLOYED_ON`, `USES_TECHNOLOGY`,
`HAS_TECHNOLOGY`, and `RELATED_TO` until we confirm the Graflo ingestion shape.

## Ingest With Graflo

After the manifest validates, configure Graflo's Neo4j-compatible connection
environment variables for your target database, for example:

```bash
export NEO4J_URI="bolt://HOST:PORT"
export NEO4J_USERNAME="YOUR_USERNAME"
export NEO4J_PASSWORD="YOUR_PASSWORD"
```

Then ingest:

```bash
python3 graflo_experiment/ingest.py \
  --manifest graflo_experiment/manifest.apm_topology.yaml \
  --data-dir data/real/APM_DATA \
  --clear \
  --batch-size 1000
```

Use `--clear` only for a dedicated test database.

## Resource Shape

The manifest uses one resource per source table:

- `apm_cluster`
- `apm_subclusters`
- `apm_applications`
- `apm_contacts`
- `apm_application_daps`
- `apm_obso`
- `apm_technologies`

The central topology resources are `apm_applications`, `apm_application_daps`,
and `apm_obso`. `apm_applications` creates the application, cluster, and
contact-role edges. `apm_application_daps` creates the deployed-application
binding and DAP edges. `apm_obso` creates obsolescence records, application
links, host links, technology links, and operational dimensions such as
criticality, environment, and country.
