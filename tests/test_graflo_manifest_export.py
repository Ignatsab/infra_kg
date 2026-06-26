from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

from infra_kg.graph_builder import build_graph_from_tables
from infra_kg.mock_data import TABLE_FIELDS, mock_tables


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "export_manifest_graph",
    ROOT / "graflo_experiment" / "export_manifest_graph.py",
)
export_manifest_graph = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(export_manifest_graph)


class GrafloManifestExportTest(unittest.TestCase):
    def test_generated_manifest_yaml_can_be_read_without_pyyaml(self) -> None:
        manifest = export_manifest_graph.parse_generated_yaml(
            (ROOT / "graflo_experiment" / "manifest.apm_topology.yaml").read_text(encoding="utf-8")
        )

        self.assertEqual("apm_topology", manifest["schema"]["metadata"]["name"])
        self.assertEqual(
            "Cluster",
            manifest["schema"]["graph"]["vertex_config"]["vertices"][0]["name"],
        )
        self.assertGreater(len(manifest["ingestion_model"]["resources"]), 0)

    def test_manifest_preview_matches_direct_fk_graph_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = write_mock_csvs(Path(tmp_dir), cluster_filename="apm_cluster")
            manifest = export_manifest_graph.load_manifest_or_rebuild(
                ROOT / "graflo_experiment" / "missing-for-test.yaml",
                base,
            )[0]

            graph = export_manifest_graph.build_graph_from_manifest(manifest, base)

        expected = build_graph_from_tables(mock_tables(), include_derived=False)
        self.assertEqual(expected.label_counts(), graph.label_counts())
        self.assertEqual(expected.edge_counts(), graph.edge_counts())
        self.assertEqual([], graph.warnings)

    def test_manifest_preview_supports_apm_clusters_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = write_mock_csvs(Path(tmp_dir), cluster_filename="apm_clusters")
            manifest = export_manifest_graph.load_manifest_or_rebuild(
                ROOT / "graflo_experiment" / "missing-for-test.yaml",
                base,
            )[0]

            graph = export_manifest_graph.build_graph_from_manifest(manifest, base)

        self.assertEqual(3, graph.label_counts()["Cluster"])
        self.assertEqual(7, graph.edge_counts()["HAS_APPLICATION"])
        self.assertEqual([], graph.warnings)


def write_mock_csvs(base: Path, *, cluster_filename: str) -> Path:
    tables = mock_tables()
    for table_name, rows in tables.items():
        output_name = cluster_filename if table_name == "apm_cluster" else table_name
        with (base / f"{output_name}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TABLE_FIELDS[table_name])
            writer.writeheader()
            writer.writerows(rows)
    return base


if __name__ == "__main__":
    unittest.main()
