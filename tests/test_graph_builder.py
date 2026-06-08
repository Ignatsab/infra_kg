from __future__ import annotations

import unittest

from infra_kg.graph_builder import build_graph_from_tables
from infra_kg.mock_data import mock_tables


class GraphBuilderTest(unittest.TestCase):
    def test_source_edges_follow_declared_foreign_keys(self) -> None:
        graph = build_graph_from_tables(mock_tables(), include_derived=False)

        self.assertEqual([], graph.warnings)
        self.assertEqual(
            {
                "Application": 7,
                "Cluster": 3,
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
                "HAS_OBSOLESCENCE_RECORD": 14,
                "HAS_SUBCLUSTER": 6,
                "ON_HOST": 14,
                "REFERENCES_TECHNOLOGY": 14,
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


if __name__ == "__main__":
    unittest.main()
