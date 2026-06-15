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


if __name__ == "__main__":
    unittest.main()
