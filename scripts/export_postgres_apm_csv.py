#!/usr/bin/env python3
"""Export APM tables from PostgreSQL into the CSV staging directory."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from infra_kg.env import load_dotenv


@dataclass(frozen=True)
class PostgresSettings:
    dsn: str | None
    host: str | None
    port: str | None
    database: str | None
    username: str | None
    password: str | None
    schema: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Export apm_* PostgreSQL tables to CSV files.")
    parser.add_argument("--output-dir", default="data/real/APM_DATA", help="Directory where CSV files will be written.")
    parser.add_argument("--env-path", default=".env", help="Path to .env with PostgreSQL credentials.")
    parser.add_argument("--schema", default=None, help="PostgreSQL schema. Defaults to POSTGRES_SCHEMA or public.")
    parser.add_argument("--table-prefix", default="apm_", help="Export tables whose names start with this prefix.")
    parser.add_argument(
        "--table",
        action="append",
        default=[],
        help="Specific table to export. Can be used multiple times. If omitted, tables are discovered by prefix.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional per-table row limit. 0 means no limit.")
    parser.add_argument("--batch-size", type=int, default=5000, help="Rows fetched from PostgreSQL at a time.")
    parser.add_argument("--include-views", action="store_true", help="Also discover views matching the table prefix.")
    args = parser.parse_args()

    load_dotenv(args.env_path)
    settings = postgres_settings(schema_override=args.schema)
    psycopg, sql = import_psycopg()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    table_names = normalize_table_names(args.table)

    with psycopg.connect(connection_kwargs(settings)) as connection:
        if not table_names:
            table_names = discover_tables(
                connection,
                settings.schema,
                args.table_prefix,
                include_views=args.include_views,
            )
        if not table_names:
            raise SystemExit(
                f"No tables found in schema {settings.schema!r} with prefix {args.table_prefix!r}."
            )

        print(f"Exporting {len(table_names)} table(s) from schema {settings.schema} to {output_dir}")
        for table_name in table_names:
            row_count = export_table(
                connection,
                sql,
                settings.schema,
                table_name,
                output_dir / f"{table_name}.csv",
                limit=args.limit,
                batch_size=args.batch_size,
            )
            print(f"- {table_name}: {row_count} row(s)")


def postgres_settings(*, schema_override: str | None = None) -> PostgresSettings:
    return PostgresSettings(
        dsn=os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL"),
        host=os.environ.get("POSTGRES_HOST") or os.environ.get("PGHOST"),
        port=os.environ.get("POSTGRES_PORT") or os.environ.get("PGPORT"),
        database=(
            os.environ.get("POSTGRES_DB")
            or os.environ.get("POSTGRES_DATABASE")
            or os.environ.get("PGDATABASE")
        ),
        username=os.environ.get("POSTGRES_USER") or os.environ.get("PGUSER"),
        password=os.environ.get("POSTGRES_PASSWORD") or os.environ.get("PGPASSWORD"),
        schema=schema_override or os.environ.get("POSTGRES_SCHEMA") or "public",
    )


def import_psycopg():
    try:
        import psycopg
        from psycopg import sql

        return psycopg, sql
    except ImportError as exc:
        raise SystemExit(
            "Missing PostgreSQL driver. Install dependencies with:\n"
            "  python3 -m pip install -r requirements.txt"
        ) from exc


def connection_kwargs(settings: PostgresSettings) -> str | dict[str, Any]:
    if settings.dsn:
        return settings.dsn

    missing = [
        name
        for name, value in {
            "POSTGRES_HOST": settings.host,
            "POSTGRES_DB": settings.database,
            "POSTGRES_USER": settings.username,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing PostgreSQL connection settings. Set POSTGRES_DSN or "
            f"set {', '.join(missing)} in your .env file."
        )

    kwargs: dict[str, Any] = {
        "host": settings.host,
        "dbname": settings.database,
        "user": settings.username,
    }
    if settings.port:
        kwargs["port"] = settings.port
    if settings.password:
        kwargs["password"] = settings.password
    return kwargs


def discover_tables(
    connection,
    schema: str,
    table_prefix: str,
    *,
    include_views: bool,
) -> list[str]:
    table_types = ["BASE TABLE"]
    if include_views:
        table_types.append("VIEW")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name LIKE %s
              AND table_type = ANY(%s)
            ORDER BY table_name
            """,
            (schema, f"{table_prefix}%", table_types),
        )
        return [row[0] for row in cursor.fetchall()]


def export_table(
    connection,
    sql,
    schema: str,
    table_name: str,
    output_path: Path,
    *,
    limit: int,
    batch_size: int,
) -> int:
    query = sql.SQL("SELECT * FROM {}.{}").format(
        sql.Identifier(schema),
        sql.Identifier(table_name),
    )
    if limit > 0:
        query += sql.SQL(" LIMIT {}").format(sql.Literal(limit))

    row_count = 0
    with connection.cursor() as cursor:
        cursor.execute(query)
        headers = [column.name for column in cursor.description or []]
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            while True:
                rows = cursor.fetchmany(max(1, batch_size))
                if not rows:
                    break
                writer.writerows(rows)
                row_count += len(rows)
    return row_count


def normalize_table_names(table_names: Iterable[str]) -> list[str]:
    normalized = []
    seen = set()
    for table_name in table_names:
        clean = table_name.strip()
        if not clean:
            continue
        if "." in clean:
            clean = clean.rsplit(".", 1)[-1]
        if clean not in seen:
            normalized.append(clean)
            seen.add(clean)
    return normalized


if __name__ == "__main__":
    main()
