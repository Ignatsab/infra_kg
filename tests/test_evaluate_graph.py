from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from infra_kg.graph_builder import build_graph_from_tables
from infra_kg.mock_data import mock_tables


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evaluate_graph", ROOT / "scripts" / "evaluate_graph.py")
evaluate_graph = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(evaluate_graph)


class EvaluateGraphTest(unittest.TestCase):
    def test_mock_graph_has_no_structural_errors(self) -> None:
        graph = build_graph_from_tables(mock_tables()).to_dict()

        report = evaluate_graph.evaluate_graph(graph)

        self.assertEqual("PASS", report["status"])
        self.assertEqual(100, report["quality_score"])
        self.assertEqual(0, report["schema"]["broken_edge_count"])
        self.assertEqual(0, report["schema"]["schema_violation_count"])
        self.assertEqual(1, report["connectivity"]["component_count"])

    def test_broken_edge_and_schema_violation_are_reported(self) -> None:
        graph = build_graph_from_tables(mock_tables()).to_dict()
        graph["edges"].append(
            {
                "start_key": "Application:app_payments",
                "type": "HAS_APPLICATION",
                "end_key": "Technology:tech_java8",
                "properties": {},
            }
        )
        graph["edges"].append(
            {
                "start_key": "Application:app_missing",
                "type": "USES_TECHNOLOGY",
                "end_key": "Technology:tech_java8",
                "properties": {},
            }
        )

        report = evaluate_graph.evaluate_graph(graph)

        self.assertEqual("FAIL", report["status"])
        self.assertEqual(1, report["schema"]["broken_edge_count"])
        self.assertEqual(1, report["schema"]["schema_violation_count"])


if __name__ == "__main__":
    unittest.main()
