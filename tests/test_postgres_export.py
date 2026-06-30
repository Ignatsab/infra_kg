from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "export_postgres_apm_csv",
    ROOT / "scripts" / "export_postgres_apm_csv.py",
)
export_postgres_apm_csv = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = export_postgres_apm_csv
SPEC.loader.exec_module(export_postgres_apm_csv)


class PostgresExportTest(unittest.TestCase):
    def test_normalize_table_names_removes_schema_and_duplicates(self) -> None:
        self.assertEqual(
            ["apm_applications", "apm_obso"],
            export_postgres_apm_csv.normalize_table_names(
                [" public.apm_applications ", "apm_applications", "prod.apm_obso"]
            ),
        )

    def test_connection_kwargs_prefers_dsn(self) -> None:
        settings = export_postgres_apm_csv.PostgresSettings(
            dsn="postgresql://example",
            host=None,
            port=None,
            database=None,
            username=None,
            password=None,
            schema="public",
        )

        self.assertEqual("postgresql://example", export_postgres_apm_csv.connection_kwargs(settings))

    def test_postgres_settings_reads_common_env_names(self) -> None:
        env = {
            "PGHOST": "db.example.test",
            "PGPORT": "5433",
            "PGDATABASE": "cmdb",
            "PGUSER": "reader",
            "PGPASSWORD": "secret",
            "POSTGRES_SCHEMA": "inventory",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = export_postgres_apm_csv.postgres_settings()

        self.assertEqual("db.example.test", settings.host)
        self.assertEqual("5433", settings.port)
        self.assertEqual("cmdb", settings.database)
        self.assertEqual("reader", settings.username)
        self.assertEqual("secret", settings.password)
        self.assertEqual("inventory", settings.schema)


if __name__ == "__main__":
    unittest.main()
