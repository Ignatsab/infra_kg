"""APM topology mapping for a GraFlo manifest experiment.

This file is intentionally separate from the existing infra_kg graph builder.
It records the table-to-vertex and table-to-edge contract in a compact form so
we can generate a GraFlo-style manifest and review it with Graflo's author.
"""

from __future__ import annotations

TABLE_ALIASES = {
    "apm_cluster": ["apm_cluster", "apm_clusters"],
}

VERTICES = [
    {
        "name": "Cluster",
        "source_table": "apm_cluster",
        "identity": {"id": "id"},
        "source_columns": "all",
    },
    {
        "name": "Subcluster",
        "source_table": "apm_subclusters",
        "identity": {"id": "id"},
        "source_columns": "all",
    },
    {
        "name": "Application",
        "source_table": "apm_applications",
        "identity": {"id": "id"},
        "source_columns": "all",
    },
    {
        "name": "Contact",
        "source_table": "apm_contacts",
        "identity": {"id": "id"},
        "source_columns": "all",
    },
    {
        "name": "ApplicationDap",
        "source_table": "apm_application_daps",
        "identity": {"id": "id"},
        "source_columns": "all",
    },
    {
        "name": "Dap",
        "source_table": "apm_application_daps",
        "identity": {"id": "dap_id"},
        "properties": {"name": "dap_name"},
    },
    {
        "name": "Technology",
        "source_table": "apm_technologies",
        "identity": {"id": "id"},
        "source_columns": "all",
    },
    {
        "name": "ObsolescenceRecord",
        "source_table": "apm_obso",
        "identity": {"id": "id"},
        "source_columns": "all",
    },
    {
        "name": "Host",
        "source_table": "apm_obso",
        "identity": {"id": "host"},
        "properties": {"name": "host"},
    },
    {
        "name": "Criticality",
        "source_table": "apm_obso",
        "identity": {"id": "criticality"},
        "properties": {"name": "criticality"},
    },
    {
        "name": "Environment",
        "source_table": "apm_obso",
        "identity": {"id": "env"},
        "properties": {"name": "env"},
    },
    {
        "name": "LocationCountry",
        "source_table": "apm_obso",
        "identity": {"id": "location_country"},
        "properties": {"name": "location_country"},
    },
]

EDGES = [
    {
        "name": "HAS_SUBCLUSTER",
        "source": "Cluster",
        "target": "Subcluster",
        "source_table": "apm_subclusters",
        "source_key": {"vertex_field": "id", "column": "apm_cluster"},
        "target_key": {"vertex_field": "id", "column": "id"},
    },
    {
        "name": "HAS_APPLICATION",
        "source": "Cluster",
        "target": "Application",
        "source_table": "apm_applications",
        "source_key": {"vertex_field": "id", "column": "apm_cluster"},
        "target_key": {"vertex_field": "id", "column": "id"},
    },
    {
        "name": "HAS_PRODUCTION_DOMAIN_MANAGER",
        "source": "Application",
        "target": "Contact",
        "source_table": "apm_applications",
        "source_key": {"vertex_field": "id", "column": "id"},
        "target_key": {"vertex_field": "id", "column": "production_domain_manager"},
    },
    {
        "name": "HAS_APPLICATION_MANAGER",
        "source": "Application",
        "target": "Contact",
        "source_table": "apm_applications",
        "source_key": {"vertex_field": "id", "column": "id"},
        "target_key": {"vertex_field": "id", "column": "application_manager"},
    },
    {
        "name": "HAS_DOMAIN_MANAGER",
        "source": "Application",
        "target": "Contact",
        "source_table": "apm_applications",
        "source_key": {"vertex_field": "id", "column": "id"},
        "target_key": {"vertex_field": "id", "column": "domain_manager"},
    },
    {
        "name": "HAS_PRODUCTION_MANAGER",
        "source": "Application",
        "target": "Contact",
        "source_table": "apm_applications",
        "source_key": {"vertex_field": "id", "column": "id"},
        "target_key": {"vertex_field": "id", "column": "production_manager"},
    },
    {
        "name": "HAS_APM_SPOC",
        "source": "Application",
        "target": "Contact",
        "source_table": "apm_applications",
        "source_key": {"vertex_field": "id", "column": "id"},
        "target_key": {"vertex_field": "id", "column": "apm_spoc"},
    },
    {
        "name": "HAS_DAP_BINDING",
        "source": "Application",
        "target": "ApplicationDap",
        "source_table": "apm_application_daps",
        "source_key": {"vertex_field": "id", "column": "apm_application"},
        "target_key": {"vertex_field": "id", "column": "id"},
    },
    {
        "name": "TARGETS_DAP",
        "source": "ApplicationDap",
        "target": "Dap",
        "source_table": "apm_application_daps",
        "source_key": {"vertex_field": "id", "column": "id"},
        "target_key": {"vertex_field": "id", "column": "dap_id"},
    },
    {
        "name": "EXPOSES_DAP",
        "source": "Application",
        "target": "Dap",
        "source_table": "apm_application_daps",
        "source_key": {"vertex_field": "id", "column": "apm_application"},
        "target_key": {"vertex_field": "id", "column": "dap_id"},
        "source_columns": "all",
    },
    {
        "name": "HAS_OBSOLESCENCE_RECORD",
        "source": "Application",
        "target": "ObsolescenceRecord",
        "source_table": "apm_obso",
        "source_key": {"vertex_field": "id", "column": "application_id"},
        "target_key": {"vertex_field": "id", "column": "id"},
    },
    {
        "name": "ON_HOST",
        "source": "ObsolescenceRecord",
        "target": "Host",
        "source_table": "apm_obso",
        "source_key": {"vertex_field": "id", "column": "id"},
        "target_key": {"vertex_field": "id", "column": "host"},
    },
    {
        "name": "REFERENCES_TECHNOLOGY",
        "source": "ObsolescenceRecord",
        "target": "Technology",
        "source_table": "apm_obso",
        "source_key": {"vertex_field": "id", "column": "id"},
        "target_key": {"vertex_field": "id", "column": "technology_id"},
    },
    {
        "name": "HAS_CRITICALITY",
        "source": "ObsolescenceRecord",
        "target": "Criticality",
        "source_table": "apm_obso",
        "source_key": {"vertex_field": "id", "column": "id"},
        "target_key": {"vertex_field": "id", "column": "criticality"},
    },
    {
        "name": "IN_ENVIRONMENT",
        "source": "ObsolescenceRecord",
        "target": "Environment",
        "source_table": "apm_obso",
        "source_key": {"vertex_field": "id", "column": "id"},
        "target_key": {"vertex_field": "id", "column": "env"},
    },
    {
        "name": "LOCATED_IN_COUNTRY",
        "source": "ObsolescenceRecord",
        "target": "LocationCountry",
        "source_table": "apm_obso",
        "source_key": {"vertex_field": "id", "column": "id"},
        "target_key": {"vertex_field": "id", "column": "location_country"},
    },
]
