from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from infra_kg.embeddings import HashEmbeddingProvider
from infra_kg.graph_builder import build_graph, build_graph_from_tables
from infra_kg.mock_data import TABLE_FIELDS, mock_tables


class GraphBuilderTest(unittest.TestCase):
    def test_source_edges_follow_declared_foreign_keys(self) -> None:
        graph = build_graph_from_tables(mock_tables(), include_derived=False)

        self.assertEqual([], graph.warnings)
        self.assertEqual(
            {
                "Application": 7,
                "ApplicationDap": 10,
                "Cluster": 3,
                "Contact": 6,
                "Dap": 6,
                "Host": 12,
                "ObsolescenceRecord": 14,
                "Subcluster": 6,
                "Technology": 8,
            },
            graph.label_counts(),
        )
        self.assertEqual(
            {
                "EXPOSES_DAP": 10,
                "HAS_APPLICATION": 7,
                "HAS_APPLICATION_MANAGER": 7,
                "HAS_APM_SPOC": 7,
                "HAS_DAP_BINDING": 10,
                "HAS_DOMAIN_MANAGER": 7,
                "HAS_OBSOLESCENCE_RECORD": 14,
                "HAS_PRODUCTION_DOMAIN_MANAGER": 7,
                "HAS_PRODUCTION_MANAGER": 7,
                "HAS_SUBCLUSTER": 6,
                "ON_HOST": 14,
                "REFERENCES_TECHNOLOGY": 14,
                "TARGETS_DAP": 10,
            },
            graph.edge_counts(),
        )

    def test_derived_edges_add_agent_friendly_shortcuts(self) -> None:
        graph = build_graph_from_tables(mock_tables())

        edge_counts = graph.edge_counts()
        self.assertGreater(edge_counts["DEPLOYED_ON"], 0)
        self.assertGreater(edge_counts["USES_TECHNOLOGY"], 0)
        self.assertGreater(edge_counts["HAS_TECHNOLOGY"], 0)
        self.assertGreater(edge_counts["RELATED_TO"], 0)

        app_payments = graph.nodes["Application:app_payments"]
        self.assertEqual("Payments API", app_payments.properties["name"])
        self.assertIn("retrieval_text", app_payments.properties)

    def test_application_contact_role_edges_are_created(self) -> None:
        graph = build_graph_from_tables(mock_tables(), include_derived=False)

        role_edges = {
            edge.type: edge.end_key
            for edge in graph.edges
            if edge.start_key == "Application:app_payments" and edge.end_key.startswith("Contact:")
        }
        self.assertEqual(
            {
                "HAS_PRODUCTION_DOMAIN_MANAGER": "Contact:contact_alice",
                "HAS_APPLICATION_MANAGER": "Contact:contact_boris",
                "HAS_DOMAIN_MANAGER": "Contact:contact_chloe",
                "HAS_PRODUCTION_MANAGER": "Contact:contact_daniel",
                "HAS_APM_SPOC": "Contact:contact_elena",
            },
            role_edges,
        )

    def test_apm_clusters_alias_is_supported_for_table_dicts(self) -> None:
        tables = mock_tables()
        tables["apm_clusters"] = tables.pop("apm_cluster")

        graph = build_graph_from_tables(tables, include_derived=False)

        self.assertEqual(3, graph.label_counts()["Cluster"])
        self.assertEqual(7, graph.edge_counts()["HAS_APPLICATION"])
        self.assertEqual([], graph.warnings)

    def test_apm_clusters_alias_is_supported_for_csv_files(self) -> None:
        tables = mock_tables()
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            for table_name, rows in tables.items():
                output_name = "apm_clusters" if table_name == "apm_cluster" else table_name
                with (base / f"{output_name}.csv").open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=TABLE_FIELDS[table_name])
                    writer.writeheader()
                    writer.writerows(rows)

            graph = build_graph(base, include_derived=False)

        self.assertEqual(3, graph.label_counts()["Cluster"])
        self.assertEqual(7, graph.edge_counts()["HAS_APPLICATION"])
        self.assertEqual([], graph.warnings)

    def test_hash_embeddings_are_added_to_nodes(self) -> None:
        graph = build_graph_from_tables(mock_tables(), embedding_provider=HashEmbeddingProvider(dimensions=16))

        app_payments = graph.nodes["Application:app_payments"]
        self.assertEqual(16, len(app_payments.properties["embedding"]))
        self.assertEqual(16, app_payments.properties["embedding_dimensions"])

    def test_extra_source_columns_are_preserved(self) -> None:
        tables = mock_tables()
        tables["apm_applications"][0]["Owner Email"] = "payments@example.test"
        tables["apm_application_daps"][0]["SLA Tier"] = "gold"

        graph = build_graph_from_tables(tables, include_derived=False)

        self.assertEqual(
            "payments@example.test",
            graph.nodes["Application:app_payments"].properties["Owner_Email"],
        )
        self.assertEqual(
            "gold",
            graph.nodes["ApplicationDap:adap_001"].properties["SLA_Tier"],
        )

        exposes_dap = [
            edge
            for edge in graph.edges
            if edge.start_key == "Application:app_payments"
            and edge.type == "EXPOSES_DAP"
            and edge.end_key == "Dap:dap_payment_events"
        ][0]
        self.assertEqual("gold", exposes_dap.properties["SLA_Tier"])

    def test_large_related_groups_are_skipped_by_default(self) -> None:
        tables = mock_tables()
        tables["apm_applications"] = [
            {
                "id": f"app_{idx}",
                "name": f"Application {idx}",
                "apm_cluster": "cl_eu_prod",
                "criticality": "tier_3",
                "business_owner": "test",
                "runtime_tier": "service",
            }
            for idx in range(5)
        ]
        tables["apm_application_daps"] = []
        tables["apm_obso"] = []

        graph = build_graph_from_tables(tables, max_related_group_size=3)

        self.assertNotIn("RELATED_TO", graph.edge_counts())
        self.assertTrue(any("Skipped RELATED_TO expansion" in warning for warning in graph.warnings))


if __name__ == "__main__":
    unittest.main()
