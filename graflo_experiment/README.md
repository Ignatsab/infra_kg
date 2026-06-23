# GraFlo APM Topology Experiment

This folder is a separate experiment for trying the same APM topology graph with
GraFlo, without changing the current `src/infra_kg` builder or Memgraph loader.

GraFlo is manifest-driven: the manifest describes vertices, edges, identities,
properties, ingestion resources, and source bindings. In our case the important
part is the table relationship contract: which table column creates a node id,
and which table column points to another node id.

## Files

- `apm_mapping.py` - compact source of truth for APM vertices and edges.
- `generate_manifest.py` - generates a GraFlo-style YAML manifest from the
  mapping and current CSV headers.
- `manifest.apm_topology.yaml` - generated manifest draft.
- `validate_manifest.py` - optional validation using Graflo, if installed.

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
