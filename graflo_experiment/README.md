# GraFlo APM Topology Experiment

This folder is a separate experiment for trying the same APM topology graph with
GraFlo, without changing the current `src/infra_kg` builder or Memgraph loader.

GraFlo is manifest-driven: the manifest describes vertices, edges, identities,
properties, and ingestion resources. Runtime bindings connect those resources to
physical CSV files. In our case the important part is the table relationship
contract: which table column creates a node id, and which table column points to
another node id.

This experiment follows the Graflo documentation and the official
`examples/4-ingest-neo4j` pattern:

- `schema.graph.vertex_config.vertices` defines logical node types.
- `schema.graph.edge_config.edges` defines logical edge types with `relation`.
- `ingestion_model.resources[*].pipeline` maps each source record into vertices
  and edges.
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
- `ObsolescenceRecord -LOCATED_IN_COUNTRY-> LocationCountry`

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

## Why There Are Many Resources

The manifest creates one vertex resource per source-derived vertex and one edge
resource per relationship. This is deliberate: it avoids ambiguous same-label
vertices in one row, especially the five different `Application -> Contact`
roles. Every edge resource creates exactly the two endpoint vertices it needs
and then emits one `source/target/relation` step.
