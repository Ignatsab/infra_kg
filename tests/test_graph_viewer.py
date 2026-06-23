from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from infra_kg.graph_builder import build_graph_from_tables
from infra_kg.mock_data import mock_tables


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_graph_viewer", ROOT / "scripts" / "render_graph_viewer.py")
render_graph_viewer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(render_graph_viewer)


class GraphViewerTest(unittest.TestCase):
    def test_sample_keeps_all_labels_and_relationship_types_when_possible(self) -> None:
        graph = build_graph_from_tables(mock_tables()).to_dict()

        sampled = render_graph_viewer.sample_graph(graph, max_nodes=40, max_edges=80)

        self.assertEqual(
            sorted({node["label"] for node in graph["nodes"]}),
            sorted({node["label"] for node in sampled["nodes"]}),
        )
        self.assertEqual(
            sorted({edge["type"] for edge in graph["edges"]}),
            sorted({edge["type"] for edge in sampled["edges"]}),
        )
        self.assertTrue(sampled["metadata"]["sampled"])

    def test_focus_application_graph_matches_name_and_keeps_neighborhood(self) -> None:
        graph = build_graph_from_tables(mock_tables()).to_dict()

        focused = render_graph_viewer.focus_application_graph(
            graph,
            application_name="payments api",
            application_id=None,
            depth=2,
            max_nodes=40,
            max_edges=80,
            exclude_edge_types=set(),
        )

        keys = {node["key"] for node in focused["nodes"]}
        edge_endpoints = {(edge["start_key"], edge["end_key"]) for edge in focused["edges"]}

        self.assertIn("Application:app_payments", keys)
        self.assertIn("ObsolescenceRecord:obso_001", keys)
        self.assertIn("Host:pay-api-01.eu.prod", keys)
        self.assertIn("Technology:tech_java8", keys)
        self.assertIn(("ObsolescenceRecord:obso_001", "Host:pay-api-01.eu.prod"), edge_endpoints)
        self.assertTrue(focused["metadata"]["focused"])
        self.assertEqual(1, focused["metadata"]["focus_root_count"])

    def test_focus_application_graph_respects_limits(self) -> None:
        graph = build_graph_from_tables(mock_tables()).to_dict()

        focused = render_graph_viewer.focus_application_graph(
            graph,
            application_name="payments",
            application_id=None,
            depth=3,
            max_nodes=6,
            max_edges=5,
            exclude_edge_types=set(),
        )
        keys = {node["key"] for node in focused["nodes"]}

        self.assertLessEqual(len(focused["nodes"]), 6)
        self.assertLessEqual(len(focused["edges"]), 5)
        self.assertIn("Application:app_payments", keys)
        for edge in focused["edges"]:
            self.assertIn(edge["start_key"], keys)
            self.assertIn(edge["end_key"], keys)
        self.assertTrue(focused["metadata"]["hit_node_limit"] or focused["metadata"]["hit_edge_limit"])

    def test_focus_application_graph_reports_missing_match(self) -> None:
        graph = build_graph_from_tables(mock_tables()).to_dict()

        with self.assertRaisesRegex(ValueError, "No Application node matched"):
            render_graph_viewer.focus_application_graph(
                graph,
                application_name="definitely missing",
                application_id=None,
                depth=1,
                max_nodes=20,
                max_edges=20,
                exclude_edge_types=set(),
            )


if __name__ == "__main__":
    unittest.main()
